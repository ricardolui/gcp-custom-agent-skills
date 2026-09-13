---
name: blip-pubsub-eventhub-migration
description: Use when migrating Azure Event Hubs ingestion pipelines to Google Cloud Pub/Sub Import Topics and BigQuery Managed Iceberg tables, configuring Azure Entra ID OIDC federation, JavaScript UDF SMT transforms, or managing BigQuery direct subscriptions.
---

# Blip: Azure Event Hubs to Cloud Pub/Sub & BigLake Iceberg Ingestion

Comprehensive operational guide and architecture patterns for migrating streaming ingestion pipelines from Azure Event Hubs to Google Cloud Pub/Sub Topic Ingestion and BigQuery Managed Apache Iceberg tables (`raw_*_pubsub.imt_*`).

---

## 📌 Architectural Overview & Financial Impact

Legacy Blip ingestion routes Azure Event Hubs through Google Cloud Dataflow streaming jobs (`EventHubsToBigQuery.json`). This requires ~258 dedicated GCE worker instances in São Paulo (`southamerica-east1`), accumulating **~$32,000 to $34,000/month** due to regional VM compute surcharges (+158% vs US regions) and minimum cluster constraints on low-throughput topics.

Google Cloud Pub/Sub native **Topic Ingestion (Azure Event Hubs)** and **BigQuery Direct Subscriptions** eliminate the entire Dataflow fleet:
* **Pub/Sub Import Topic (Azure Event Hubs -> Pub/Sub):** \$80/TiB (flat global rate, zero regional surcharge).
* **BigQuery Direct Subscription:** \$50/TiB (replaces separate BigQuery Storage Write API charges).
* **Total Cost:** **~$1,511/month** across all 102 pipelines (11.63 TiB/month) = **~95.3% cost reduction** (~-$31,500/month or ~R$ 170.000/mês savings).

```
LEGACY DATAFLOW ARCHITECTURE (~$33k/mo):
[Azure Event Hubs] ──(SAS Connection String)──> [GCE Dataflow Fleet (258 VMs)] ──(Storage Write API)──> [BigQuery raw_platform.imt_*]

PUB/SUB IMPORT & BIGLAKE ICEBERG (~$1.5k/mo):
[Azure Event Hubs] ──(OIDC Workload Identity)──> [Pub/Sub Import Topic] ──(JS UDF SMT + Table Schema)──> [BigQuery raw_platform_pubsub.imt_* (Iceberg)]
```

---

## 🎯 When to Use & When NOT to Use

### Use When:
- Migrating any Azure Event Hubs ingestion pipeline to Google Cloud Pub/Sub managed ingestion.
- Provisioning or updating Pub/Sub BigQuery subscriptions writing directly into BigLake Apache Iceberg tables (`table_format = 'ICEBERG'`).
- Configuring Single Message Transforms (SMT JavaScript UDF) to inject metadata columns (`_meta_source_signature`, `_meta_namespace`, `_meta_enqueued_time`, `_meta_ingestion_time`, `_meta_partition_id`, `_meta_sequence_number`) matching legacy Dataflow contracts.
- Configuring Azure Entra ID (Azure AD) Workload Identity Federation (OIDC) between Azure Event Hubs and Google Cloud Pub/Sub.
- Truncating or resetting BigLake Iceberg tables receiving streaming writes.
- Debugging NULL metadata columns or schema parsing failures on Pub/Sub BigQuery subscriptions.

### Do NOT Use When:
- Ingesting Confluent Cloud Kafka topics (use `confluent-kafka-bigquery-ingestion`).
- Refactoring Cloud Composer Airflow DAGs for Dataform incremental routines (use `blip-composer-dataform-stream-migration`).
- Ingesting batch relational databases (SQL Server, PostgreSQL, MongoDB) via CDC.

---

## ⚡ Quick Reference: The 6-Phase Lifecycle

