---
name: confluent-kafka-bigquery-ingestion
description: Ingest Kafka topics from Confluent Cloud directly into Google Cloud BigQuery and BigLake Apache Iceberg tables using BigQueryStorageSink with static SMTs, in-place connector upgrades, and partitioned historical backfills.
metadata:
  version: "1.1.0"
---

# Confluent Cloud to BigQuery & BigLake Iceberg Ingestion (BigQueryStorageSink)

A comprehensive guide and production-grade operational pattern for streaming high-volume Kafka topics from Confluent Cloud directly into Google Cloud BigQuery and BigLake Managed Apache Iceberg tables using the fully-managed `BigQueryStorageSink` connector, static Single Message Transforms (SMTs), zero-downtime in-place upgrades, and partition-scoped historical backfills.

---

## 1. Architectural Overview

```
                                  CONFLUENT CLOUD
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  Kafka Clusters (Multi-Tenant & Platform Core)                                               │
│    Topics: imt-message, httpresponse, session, transport (Raw JSON / String payloads)        │
│                                │                                                             │
│                                ▼                                                             │
│  BigQueryStorageSink Connector (Tasks 0..N per tenant/cluster)                               │
│    ├── SMT 1: HoistField$Value (wraps raw string payload into struct.data)                  │
│    ├── SMT 2: InsertField$Value (extracts offset, partition, timestamp, topic, key)          │
│    ├── SMT 3: InsertField$Value (duplicates timestamp -> _meta_ingestion_time)              │
│    ├── SMT 4: InsertField$Value (injects static _meta_source_signature = '<tenant>')         │
│    └── SMT 5: Cast$Value (casts _meta_partition_id from int32 to STRING)                    │
│                                │                                                             │
│    Auth: Google Service Account Impersonation (Provider Integration / Workload Identity)     │
└────────────────────────────────┼─────────────────────────────────────────────────────────────┘
                                 │ Google Cloud BigQuery Storage Write API (Streaming)
                                 ▼
                     GOOGLE CLOUD PLATFORM (GCP)
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│  BigQuery Dataset (e.g., raw_platform_kfkconn)                                               │
│    ├── BigLake Managed Apache Iceberg Tables (table_format = 'ICEBERG', Parquet in GCS)     │
│    │     Partitioned by: DATE(_meta_ingestion_time) or DATE(_meta_enqueued_time)             │
│    │     Clustered by:   _meta_namespace, _meta_partition_id                                 │
│    │     Storage URI:    gs://<lakehouse-bucket>/<table_name>                                │
│    └── Native BigQuery Tables (Standard Storage)                                            │
│                                                                                              │
│  Historical Backfills & Parity Audits                                                        │
│    └── Day-by-Day Partition Pruned UPDATEs (bypasses Streaming Buffer lock)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Critical Constraints & Gotchas

### A. BigLake Apache Iceberg Streaming Support & Crucial IAM Permissions
- **Discovery**: The `BigQueryStorageSink` connector (via the BigQuery Storage Write API) **DOES natively support streaming directly into BigLake Managed Apache Iceberg tables**.
- **Crucial IAM Requirement for BigLake Connection**:
  - The BigQuery Connection Service Account (format: `bqcx-<project_number>-<hash>@gcp-sa-bigquery-condel.iam.gserviceaccount.com`) **MUST have bucket-level metadata permissions** (`storage.buckets.get`, e.g. via role `roles/storage.admin` or `roles/storage.legacyBucketReader`) on the target GCS bucket, in addition to object-level permissions (`roles/storage.objectAdmin`).
  - **Gotcha**: If the connection service account only has `roles/storage.objectAdmin`, streaming ingestion will fail with:
    ```
    PERMISSION_DENIED: Streaming is not available since connection <conn> does not have permissions storage.buckets.get to GCS bucket <bucket>. Please grant permissions of the GCS bucket to the connection's service account ID via IAM.
    ```
  - **Resolution**:
    ```bash
    gcloud storage buckets add-iam-policy-binding gs://<bucket_name> \
      --member="serviceAccount:<connection_service_account>" \
      --role="roles/storage.admin"
    ```

### B. `auto.create.tables` & `auto.update.schemas` Prohibited for STRING Format
- When `input.data.format` is set to `STRING` or `JSON`, Confluent Cloud explicitly rejects the configuration if `auto.create.tables` or `auto.update.schemas` is enabled:
  ```
  auto.update.schemas does not support JSON or STRING message formats
  ```
- **Rule**: Target tables must be pre-created in BigQuery before deploying the connector.

### C. BigQuery Metadata Propagation Race Condition
- When a table is dropped and recreated in BigQuery, the Storage Write API worker endpoint may cache the old table ID or report:
  ```
  Received "Requested entity not found" while writing to BigQuery table ...
  ```
- **Rule**: Wait at least 15–30 seconds after creating BigQuery tables before deploying/starting the connector. Confluent Cloud's auto-restart feature (`enable.connector.auto.restart = true`) will automatically recover once metadata propagates.

### D. Naming & Hyphens: `sanitize.topics` vs `topic2table.map`
- Kafka topics frequently use hyphens (e.g., `blip-command`, `msging-http-request`), whereas BigQuery standard naming prefers underscores (`blip_command`).
- While `sanitize.topics = true` replaces hyphens with underscores, explicitly specifying `topic2table.map` provides deterministic, unambiguous routing:
  ```json
  "topic2table.map": "blip-command:blip_command,blip-session:blip_session"
  ```

### E. In-Place Connector Upgrades vs Offset Rewind Pitfalls
- **Offset Preservation**: Deploying configuration updates to an existing connector via REST API (`PUT /config`) **PRESERVES** the existing consumer group offsets (`connect-<CONNECTOR_NAME>`). The connector reloads tasks and continues streaming from the current offset with the new SMTs applied immediately.
- **The `auto.offset.reset` Gotcha**: Changing `consumer.override.auto.offset.reset` to `earliest` on an existing connector does **NOT** rewind offsets. Kafka only evaluates `auto.offset.reset` if there are no committed offsets in the consumer group or if the committed offsets are out of range.
- **The Rewind Antipattern**: Deleting a connector and recreating it under a new name (or forcefully rewinding offsets via `kafka-consumer-groups --reset-offsets`) causes the connector to re-ingest all messages within Kafka retention (e.g. 36 hours to 7 days). For high-throughput platforms (tens of billions of rows), this triggers:
  1. Massive Storage Write API write storms and quota exhaustion.
  2. Substantial cloud compute and storage costs.
  3. High downstream latency and duplicated records requiring complex deduplication.
- **The Golden Rule**: For existing production pipelines, **always update connector configs in-place** for real-time traffic, and remediate historical data via **partition-scoped BigQuery physical updates**.

### F. BigQuery Streaming Buffer Lock & DML Restrictions
- When data streams into BigQuery via Storage Write API, recently arrived records enter the streaming buffer (typically lingering for 30 to 90 minutes before being flushed to persistent storage).
- Attempting a global `UPDATE` on the table:
  ```sql
  -- ANTIPATTERN (FAILS ON STREAMING TABLES)
  UPDATE `<project>.<dataset>.<table>`
  SET _meta_source_signature = 'caramelo'
  WHERE _meta_source_signature IS NULL;
  ```
  Fails immediately with:
  ```
  UPDATE or DELETE statement over table <project>.<dataset>.<table> would affect rows in the streaming buffer, which is not supported.
  ```
- **The Partition Pruning Solution**: BigQuery permits DML statements on streaming tables **only if the query prunes the scan strictly to closed historical partitions** that contain no active streaming buffers:
  ```sql
  -- SAFE PRODUCTION PATTERN (DAY-BY-DAY PRUNED)
  UPDATE `<project>.<dataset>.<table>`
  SET _meta_source_signature = @signature
  WHERE DATE(_meta_enqueued_time) = @partition_date
    AND _meta_source_signature IS NULL;
  ```

---

## 3. BigLake Apache Iceberg Target Table Schema

Pre-create each target table in BigQuery with the exact schema matching the SMT pipeline.

### For BigLake Managed Apache Iceberg:
```sql
CREATE OR REPLACE TABLE `<project_id>.<dataset_id>.<table_name>` (
  data STRING OPTIONS(description="Raw message payload string/JSON"),
  messageKey STRING OPTIONS(description="Kafka message key"),
  _meta_partition_id STRING OPTIONS(description="Kafka partition number as string"),
  _meta_sequence_number INT64 OPTIONS(description="Kafka record offset"),
  _meta_enqueued_time TIMESTAMP OPTIONS(description="Kafka record timestamp"),
  _meta_ingestion_time TIMESTAMP OPTIONS(description="Pipeline ingestion timestamp"),
  _meta_source_signature STRING OPTIONS(description="Source signature / tenant identifier"),
  _meta_namespace STRING OPTIONS(description="Kafka topic name")
)
PARTITION BY DATE(_meta_enqueued_time)
CLUSTER BY _meta_namespace, _meta_partition_id
WITH CONNECTION `<project_id>.<region>.<connection_id>`
OPTIONS (
  table_format = 'ICEBERG',
  file_format = 'PARQUET',
  storage_uri = 'gs://<lakehouse_bucket>/<table_name>'
);
```

### For Native BigQuery Tables:
```sql
CREATE TABLE IF NOT EXISTS `<project_id>.<dataset_id>.<table_name>` (
  data STRING OPTIONS(description="Raw message payload string/JSON"),
  messageKey STRING OPTIONS(description="Kafka message key"),
  _meta_partition_id STRING OPTIONS(description="Kafka partition number as string"),
  _meta_sequence_number INT64 OPTIONS(description="Kafka record offset"),
  _meta_enqueued_time TIMESTAMP OPTIONS(description="Kafka record timestamp"),
  _meta_ingestion_time TIMESTAMP OPTIONS(description="Pipeline ingestion timestamp"),
  _meta_source_signature STRING OPTIONS(description="Source signature / tenant identifier"),
  _meta_namespace STRING OPTIONS(description="Kafka topic name")
)
PARTITION BY DATE(_meta_enqueued_time)
CLUSTER BY _meta_namespace, _meta_partition_id;
```

---

## 4. Single Message Transform (SMT) Pipeline

To convert raw string/JSON payloads into structured BigQuery rows with audit metadata and static tenant signatures without running intermediate stream transformations, chain these five SMTs:

| Transform Alias | SMT Class | Action |
| :--- | :--- | :--- |
| **`hoist`** | `org.apache.kafka.connect.transforms.HoistField$Value` | Wraps raw string payload into Struct with field name `data` |
| **`insertMeta1`** | `org.apache.kafka.connect.transforms.InsertField$Value` | Extracts Kafka header/envelope metadata (`offset`, `partition`, `timestamp`, `topic`, `key`) |
| **`insertMeta2`** | `org.apache.kafka.connect.transforms.InsertField$Value` | Duplicates record timestamp into `_meta_ingestion_time` |
| **`insertSignature`** | `org.apache.kafka.connect.transforms.InsertField$Value` | Injects static string constant into `_meta_source_signature` |
| **`cast`** | `org.apache.kafka.connect.transforms.Cast$Value` | Casts `_meta_partition_id` from int32 to `string` to match BigQuery clustering schema |

### SMT JSON Configuration:
```json
{
  "transforms": "hoist,insertMeta1,insertMeta2,insertSignature,cast",
  "transforms.hoist.type": "org.apache.kafka.connect.transforms.HoistField$Value",
  "transforms.hoist.field": "data",
  "transforms.insertMeta1.type": "org.apache.kafka.connect.transforms.InsertField$Value",
  "transforms.insertMeta1.offset.field": "_meta_sequence_number",
  "transforms.insertMeta1.partition.field": "_meta_partition_id",
  "transforms.insertMeta1.timestamp.field": "_meta_enqueued_time",
  "transforms.insertMeta1.topic.field": "_meta_namespace",
  "transforms.insertMeta1.key.field": "messageKey",
  "transforms.insertMeta2.type": "org.apache.kafka.connect.transforms.InsertField$Value",
  "transforms.insertMeta2.timestamp.field": "_meta_ingestion_time",
  "transforms.insertSignature.type": "org.apache.kafka.connect.transforms.InsertField$Value",
  "transforms.insertSignature.static.field": "_meta_source_signature",
  "transforms.insertSignature.static.value": "caramelo",
  "transforms.cast.type": "org.apache.kafka.connect.transforms.Cast$Value",
  "transforms.cast.spec": "_meta_partition_id:string"
}
```

> [!IMPORTANT]
> The order of `transforms` matters: `hoist` must execute first so the payload is a Struct. `insertSignature` must execute before `cast` or before connector output emission.

---

## 5. Complete Production Connector Configuration Template

Deploy via Confluent Cloud Connect REST API:
`PUT https://api.confluent.cloud/connect/v1/environments/<ENV_ID>/clusters/<CLUSTER_ID>/connectors/<CONNECTOR_NAME>/config`

