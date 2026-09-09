---
name: blip-composer-dataform-stream-migration
description: Use when migrating streaming ingestion pipelines in Cloud Composer and Dataform from legacy Dataflow jobs to Confluent Kafka direct Iceberg ingestion, deploying pure incremental DAGs, resolving source dataset/table mapping mismatches, validating shadow A/B parity, and draining Dataflow compute.
---

# Blip: Cloud Composer & Dataform Streaming Migration (Dataflow Elimination)

Comprehensive operational guide and architecture patterns for migrating streaming ingestion pipelines from legacy Dataflow jobs (`KafkaToBigQuery` / `EventHubsToBigQuery`) to pure incremental Dataform routines running on Cloud Composer, backed by Confluent Cloud Kafka BigLake Apache Iceberg Managed Tables (`raw_*_kfkconn.imt_*`).

---

## 📌 Architectural Overview & Core Principle

In the legacy Blip architecture, Cloud Composer DAGs launched long-running streaming Dataflow jobs (`DataflowStartFlexTemplateOperator`) before compiling and executing incremental Dataform transformations (`DataformCreateCompilationResultOperator` and `DataformCreateWorkflowInvocationOperator`).

Confluent Cloud Kafka Connect (`gcp_bq_sink_*`) now streams all Kafka topics directly into BigLake Apache Iceberg Managed Tables (`raw_platform_kfkconn.imt_*`, `raw_blipaisuite_kfkconn.imt_*`) in real time.

**Core Principle:**
> **Never keep Dataflow jobs running inside Composer DAGs once Confluent Connect is live.**  
> Dataflow streaming inside the DAG creates duplicate BigQuery Storage Write API ingestion costs ($0.045/GB in `southamerica-east1`) and wastes ~$19k–$21k/month in redundant GCE worker compute. Composer DAGs must be refactored into pure, fast (<30s) incremental Dataform execution routines.

```
LEGACY DAG (Problematic):
[Start] ──> [Check Dataflow Status] ──> [DataflowStartFlexTemplate (Hang/Redundant)] ──> [Dataform Compilation] ──> [Dataform Invocation] ──> [End]

MIGRATED DAG (Clean, Pure Incremental):
[Start Routine] ──> [Dataform Compilation (vars injected)] ──> [Dataform Invocation (tag-scoped)] ──> [End DAG]
```

---

## 🎯 When to Use & When NOT to Use

### Use When:
- Refactoring any of the 58 Confluent Kafka ingestion DAGs in Cloud Composer to eliminate Dataflow operators.
- Parameterizing Dataform source declarations (`definitions/01_sources/`) and staging views (`definitions/02_staging/`) to dynamically switch from `raw_copilot` / `raw_platform` to `raw_platform_kfkconn`.
- Diagnosing and debugging failed Dataform workflow invocations (e.g., `Table raw_platform_kfkconn.<name> not found`).
- Provisioning isolated shadow datasets (`staging__kfkconn_test`, `<silver>__kfkconn_test`) for safe A/B validation without touching production tables.
- Running automated cross-table parity audits (Full Outer Join, row counts, and primary key checks) between production and shadow test tables.
- Preparing for and executing the decommissioning/drain of legacy Dataflow streaming jobs.

### Do NOT Use When:
- Ingesting batch databases (e.g., SQL Server `JdbcToBigQuery`, MongoDB) that still require Dataflow/Dataproc.
- Provisioning brand-new Confluent Cloud Kafka Connect connectors (use `confluent-kafka-bigquery-ingestion`).
- Migrating Azure Event Hubs directly via Google Cloud Pub/Sub (use `blip-pubsub-eventhub-migration`).

---

## ⚡ Quick Reference: The 6-Phase Rollout Lifecycle