| Phase | Responsibility | Key Action / Asset |
| :--- | :--- | :--- |
| **1. Azure Entra ID & RBAC** | Azure Admin | Create App registration, configure OIDC Federated Credential with GCP SA, assign `Azure Event Hubs Data Receiver` role. |
| **2. GCP IAM Preparation** | GCP Admin | Grant `roles/iam.serviceAccountTokenCreator` on GCP Ingestion SA to Pub/Sub Service Agent (`service-{NUM}@gcp-sa-pubsub.iam.gserviceaccount.com`). |
| **3. BigLake Iceberg Tables** | BigQuery / IaC | Create `raw_*_pubsub` dataset and Iceberg Managed Tables (`table_format = 'ICEBERG'`, `file_format = 'PARQUET'`, `WITH CONNECTION`). |
| **4. Pub/Sub Import Topic** | Pub/Sub / IaC | Provision `google_pubsub_topic` with `ingestion_data_source_settings.azure_event_hubs`. Topic status transitions to `ACTIVE`. |
| **5. SMT JS UDF & Subscription** | Pub/Sub / IaC | Provision `google_pubsub_subscription` with `use_table_schema = true`, `drop_unknown_fields = true`, and JavaScript UDF SMT injecting cluster metadata. |
| **6. Parity Audit & Cutover** | Data Engineering | Verify zero NULL metadata columns, truncate test tables cleanly, and point downstream Dataform staging views to `raw_*_pubsub`. |

---

## 🔐 Phase 1 & 2: OIDC Workload Identity Federation

Pub/Sub managed import **does not support static SAS connection strings**. It strictly requires OIDC Workload Identity Federation via Microsoft Entra ID.

### 1. Azure Entra ID Configuration (Azure Portal / CLI)
1. **App Registration:** Create an App Registration in Azure AD (e.g. `gcp-pubsub-eventhub-reader`).
   * Record `client_id` (Application ID) and `tenant_id` (Directory ID).
2. **Federated Credential:**
   * **Federation Scenario:** Customer Managed / Other issuer.
   * **Issuer URL:** `https://accounts.google.com`
   * **Subject Identifier:** The Unique Numeric ID of the GCP Ingestion Service Account:
     ```bash
     gcloud iam service-accounts describe \
       blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com \
       --format="value(uniqueId)"
     ```
   * **Audience:** The same GCP SA Unique Numeric ID (or `https://accounts.google.com`).
3. **Role Assignment (RBAC):**
   * Assign the role **`Azure Event Hubs Data Receiver`** to the App Registration identity on the target Resource Group or Event Hub Namespace.

### 2. GCP IAM Binding
The Google Cloud Pub/Sub service agent needs permission to impersonate the GCP ingestion service account to request tokens:
```bash
CLOUDSDK_ACTIVE_CONFIG_NAME=blip gcloud iam service-accounts add-iam-policy-binding \
  blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com \
  --project=blip-dpl-prd-sam-i-plt-str-0 \
  --member="serviceAccount:service-885060824987@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

---

## 🧊 Phase 3: BigLake Apache Iceberg Table Provisioning

Target tables must match the canonical Dataflow 8-column layout, partitioned by `_meta_enqueued_time` and clustered by `_meta_namespace, _meta_partition_id`:

```sql
CREATE SCHEMA IF NOT EXISTS `blip-dpl-prd-sam-i-plt-str-0.raw_platform_pubsub`
OPTIONS(location="southamerica-east1");

