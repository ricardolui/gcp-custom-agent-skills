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

---

## ⚡ GOLDEN RULE: Timestamp Alignment & Partition Pre-Filtering

### 1. Why `_meta_enqueued_time` $\neq$ Databricks `StorageDate`
- In **Databricks (`bliplayer.raw.*`, `rawcoreblip.blipraw.*`)**, tables do NOT filter by broker arrival time; they filter by **`StorageDate`** (or `StorageDateBR`), which is extracted from the application JSON payload (`$.StorageDate`, `$.storageDate`, or `$.timestamp`).
- In **BigQuery (`raw_*_kfkevh.imt_*`)**, tables are physically partitioned by **`DATE(_meta_enqueued_time)`** (the Kafka/EventHub broker publish time in UTC).
- Because broker ingestion can lag application `StorageDate` by milliseconds to minutes, comparing Databricks `StorageDate` against BigQuery `_meta_enqueued_time` creates artificial boundary drift at the edges of each hour.
- **Empirical Proof:** When filtering both Databricks (`StorageDate`) and BigQuery (`JSON_VALUE(data, '$.StorageDate')`) over `'2026-09-16 14:00:00'` to `'2026-09-16 15:00:00'` for `evhns-msging-server3-prd-dalmata-003`, **both return 28,720,517 rows (100.000000% exact match to the single row)**.

### 2. Mandatory Partition Pre-Filtering (Cost Protection & Timezone Rules)
Because `JSON_VALUE(data, '$.StorageDate')` cannot prune BigQuery partitions, **every BigQuery parity query MUST apply a two-tier filter**:
1. **Partition Pruning Envelope (`_meta_enqueued_time` in UTC):** Always pre-filter `_meta_enqueued_time` with a **$\pm 4\text{ hours}$ safety buffer** around the target `StorageDate` window:
   ```sql
   WHERE _meta_enqueued_time >= TIMESTAMP_SUB(TIMESTAMP('2026-09-16 14:00:00 UTC'), INTERVAL 4 HOUR)
     AND _meta_enqueued_time <= TIMESTAMP_ADD(TIMESTAMP('2026-09-16 15:00:00 UTC'), INTERVAL 4 HOUR)
   ```
   This guarantees BigQuery scans only the relevant daily/hourly partitions and keeps query costs minimal.
2. **Payload Timestamp Exact Filter (`StorageDate` in UTC):** Filter and group by the extracted payload timestamp:
   ```sql
   AND COALESCE(
     SAFE_CAST(JSON_VALUE(data, '$.StorageDate') AS TIMESTAMP),
     SAFE_CAST(JSON_VALUE(data, '$.storageDate') AS TIMESTAMP),
     SAFE_CAST(JSON_VALUE(data, '$.timestamp') AS TIMESTAMP)
   ) BETWEEN TIMESTAMP('2026-09-16 14:00:00 UTC') AND TIMESTAMP('2026-09-16 15:00:00 UTC')
   ```
3. **Databricks Partition Pruning (`StorageDateDayBR` in UTC-3):** In Databricks, `StorageDateDayBR` is formatted as `'yyyy-MM-dd'` in **Brasília time (UTC-3)**. Always include `WHERE StorageDateDayBR IN (...)` covering the UTC-3 dates corresponding to your UTC window.

---

## 🔑 Canonical `_kfkevh` Deduplication Contract

Legacy tables (`_pubsub`) relied on `messageKey` (which is removed in `_kfkevh`). In the new unified **`raw_*_kfkevh.imt_*`** architecture, technical deduplication **MUST** always use the 3-column composite key:
- **`_meta_namespace`** (Kafka topic or EventHub namespace)
- **`_meta_partition_id`** (Partition ID string)
- **`_meta_sequence_number`** (Kafka offset string or 64-bit Pub/Sub `message_id` string)

### Canonical BigQuery Query Template (`_kfkevh` Deduplicated + Timestamp Aligned)