| Phase | Action | Key Tool / Asset | Risk Level |
| :--- | :--- | :--- | :---: |
| **1. Source Alignment** | Identify target table in `raw_*_kfkconn`; create compatibility view if SMT prefixed it | BigQuery DDL View | Zero |
| **2. Dataform Refactor** | Parameterize source dataset and staging `ref()`; commit and push feature branch | Dataform REST API | Zero |
| **3. Shadow Datasets** | Create `staging__kfkconn_test` and `<silver>__kfkconn_test` | BigQuery DDL | Zero |
| **4. DAG Refactor** | Strip Dataflow; configure compilation `vars`; upload to Composer bucket | Cloud Composer SA Impersonation | Zero |
| **5. A/B Validation** | Trigger pilot DAG; run parity query against production table | Airflow REST API + BigQuery SQL | Zero |
| **6. Cutover & Drain** | Merge PR to `main`; remove `schema_suffix`; drain legacy Dataflow job | GitHub PR + Dataflow CLI | Low |

---

## 🛠️ Step-by-Step Implementation

### Phase 1: Source Identification & BigQuery Compatibility View

Confluent Cloud Kafka Connect maps topics using Single Message Transforms (SMT). In some cases, platform topics retain prefixes (e.g., `prod-copilot-ticket-end-summary-created` becomes `imt_prod_copilot_ticket_end_summary_created`), whereas the legacy Dataflow pipeline wrote to `raw_copilot.imt_ticket_end_summary_created`.

1. Check active streaming tables in `raw_platform_kfkconn`:
   ```sql
   SELECT table_name, row_count, TIMESTAMP_MILLIS(last_modified_time) AS last_modified
   FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.__TABLES__`
   WHERE table_name LIKE '%<entity_name>%'
   ORDER BY last_modified DESC;
   ```

2. If the table name differs from the legacy Dataform declaration, **create a BigQuery Compatibility View** inside `raw_platform_kfkconn`:
   ```sql
   CREATE OR REPLACE VIEW `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_<entity_name>` AS
   SELECT * FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_prod_<entity_name>`;
   ```
   > [!TIP]
   > Creating a BigQuery view in `raw_platform_kfkconn` guarantees zero code changes to existing downstream Dataform logic and prevents `Table not found` errors.

---

### Phase 2: Dataform Source Parameterization

1. **In `definitions/01_sources/<dataset>/<table_name>.sqlx`:**
   Parameterize the `schema` using project configuration variables:
   ```javascript
   config {
     type: "declaration",
     database: `${utils.projectId("i-plt-str")}`,
     schema: `${dataform.projectConfig.vars.raw_source_dataset || "raw_copilot"}`,
     name: "imt_ticket_end_summary_created",
     description: "Tabela bronze schemaless de streaming."
   }
   ```

2. **In `definitions/02_staging/<silver_domain>/stg_<table_name>.sqlx`:**
   Ensure the `ref()` function uses the dynamic source variable:
   ```sql
   FROM ${ref(dataform.projectConfig.vars.raw_source_dataset || "raw_copilot", "imt_ticket_end_summary_created")}
   ```

3. **In `definitions/03_silver/<silver_domain>/<table_name>.sqlx`:**
   Keep the standard staging reference:
   ```sql
   FROM ${ref("staging", "stg_ticket_end_summary_created")}
   ${utils.incrementalFilterStreaming("_meta_enqueued_time", self(), incremental())}
   ```

4. **Commit & Push to GitHub via Dataform REST API:**
   * Branch naming must follow GitHub repository regex: `feat/kfkconn-<entity>-pilot`
   * Commit payload requires `author.name` and `author.emailAddress`.

---

### Phase 3: Shadow Datasets Provisioning

Before executing any pilot runs, isolate output from production:

```sql
CREATE SCHEMA IF NOT EXISTS `blip-dpl-prd-sam-i-plt-str-0.staging__kfkconn_test`
OPTIONS(location="southamerica-east1");

CREATE SCHEMA IF NOT EXISTS `blip-dpl-prd-sam-i-plt-str-0.silver_copilot__kfkconn_test`
OPTIONS(location="southamerica-east1");
```

---

### Phase 4: Refactoring the Cloud Composer DAG

1. Strip all Dataflow imports and tasks (`DataflowStartFlexTemplateOperator`, `BranchPythonOperator`, `check_dataflow_job_status`).
2. Retain pure Dataform operators:

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup
from airflow.providers.google.cloud.operators.dataform import (
    DataformCreateCompilationResultOperator,
    DataformCreateWorkflowInvocationOperator,
)