CREATE TABLE IF NOT EXISTS `blip-dpl-prd-sam-i-plt-str-0.raw_platform_pubsub.imt_tickets` (
  data STRING,
  messageKey STRING,
  _meta_partition_id STRING,
  _meta_sequence_number INT64,
  _meta_enqueued_time TIMESTAMP,
  _meta_ingestion_time TIMESTAMP,
  _meta_source_signature STRING,
  _meta_namespace STRING
)
PARTITION BY DATE(_meta_enqueued_time)
CLUSTER BY _meta_namespace, _meta_partition_id
WITH CONNECTION `blip-dpl-prd-sam-i-plt-str-0.southamerica-east1.dpl-conn-raw_platform`
OPTIONS (
  file_format = 'PARQUET',
  table_format = 'ICEBERG',
  storage_uri = 'gs://blip-dpl-prd-sam-i-plt-str-0-dpl-iceberg-raw_platform/raw_platform_pubsub/imt_tickets/'
);
```

---

## ⚙️ Phase 4 & 5: Terraform Module & SMT UDF Architecture

### 1. The SMT JavaScript UDF (`references/eventhub_smt_template.js`)
Without SMT, Pub/Sub BigQuery subscriptions write ONLY to the `data` column, leaving all `_meta_*` columns NULL.  
The JavaScript UDF extracts attributes from Azure Event Hubs, injects pipeline-specific parameters (`_meta_source_signature` and `_meta_namespace`), and hoists the payload:

```javascript
function transform(message, metadata) {
  var rawData = message.data;
  var attrs = message.attributes || {};
  var now = new Date().toISOString();
  
  var enqueued = attrs["azure.eventhubs.enqueued_time"] || (metadata && metadata.publish_time) || now;
  var partitionId = attrs["azure.eventhubs.partition_id"] || "0";
  var seqNum = attrs["azure.eventhubs.sequence_number"] ? parseInt(attrs["azure.eventhubs.sequence_number"], 10) : 0;
  
  var transformed = {
    data: rawData,
    messageKey: message.orderingKey || null,
    _meta_partition_id: partitionId,
    _meta_sequence_number: seqNum,
    _meta_enqueued_time: enqueued,
    _meta_ingestion_time: now,
    _meta_source_signature: "${META_SOURCE_SIGNATURE}",
    _meta_namespace: "${META_NAMESPACE}"
  };
  
  message.data = JSON.stringify(transformed);
  return message;
}
```

### 2. Variable Extraction Rules for Dataflow Parity:
* **Desk Multi-Tenant / Dog-Breed Clusters** (`evhns-msging-desk-prd-<tenant>`):
  * Regex rule: `can(regex("^evhns-msging-desk-prd-(.+)$", namespace)) ? regex("^evhns-msging-desk-prd-(.+)$", namespace)[0] : topic`
  * Injects tenant cluster slugs: `maltes`, `dalmata`, `caramelo`, `boxer`, `beagle`, `labrador`, `husky`.
  * Downstream Dataform Silver models (`stg_platform_tickets.sqlx`) require this exact value as `source_signature`.
* **Shared Multi-Topic Namespaces** (`da-seq-eventhub`):
  * Injects the EventHub topic name: `seq-blipprod`, `seq-blippacks`, `seq-whatsappbroadcast`, `seq-pluginmarketplace`.

### 3. Terraform Module Definition (`modules/gcp_pubsub_eventhub_ingestion/`)
```hcl
resource "google_pubsub_topic" "eventhub_topic" {
  name    = var.topic_name
  project = var.project_id

  ingestion_data_source_settings {
    azure_event_hubs {
      resource_group     = var.azure_resource_group
      namespace          = var.eventhub_namespace
      event_hub          = var.eventhub_name
      client_id          = var.azure_client_id
      tenant_id          = var.azure_tenant_id
      subscription_id    = var.azure_subscription_id
      gcp_service_account = var.gcp_service_account
    }
  }
}