```sql
WITH pruned_and_deduped AS (
  SELECT
    _meta_namespace,
    _meta_partition_id,
    _meta_sequence_number,
    _meta_enqueued_time,
    COALESCE(
      SAFE_CAST(JSON_VALUE(data, '$.StorageDate') AS TIMESTAMP),
      SAFE_CAST(JSON_VALUE(data, '$.storageDate') AS TIMESTAMP),
      SAFE_CAST(JSON_VALUE(data, '$.timestamp') AS TIMESTAMP),
      _meta_enqueued_time
    ) AS storage_date_utc,
    COALESCE(
      JSON_VALUE(data, '$.Ticket.id'),
      JSON_VALUE(data, '$.Id'),
      JSON_VALUE(data, '$.id')
    ) AS business_id
  FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_notifications`
  -- 1. MANDATORY PARTITION PRUNING ENVELOPE (UTC +/- 4 hours)
  WHERE _meta_enqueued_time >= TIMESTAMP_SUB(TIMESTAMP('2026-09-16 14:00:00 UTC'), INTERVAL 4 HOUR)
    AND _meta_enqueued_time <= TIMESTAMP_ADD(TIMESTAMP('2026-09-16 15:00:00 UTC'), INTERVAL 4 HOUR)
    AND _meta_namespace = 'evhns-msging-server3-prd-dalmata-003'
  -- 2. CANONICAL _kfkevh 3-COLUMN DEDUPLICATION
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY _meta_namespace, _meta_partition_id, _meta_sequence_number
    ORDER BY _meta_enqueued_time DESC
  ) = 1
)
SELECT
  _meta_namespace AS nameSpace,
  FORMAT_TIMESTAMP('%Y-%m-%d %H:00', TIMESTAMP_TRUNC(storage_date_utc, HOUR)) AS hour_utc,
  COUNT(*) AS bq_dedup_rows,
  COUNT(DISTINCT business_id) AS bq_unique_ids
FROM pruned_and_deduped
-- 3. EXACT PAYLOAD TIMESTAMP ALIGNMENT WITH DATABRICKS StorageDate
WHERE storage_date_utc BETWEEN TIMESTAMP('2026-09-16 14:00:00 UTC') AND TIMESTAMP('2026-09-16 15:00:00 UTC')
GROUP BY 1, 2
ORDER BY 2 DESC;
```

### Canonical Databricks Query Template (`Spark SQL` Equivalent)

```sql
SELECT
  nameSpace,
  DATE_FORMAT(DATE_TRUNC('HOUR', StorageDate), 'yyyy-MM-dd HH:00') AS hour_utc,
  COUNT(*) AS dbx_rows,
  COUNT(DISTINCT Id) AS dbx_unique_ids
FROM bliplayer.raw.notifications
-- 1. MANDATORY PARTITION PRUNING (UTC-3 Date String)
WHERE StorageDateDayBR IN ('2026-09-16', '2026-09-17')
  -- 2. EXACT PAYLOAD TIMESTAMP WINDOW
  AND StorageDate BETWEEN TIMESTAMP('2026-09-16 14:00:00') AND TIMESTAMP('2026-09-16 15:00:00')
  AND nameSpace = 'evhns-msging-server3-prd-dalmata-003'