default_args = {
    'owner': 'data-engineers',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='ING_EVH_KAFKA_COPILOT_TICKET_END_SUMMARY_CREATED_KFKCONN',
    default_args=default_args,
    schedule_interval='40 0 * * *',
    start_date=datetime(2026, 9, 1),
    catchup=False,
    max_active_runs=1,
    tags=['kfkconn', 'copilot', 'dataform', 'incremental'],
) as dag:

    start_task = EmptyOperator(task_id='start_incremental_routine')
    end_task = EmptyOperator(task_id='end_dag')

    with TaskGroup(group_id='copilot_ticket_end_summary_created_silver') as tg:
        with TaskGroup(group_id='copilot_ticket_end_summary_created_dataform_group') as df_group:
            create_compilation = DataformCreateCompilationResultOperator(
                task_id='create_compilation',
                project_id='blip-dpl-prd-sam-i-plt-str-0',
                region='southamerica-east1',
                repository_id='gcp-dpl-dataform-blip-stream-ingestion',
                compilation_result={
                    "git_commitish": 'feat/kfkconn-copilot-pilot', # Switch to 'main' post-merge
                    "code_compilation_config": {
                        "vars": {
                            "project_id": "blip-dpl-prd-sam-i-plt-str-0",
                            "raw_copilot_dataset": "raw_platform_kfkconn",
                            "schema_suffix": "__kfkconn_test", # Set to "" for official production
                            "REGION": "sam",
                            "ENV": "prd"
                        },
                    },
                },
                impersonation_chain='blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com',
            )

            create_invocation = DataformCreateWorkflowInvocationOperator(
                task_id='create_invocation',
                project_id='blip-dpl-prd-sam-i-plt-str-0',
                region='southamerica-east1',
                repository_id='gcp-dpl-dataform-blip-stream-ingestion',
                workflow_invocation={
                    "compilation_result": "{{ task_instance.xcom_pull(task_ids='copilot_ticket_end_summary_created_silver.copilot_ticket_end_summary_created_dataform_group.create_compilation')['name'] }}",
                    "invocation_config": {
                        "service_account": "blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com",
                        "included_tags": ["copilot_ticket_end_summary_created"],
                        "transitive_dependencies_included": False,
                        "fully_refresh_incremental_tables_enabled": False,
                    },
                },
                impersonation_chain='blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com',
            )
            create_compilation >> create_invocation

    start_task >> tg >> end_task
```

3. **Upload to Cloud Composer Bucket via Impersonation:**
   The Composer bucket (`gs://blip-prd-cmp-dag-sam1`) requires impersonating the Composer management service account:
   ```bash
   CLOUDSDK_ACTIVE_CONFIG_NAME=blip gcloud storage cp \
     dag_ING_EVH_KAFKA_COPILOT_TICKET_END_SUMMARY_CREATED_KFKCONN.py \
     gs://blip-prd-cmp-dag-sam1/dags/custom/ \
     --impersonate-service-account=blip-dpl-prd-cmp-sa-sam1@blip-dpl-prd-sam-central.iam.gserviceaccount.com
   ```

---

### Phase 5: Trigger & A/B Parity Audit

1. **Unpause & Trigger DAG via Composer Airflow REST API:**
   ```python
   # Authenticate with Composer SA token
   # POST https://<composer-web-url>/api/v1/dags/<dag_id>/dagRuns
   ```

2. **Execute A/B Parity Query:**
   ```sql
   WITH prod AS (
     SELECT 
       DATE(storage_date_br) AS dt,
       COUNT(1) AS prod_count,
       COUNT(DISTINCT ticket_id) AS prod_unique_keys
     FROM `blip-dpl-prd-sam-i-plt-str-0.silver_copilot.ticket_end_summary_created`
     WHERE DATE(storage_date_br) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
     GROUP BY 1
   ),
   shadow AS (
     SELECT 
       DATE(storage_date_br) AS dt,
       COUNT(1) AS shadow_count,
       COUNT(DISTINCT ticket_id) AS shadow_unique_keys
     FROM `blip-dpl-prd-sam-i-plt-str-0.silver_copilot__kfkconn_test.ticket_end_summary_created`
     WHERE DATE(storage_date_br) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
     GROUP BY 1
   )
   SELECT 
     COALESCE(p.dt, s.dt) AS partition_date,
     p.prod_count,
     s.shadow_count,
     (s.shadow_count - p.prod_count) AS diff_rows,
     p.prod_unique_keys,
     s.shadow_unique_keys
   FROM prod p
   FULL OUTER JOIN shadow s ON p.dt = s.dt
   ORDER BY partition_date DESC;
   ```
   > [!IMPORTANT]
   > **Verification Standard:** Closed past dates (e.g. `CURRENT_DATE() - 2`) must yield `diff_rows = 0` (100.00% exact parity).