```json
{
  "name": "gcp_bq_sink_tenant_caramelo",
  "config": {
    "name": "gcp_bq_sink_tenant_caramelo",
    "connector.class": "BigQueryStorageSink",
    "tasks.max": "2",
    "topics": "caramelo-command,caramelo-httprequest,caramelo-httpresponse,caramelo-session,caramelo-transport",
    "input.data.format": "STRING",
    "consumer.override.auto.offset.reset": "latest",
    "kafka.auth.mode": "KAFKA_API_KEY",
    "kafka.api.key": "<CONFLUENT_CLUSTER_API_KEY>",
    "kafka.api.secret": "<CONFLUENT_CLUSTER_API_SECRET>",
    "authentication.method": "Google service account impersonation",
    "provider.integration.id": "cspi-1q80j",
    "project": "blip-dpl-prd-sam-i-plt-str-0",
    "datasets": "raw_platform_kfkconn",
    "ingestion.mode": "STREAMING",
    "sanitize.topics": "true",
    "enable.connector.auto.restart": "true",
    "topic2table.map": "caramelo-command:imt_command,caramelo-httprequest:imt_httprequest,caramelo-httpresponse:imt_httpresponse,caramelo-session:imt_session,caramelo-transport:imt_transport",
    "transforms": "hoist,insertMeta1,insertMeta2,insertSignature,cast",
    "transforms.hoist.type": "org.apache.kafka.connect.transforms.HoistField$Value",
    "transforms.hoist.field": "data",
    "transforms.insertMeta1.type": "org.apache.kafka.connect.transforms.InsertField$Value",
    "transforms.insertMeta1.offset.field": "_meta_sequence_number",
    "transforms.insertMeta1.partition.field": "_meta_partition_id",
    "transforms.insertMeta1.timestamp.field": "_meta_enqueued_time",
    "transforms.insertMeta1.topic.field": "_meta_namespace",
    "transforms.insertMeta1.key.field": "messageKey",
    "transforms.insertMeta2.type": "org.apache.kafka.connect.transforms.InsertField$Value",
    "transforms.insertMeta2.timestamp.field": "_meta_ingestion_time",
    "transforms.insertSignature.type": "org.apache.kafka.connect.transforms.InsertField$Value",
    "transforms.insertSignature.static.field": "_meta_source_signature",
    "transforms.insertSignature.static.value": "caramelo",
    "transforms.cast.type": "org.apache.kafka.connect.transforms.Cast$Value",
    "transforms.cast.spec": "_meta_partition_id:string"
  }
}
```