GROUP BY 1, 2
ORDER BY 2 DESC;
```

---

## 🗺️ Canonical Mapping Matrix: BigQuery `_kfkevh` $\leftrightarrow$ Databricks Unity Catalog

👉 **O mapeamento completo e detalhado das 61 tabelas canônicas (`str-0` e `shs-0`) está persistido e governado em:**
- **Markdown Oficial (61 Tabelas por Domínio)**: `orchestration/reports/kfkevh_parity/CANONICAL_61_KFKEVH_TO_DATABRICKS_MAPPING.md`
- **Catálogo Estruturado JSON**: `orchestration/reports/kfkevh_parity/canonical_61_kfkevh_to_databricks_mapping.json`

### Resumo das Principais Tabelas Core (`str-0` Padrão vs. `shs-0` Shiba Segregado):

> [!IMPORTANT]
> **Segregação Arquitetural Estrita do Tenant Shiba (`shs-0` $\leftrightarrow$ `bliplayer_shiba`):**
> - No **GCP (Terraform `migracao_ingestao_v2/01_terraform/environments/sam/kfkevh_datasets_and_tables.tf`)**, as 18 tabelas canônicas do Shiba (`imt_*_shiba` em `raw_platform_kfkevh` e `imt_llmserverrequests_shiba` em `raw_blipaisuite_kfkevh`) residem **exclusivamente no projeto segregado `blip-dpl-prd-sam-i-plt-shs-0`** (nunca em `blip-dpl-prd-sam-i-plt-str-0`).
> - No **Azure Databricks Unity Catalog (`scripts/generate_61_mapping_and_3h_matrix.py`)**, as tabelas do Shiba não residem no catálogo padrão `bliplayer` / `rawcoreblip`, mas sim no catálogo segregado **`bliplayer_shiba`** (`bliplayer_shiba.raw.*` e `bliplayer_shiba.shibablipraw.*`).
> - Os 4 conectores canônicos `gcp_bq_sink_sam_shiba_01..04` (`tasks.max = 1`) gravam diretamente em `project = blip-dpl-prd-sam-i-plt-shs-0`, `datasets = raw_platform_kfkevh` com zero tabelas intermediárias.

| Entity | BigQuery `_kfkevh` Bronze Table (`str-0` / `shs-0`) | Payload Timestamp JSON Path | Databricks Unity Catalog Table | Databricks Timestamp & Partition Columns |
| :--- | :--- | :--- | :--- | :--- |
| **Notifications (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_notifications` | `$.StorageDate` / `$.timestamp` | `bliplayer.raw.notifications` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Messages (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_messages` | `$.StorageDate` / `$.timestamp` | `bliplayer.raw.messages` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Tickets** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_tickets` | `$.Ticket.storageDate` / `$.DateTime` | `rawcoreblip.blipraw.tickets` | `storageDate` / `enqueuedTime` (Part: `StorageDateDayBR`) |
| **Commands (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_commands` | `$.StorageDate` / `$.timestamp` | `bliplayer.raw.commands` | `StorageDate` / `EventEnqueuedUtcTime` (Part: `StorageDateDayBR`) |
| **Session (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_session` | `$.StorageDate` / `$.timestamp` | `rawcoreblip.blipraw.session` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Transport (Core)** | `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkevh.imt_transport` | `$.StorageDate` / `$.timestamp` | `rawcoreblip.blipraw.transport` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Notifications (Shiba)** | `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_notifications_shiba` | `$.StorageDate` / `$.timestamp` | `bliplayer_shiba.raw.notifications` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Messages (Shiba)** | `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_messages_shiba` | `$.StorageDate` / `$.timestamp` | `bliplayer_shiba.raw.messages` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Commands (Shiba)** | `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_commands_shiba` | `$.StorageDate` / `$.timestamp` | `bliplayer_shiba.raw.commands` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Session (Shiba)** | `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_session_shiba` | `$.StorageDate` / `$.timestamp` | `bliplayer_shiba.shibablipraw.session` | `StorageDate` (Part: `StorageDateDayBR`) |
| **Transport (Shiba)** | `blip-dpl-prd-sam-i-plt-shs-0.raw_platform_kfkevh.imt_transport_shiba` | `$.StorageDate` / `$.timestamp` | `bliplayer_shiba.shibablipraw.transport` | `StorageDate` (Part: `StorageDateDayBR`) |

---

## 🛠️ CLI Tools & Automated Matrix Runners

1. **Multi-Table 3-Hour Comparative Matrix Generator (`scripts/generate_61_mapping_and_3h_matrix.py`)**:
   Gera o dashboard comparativo quebrado por hora (`H-3`, `H-2`, `H-1`) + **Soma Total de N Horas (`Soma 3h BQ` vs `Soma 3h DBX`)** e salva em `orchestration/reports/kfkevh_parity/matrix_3h_comparative_dashboard.md`:
   ```bash
   CLOUDSDK_ACTIVE_CONFIG_NAME=blip CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski \
     python3 scripts/generate_61_mapping_and_3h_matrix.py \
     --mode hybrid \
     --start-utc "2026-09-16 13:00:00" \
     --hours 3 \
     --sample-tables "imt_notifications,imt_tickets"
   ```
2. **Direct SQL Runner (`scripts/dbx_sql.py`)**:
   ```bash
   python3 scripts/dbx_sql.py "SELECT nameSpace, COUNT(*) FROM bliplayer.raw.notifications WHERE StorageDateDayBR = '2026-09-16' AND StorageDate BETWEEN '2026-09-16 14:00:00' AND '2026-09-16 15:00:00' GROUP BY 1"
   ```
3. **Single-Entity Deep Auditor (`orchestration/scripts/audit_kfkevh_vs_databricks.py`)**:
   ```bash
   python3 orchestration/scripts/audit_kfkevh_vs_databricks.py --only notifications --start "2026-09-16 13:00:00" --end "2026-09-16 16:00:00" --namespace "evhns-msging-server3-prd-dalmata-003"
   ```