---

### Phase 6: Production Cutover & Dataflow Decommissioning

1. **Merge PR on GitHub:** Merge `feat/kfkconn-...` into `main`.
2. **Update DAG in GCS:**
   * Set `"git_commitish": "main"`
   * Remove or empty `"schema_suffix": ""` so outputs write to `silver_copilot.ticket_end_summary_created`.
3. **Drain Legacy Dataflow Job:**
   * Identify job ID:
     ```bash
     CLOUDSDK_ACTIVE_CONFIG_NAME=blip gcloud dataflow jobs list \
       --region=southamerica-east1 \
       --status=active \
       --filter="name:confluent-copilot-ticket-end-summary-created*"
     ```
   * Drain the job (gracefully empties in-flight buffer without data loss):
     ```bash
     CLOUDSDK_ACTIVE_CONFIG_NAME=blip gcloud dataflow jobs drain <JOB_ID> \
       --region=southamerica-east1
     ```
4. **Pause Legacy DAG in Composer:**
   Pause `ING_EVH_KAFKA_COPILOT_TICKET_END_SUMMARY_CREATED` to eliminate obsolete runs.

---

## 🚨 Troubleshooting & Diagnostic Gotchas

### 1. Error: `Table raw_platform_kfkconn.<name> was not found`
* **Root Cause:** Confluent Cloud Kafka Connect mapped the topic with an entity/tenant prefix (e.g., `imt_prod_<name>` or `imt_<tenant>_<name>`), but Dataform references the canonical name `imt_<name>`.
* **Fix:** Create a BigQuery compatibility view in `raw_platform_kfkconn` pointing to the underlying active Iceberg table.

### 2. Error: `Permission 'dataform.workflowInvocations.create' denied`
* **Root Cause:** Attempting to trigger workflow invocations directly using end-user credentials instead of the Dataform execution service account.
* **Fix:** Ensure Composer DAG specifies `impersonation_chain='blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com'`.

### 3. Error: `403 Forbidden uploading DAG to gs://blip-prd-cmp-dag-sam1`
* **Root Cause:** Direct user identity lacks GCS write access to the Composer storage bucket.
* **Fix:** Use `--impersonate-service-account=blip-dpl-prd-cmp-sa-sam1@blip-dpl-prd-sam-central.iam.gserviceaccount.com`.

### 4. Error: GitHub Branch Rejected on Push
* **Root Cause:** The remote repository enforces strict branch naming regex:
  `^(revert-\d+-)?(copilot|feat|fix|style|refactor|perf|build|chore|revert|ci|docs|spike|test|release|hotfix|hotfix-\d{1,2}\.\d{1,2}\.x)\/[a-z0-9-]+$`
* **Fix:** Name branches strictly within pattern: `feat/kfkconn-<entity>-pilot`.

---

## 🔗 Related Skills & Documentation
- `[confluent-kafka-bigquery-ingestion](file:///usr/local/google/home/gricardo/.gemini/config/skills/confluent-kafka-bigquery-ingestion/SKILL.md)`: Confluent Cloud SMT and Iceberg table mapping.
- `[gcp-dataform-deployment](file:///usr/local/google/home/gricardo/.gemini/config/skills/gcp-dataform-deployment/SKILL.md)`: Dataform REST API endpoints and token handling.
- `[blip-dataflow-kafka-parity-audit.md](file:///usr/local/google/home/gricardo/memory/default/projects/blip-dataflow-kafka-parity-audit.md)`: Full audit methodology and Dataflow shutdown readiness.