---

## 6. Zero-Downtime Deployment & In-Place Rollout Automation

Create a secure rollout script (`connectors/deploy_connectors.sh`) that sources credentials from `.env` and updates connector configurations in-place via the REST API:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Load credentials from .env if present
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

ENV_ID="${CONFLUENT_ENV_ID:-env-m62nqq}"
CLUSTER_ID="${CONFLUENT_CLUSTER_ID:-lkc-m1wog7}"
CONFLUENT_CLOUD_API_KEY="${CONFLUENT_CLOUD_API_KEY:-}"
CONFLUENT_CLOUD_API_SECRET="${CONFLUENT_CLOUD_API_SECRET:-}"
KAFKA_API_KEY="${KAFKA_API_KEY:-}"
KAFKA_API_SECRET="${KAFKA_API_SECRET:-}"

if [[ -z "${CONFLUENT_CLOUD_API_KEY}" || -z "${CONFLUENT_CLOUD_API_SECRET}" ]]; then
  echo "ERRO: CONFLUENT_CLOUD_API_KEY e CONFLUENT_CLOUD_API_SECRET devem ser exportadas."
  exit 1
fi

CONNECTORS=(
  "gcp_bq_sink_tenant_caramelo.json:gcp_bq_sink_tenant_caramelo"
  "gcp_bq_sink_tenant_husky.json:gcp_bq_sink_tenant_husky"
  "gcp_bq_sink_platform_core_blip.json:gcp_bq_sink_platform_core_blip"
)

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for item in "${CONNECTORS[@]}"; do
  FILE="${item%%:*}"
  NAME="${item##*:}"
  FILEPATH="$BASE_DIR/$FILE"
  
  echo "[-] Deploying connector $NAME in-place ($FILE)..."
  
  CONFIG_PAYLOAD=$(jq \
    --arg kkey "${KAFKA_API_KEY}" \
    --arg ksec "${KAFKA_API_SECRET}" \
    '.config | (if $kkey != "" then .["kafka.api.key"] = $kkey else . end) | (if $ksec != "" then .["kafka.api.secret"] = $ksec else . end)' \
    "$FILEPATH")
  
  HTTP_CODE=$(curl -s -o /tmp/connect_response.json -w "%{http_code}" \
    -X PUT \
    -H "Content-Type: application/json" \
    -u "$CONFLUENT_CLOUD_API_KEY:$CONFLUENT_CLOUD_API_SECRET" \
    "https://api.confluent.cloud/connect/v1/environments/$ENV_ID/clusters/$CLUSTER_ID/connectors/$NAME/config" \
    -d "$CONFIG_PAYLOAD")
    
  if [[ "$HTTP_CODE" =~ ^(200|201|202)$ ]]; then
    echo "    [OK] Connector $NAME deployed successfully (HTTP $HTTP_CODE)."
  else
    echo "    [FAIL] Failed to deploy $NAME (HTTP $HTTP_CODE)."
    cat /tmp/connect_response.json; echo ""
    exit 1
  fi