resource "google_pubsub_subscription" "bigquery_sub" {
  name    = "${var.topic_name}-bq"
  project = var.project_id
  topic   = google_pubsub_topic.eventhub_topic.id

  bigquery_config {
    table               = var.target_bigquery_table
    use_table_schema    = true
    write_metadata      = false
    drop_unknown_fields = true
  }

  message_transforms {
    javascript_udf {
      function_name = "transform"
      code          = templatefile("${path.module}/templates/transform.js.tpl", {
        meta_source_signature = var.meta_source_signature
        meta_namespace        = var.meta_namespace
      })
    }
  }

  ack_deadline_seconds = 300
}
```

---

## 🚨 Critical Pitfalls & Diagnostic Gotchas

### 1. BigLake Apache Iceberg Truncate Trap
* **Symptom:** Executing `TRUNCATE TABLE raw_platform_pubsub.imt_*` fails with:
  `BigQuery tables for Apache Iceberg do not support TRUNCATE TABLE DML`.
  Executing `DELETE FROM ... WHERE TRUE` fails with:
  `UPDATE or DELETE statement over table ... would affect rows in the streaming buffer, which is not supported`.
* **Fix:** You cannot use DML truncate. Execute `CREATE OR REPLACE TABLE ... WITH CONNECTION ... OPTIONS (table_format = 'ICEBERG')` to cleanly reset the storage manifest and table.

### 2. GCloud CLI Subscription Update Trap
* **Symptom:** Running `gcloud pubsub subscriptions update <sub> --bigquery-table=<table_id>` causes all subsequent incoming rows to write metadata columns as NULL.
* **Root Cause:** The `gcloud` CLI resets `useTableSchema` to `false` when `--bigquery-table` is modified without explicitly repeating the flags.
* **Fix:** Always supply `--use-table-schema` and `--drop-unknown-fields` during any CLI update:
  ```bash
  CLOUDSDK_ACTIVE_CONFIG_NAME=blip gcloud pubsub subscriptions update <SUB_NAME> \
    --bigquery-table=<PROJECT>:<DATASET>.<TABLE> \
    --use-table-schema \
    --drop-unknown-fields
  ```

### 3. Ingestion State `FAILED_PRECONDITION` or `RESOURCE_ERROR`
* **Symptom:** Topic ingestion state remains in `FAILED_PRECONDITION`.
* **Root Cause 1:** The Azure App Registration lacks `Azure Event Hubs Data Receiver` on the namespace.
* **Root Cause 2:** The Pub/Sub Service Agent lacks `roles/iam.serviceAccountTokenCreator` on the GCP SA.
* **Fix:** After granting permissions, force immediate re-evaluation:
  ```bash
  CLOUDSDK_ACTIVE_CONFIG_NAME=blip gcloud pubsub topics update <TOPIC_NAME> \
    --labels="recheck=true"
  ```

---

## 🧪 Verification & Parity Audit

To verify that streaming records are landing with zero NULLs and valid Dataflow parameters, run the included parity verification script:

```bash
python3 scripts/verify_pubsub_iceberg_parity.py \
  --project_id blip-dpl-prd-sam-i-plt-str-0 \
  --dataset raw_platform_pubsub \
  --table imt_segment \
  --expected_signature seq-blipprod \
  --expected_namespace da-seq-eventhub
```

Expected output standard:
* `total_rows` > 0
* `with_correct_sig == total_rows`
* `with_correct_ns == total_rows`
* `with_enqueued == total_rows`
* `with_ingestion == total_rows`

---

## 🔗 Related Skills & References
- `[blip-composer-dataform-stream-migration](file:///usr/local/google/home/gricardo/.gemini/config/skills/blip-composer-dataform-stream-migration/SKILL.md)`: Decoupling Composer DAGs and Dataform staging models.
- `[confluent-kafka-bigquery-ingestion](file:///usr/local/google/home/gricardo/.gemini/config/skills/confluent-kafka-bigquery-ingestion/SKILL.md)`: Confluent Cloud Kafka Connect to BigLake Iceberg.
- `[pubsub-bigquery-managed-iceberg](file:///usr/local/google/home/gricardo/memory/default/topics/pubsub-bigquery-managed-iceberg.md)`: Pub/Sub BigLake storage engine architecture.
- `[blip-pubsub-eventhub-migration memory](file:///usr/local/google/home/gricardo/memory/default/projects/blip-pubsub-eventhub-migration.md)`: Project tracking, sizing, and pricing model.
