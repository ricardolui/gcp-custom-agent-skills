---
name: databricks-bq-parity-checker
description: Use when auditing, validating, or reconciling data parity between Google Cloud BigQuery (_kfkevh Bronze or Silver tables) and Azure Databricks Unity Catalog tables, or executing SQL queries against Databricks from the CLI.
---

# Databricks vs. BigQuery (`_kfkevh`) Parity Checker & SQL Runner

Operational guide, Unity Catalog mapping reference, and CLI tooling for executing direct SQL queries on Azure Databricks and performing automated hourly parity reconciliation between BigQuery BigLake Apache Iceberg Managed Tables (`raw_*_kfkevh.imt_*` / `silver_*`) and Databricks Unity Catalog tables.

---

## 🔐 Authentication & Configuration (Zero-PAT OAuth2)

Personal Access Tokens (PATs) are disabled by Blip organization policy. Authentication uses **OAuth2 User-to-Machine (U2M)** via the official Databricks CLI (`~/.local/bin/databricks`) and `databricks-sdk`.

- **Host:** `https://adb-1974038730385138.18.azuredatabricks.net`
- **Profile:** `DEFAULT` (stored in `~/.databrickscfg` with automatic OAuth token refresh via `~/.databricks/token-cache.json`)
- **Default Serverless SQL Warehouse ID:** `0a78d10918dd0e80` (`dataplatform_dev_warehouse`)

### Re-authenticating (if OAuth session expires)
If queries return `401 Unauthorized` or token expiration errors, re-run:
```bash
PATH="/tmp/bin:$PATH" ~/.local/bin/databricks auth login \
  --host https://adb-1974038730385138.18.azuredatabricks.net \
  --profile DEFAULT
```

---

## 🛠️ Executing Direct SQL Queries on Databricks

Use the standalone CLI tool [`scripts/dbx_sql.py`](file:///usr/local/google/home/gricardo/blip-migration/scripts/dbx_sql.py) to run any query against Databricks Unity Catalog:

```bash
# Markdown Table Output (Default)
python3 scripts/dbx_sql.py "SELECT current_catalog(), current_user()"

# JSON Output (for programmatic comparison)
python3 scripts/dbx_sql.py --format json "SHOW TABLES IN rawcoreblip.blipraw"

# Execute SQL from a file
python3 scripts/dbx_sql.py --file my_query.sql --format csv
```

---

## 🗺️ Canonical Mapping Matrix: BigQuery `_kfkevh` $\leftrightarrow$ Databricks Unity Catalog

When auditing streaming ingestion in SAM (`southamerica-east1`), use the following canonical table mappings:

| Entity | BigQuery `_kfkevh` Bronze Table (`str-0` / `shs-0`) | BigQuery Business Key Expression | Databricks Unity Catalog Table | Databricks Timestamp / Partition Column |
| :--- | :--- | :--- | :--- | :--- |
| **Tickets** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_tickets` | `JSON_VALUE(data, '$.id')` | `rawcoreblip.blipraw.tickets` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Messages (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_messages` | `JSON_VALUE(data, '$.id')` | `bliplayer.raw.messages` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Notifications (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_notifications` | `JSON_VALUE(data, '$.id')` | `bliplayer.raw.notifications` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Commands (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_commands` | `JSON_VALUE(data, '$.id')` | `rawcoreblip.blipraw.commands` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Session (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_session` | `JSON_VALUE(data, '$.id')` | `rawcoreblip.blipraw.session` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Transport (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_transport` | `JSON_VALUE(data, '$.id')` | `rawcoreblip.blipraw.transport` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Messages (Shiba)** | `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_messages_shiba` | `JSON_VALUE(data, '$.id')` | `bliplayer_shiba.raw.messages` | `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Notifications (Shiba)**| `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_notifications_shiba`| `JSON_VALUE(data, '$.id')` | `bliplayer_shiba.raw.notifications` | `enqueuedTime` (Part: `StorageDateDayBR`) |

> [!IMPORTANT]
> **Full Lineage Reference:** For all 199 canonical Silver/Gold tables and column-level lineage, inspect [`docs/Assessment/global_data_model.json`](file:///usr/local/google/home/gricardo/blip-migration/docs/Assessment/global_data_model.json) (`legacy_lineage` field) and [`docs/[Blip] Mapeamento.csv`](file:///usr/local/google/home/gricardo/blip-migration/docs/%5BBlip%5D%20Mapeamento.csv).

---

## ⚖️ Methodology: Comparing Deduplicated `_kfkevh` vs. Databricks

BigQuery `_kfkevh` Bronze tables receive **at-least-once** streaming appends from Confluent Kafka Connect and Google Cloud Pub/Sub Import. Downstream Dataform (`02_staging/`) applies deterministic technical deduplication before loading Silver.

To perform a fair 1:1 parity check against Databricks over closed hourly windows:

### 1. BigQuery Deduplicated Aggregation Query (`GoogleSQL`)
Always apply the exact Dataform staging deduplication window (`QUALIFY ROW_NUMBER()`) and exclude the currently open hour:

```sql
WITH deduped AS (
  SELECT
    _meta_enqueued_time,
    _meta_namespace,
    _meta_source_signature,
    JSON_VALUE(data, '$.id') AS business_id
  FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_tickets`
  WHERE _meta_enqueued_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 12 HOUR)
    AND _meta_enqueued_time < TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), HOUR)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY _meta_namespace, _meta_partition_id, _meta_sequence_number
    ORDER BY _meta_enqueued_time DESC
  ) = 1
)
SELECT
  FORMAT_TIMESTAMP('%Y-%m-%d %H:00', TIMESTAMP_TRUNC(_meta_enqueued_time, HOUR)) AS hour_utc,
  COUNT(*) AS bq_dedup_rows,
  COUNT(DISTINCT business_id) AS bq_unique_keys
FROM deduped
GROUP BY 1
ORDER BY 1 DESC;
```

### 2. Databricks Aggregation Query (`Spark SQL`)
Filter by partition (`StorageDateDayBR`) for partition pruning and truncate `enqueuedTime` to UTC hours:

```sql
SELECT
  DATE_FORMAT(DATE_TRUNC('HOUR', enqueuedTime), 'yyyy-MM-dd HH:00') AS hour_utc,
  COUNT(*) AS dbx_total_rows,
  COUNT(DISTINCT id) AS dbx_unique_keys
FROM rawcoreblip.blipraw.tickets
WHERE StorageDateDayBR >= DATE_FORMAT(DATE_SUB(CURRENT_DATE(), 2), 'yyyy-MM-dd')
  AND enqueuedTime >= TIMESTAMPADD(HOUR, -12, CURRENT_TIMESTAMP())
  AND enqueuedTime < DATE_TRUNC('HOUR', CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;
```

### 3. Automated Comparative Runner
Run the automated cross-cloud parity auditor:
```bash
python3 orchestration/scripts/audit_kfkevh_vs_databricks.py --hours 6
```