done
```

---

## 7. Automated Partitioned Historical Backfill Pattern (Zero Data Loss DML)

To populate `_meta_source_signature` for records ingested prior to the SMT upgrade without hitting streaming buffer locks, execute day-by-day partition updates with strict pre/post row count parity assertion:

```python
#!/usr/bin/env python3
"""
Automated, idempotent day-by-day partitioned backfill for _meta_source_signature.
Bypasses BigQuery streaming buffer lock on BigLake Managed Apache Iceberg tables.
"""
import os
import sys
import logging
from datetime import date, timedelta
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Target partition range: from start of migration up to yesterday
START_DATE = date(2026, 9, 4)
END_DATE = date.today() - timedelta(days=1)

PROJECT_ID = "blip-dpl-prd-sam-i-plt-str-0"
DATASET_ID = "raw_platform_kfkconn"

TABLE_SIGNATURE_MAPPINGS = {
    # Tenant specific tables
    "imt_caramelo_message": "caramelo",
    "imt_husky_message": "husky",
    # Platform core tables
    "imt_blip_command": "blip",
    "imt_msging_message": "msging",
}

def backfill_table_partition(client, project, dataset, table, partition_date_str, signature):
    full_table = f"{project}.{dataset}.{table}"
    
    # 1. Pre-update audit
    audit_sql = f"""
    SELECT
      COUNT(1) as total_rows,
      COUNTIF(_meta_source_signature IS NULL) as null_sig_rows
    FROM `{full_table}`
    WHERE DATE(_meta_enqueued_time) = '{partition_date_str}'
    """
    res = list(client.query(audit_sql).result())[0]
    total_pre, null_pre = res.total_rows, res.null_sig_rows
    
    if total_pre == 0 or null_pre == 0:
        logging.info(f"[{table}] Partition {partition_date_str}: nothing to update (Total: {total_pre}, Nulls: {null_pre})")
        return {"status": "SKIPPED", "total_rows": total_pre}

    # 2. Partition-scoped UPDATE (Idempotent, strictly pruned)
    update_sql = f"""
    UPDATE `{full_table}`
    SET _meta_source_signature = '{signature}'
    WHERE DATE(_meta_enqueued_time) = '{partition_date_str}'
      AND _meta_source_signature IS NULL
    """
    job = client.query(update_sql)
    job.result()
    rows_affected = job.num_dml_affected_rows

    # 3. Post-update verification & parity check
    post_res = list(client.query(audit_sql).result())[0]
    total_post, null_post = post_res.total_rows, post_res.null_sig_rows

    if total_pre != total_post or null_post != 0:
        raise ValueError(
            f"Parity mismatch in {full_table} partition {partition_date_str}! "
            f"Pre: {total_pre}, Post: {total_post}, Remaining Nulls: {null_post}"
        )

    logging.info(f"[{table}] Partition {partition_date_str}: Updated {rows_affected}/{total_post} rows. Parity: 100% OK.")
    return {"status": "UPDATED", "rows_affected": rows_affected, "total_rows": total_post}
```

---

## 8. Post-Backfill Integrity Audit & Parity Verification

### A. Check Connector Status via REST API:
```bash
curl -s -u "$CONFLUENT_CLOUD_API_KEY:$CONFLUENT_CLOUD_API_SECRET" \
  "https://api.confluent.cloud/connect/v1/environments/$ENV_ID/clusters/$CLUSTER_ID/connectors/$NAME/status" | jq .
```
Verify:
- `connector.state == "RUNNING"`
- All tasks report `state == "RUNNING"`

### B. Real-Time Streaming Verification:
Verify incoming records show the newly injected signature in BigQuery:
```sql
SELECT 
  _meta_source_signature,
  _meta_namespace,
  _meta_partition_id,
  _meta_sequence_number,
  _meta_enqueued_time,
  SUBSTR(data, 1, 60) as payload_preview
FROM `<PROJECT_ID>.<DATASET_ID>.<TABLE_NAME>`
ORDER BY _meta_enqueued_time DESC
LIMIT 10;
```

### C. Dataset-Wide Audit for Unpopulated Signatures:
Run across all tables to guarantee complete historical parity:
```sql
SELECT 
  _meta_source_signature, 
  DATE(_meta_enqueued_time) as partition_date,
  COUNT(1) as record_count
FROM `<PROJECT_ID>.<DATASET_ID>.<TABLE_NAME>`
WHERE DATE(_meta_enqueued_time) < CURRENT_DATE()
GROUP BY 1, 2
ORDER BY partition_date DESC;
```
Verify that `_meta_source_signature IS NULL` returns **0 records**.
