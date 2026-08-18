---
name: google-iceberg-spark-bigquery
description: Manages Google Cloud Lakehouse architecture integrating Apache Iceberg, Dataproc Serverless (Spark), and BigQuery. Guides the creation of Lakehouse Iceberg REST catalogs using credential vending, configuration of Spark client applications/batches, and enabling preview features such as BigQuery DML and Table Management ('gcp.biglake.bigquery-dml.enabled' and 'gcp.biglake.table-management.enabled').
---

# Google Cloud Lakehouse: Apache Iceberg, Spark & BigQuery Integration

This skill guides you through implementing and managing an integrated, open-format **Lakehouse** on Google Cloud using **Apache Iceberg**, **Dataproc Serverless (Apache Spark)**, and **BigQuery**.

---

## 🏗️ Architectural Overview

A Google Cloud Lakehouse utilizes open-source data formats (specifically **Apache Iceberg**) stored on **Google Cloud Storage (GCS)**, which are registered in a central catalog (the **Lakehouse Iceberg REST Catalog**, formerly BigLake Metastore). 

```
     +-----------------------------------------+
     |          Google Cloud Storage           | <-- Open-format Storage (Parquet/Iceberg)
     |           gs://bucket-name/...          |
     +-----------------------------------------+
                          |
                          | (Authorized via Vended Credentials)
                          v
     +-----------------------------------------+
     |     Lakehouse Iceberg REST Catalog      | <-- Central Metadata & Access Control
     | (projects/PROJECT_ID/catalogs/CATALOG)  |
     +-----------------------------------------+
             ^                        ^
             |                        |
             v                        v
     +---------------+        +----------------+
     |   BigQuery    |        | Dataproc Spark | <-- Interoperable Engines
     | (GoogleSQL)   |        |   (PySpark)    |
     +---------------+        +----------------+
```

Using **Credential Vending (Access Delegation)**, client applications do not need direct IAM permissions on GCS. The Catalog service account delegates short-lived storage access tokens dynamically.

---

## 🛠️ Implementation Steps

### 1. Create the Lakehouse REST Catalog

Create the catalog with **vended-credentials** enabled to allow secure storage delegation.

```bash
gcloud biglake iceberg catalogs create CATALOG_ID \
    --project=PROJECT_ID \
    --catalog-type=biglake \
    --default-location=gs://BUCKET_NAME \
    --credential-mode=vended-credentials
```

### 2. Configure Cloud Storage Bucket Permissions

The auto-provisioned catalog service account needs access to read and write metadata and data files in the GCS bucket.

1. **Retrieve the catalog's service account:**
   ```bash
   BIGLAKE_SA_ID=$(gcloud biglake iceberg catalogs describe CATALOG_ID \
       --project=PROJECT_ID \
       --format="value(biglake-service-account-id)")
   ```

2. **Grant the `Storage Object User` role on the bucket:**
   ```bash
   gcloud storage buckets add-iam-policy-binding gs://BUCKET_NAME \
       --member="serviceAccount:$BIGLAKE_SA_ID" \
       --role="roles/storage.objectUser"
   ```

---

## ⚡ Spark & Dataproc Configuration

### Option A: Dataproc Serverless & Managed Service (Simplified Method)
Google Cloud provides a native mapping property that automatically configures Apache Spark to connect to your Lakehouse Catalog:

```bash
gcloud dataproc batches submit pyspark PYSPARK_FILE \
    --project=PROJECT_ID \
    --region=REGION \
    --properties="dataproc.lakehouse.catalog.CATALOG_NAME=projects/PROJECT_ID/catalogs/CATALOG_ID"
```

### Option B: PySpark Session Configuration (Manual Methods)

Depending on your execution environment (standard PySpark batch vs. Colab Enterprise / BigQuery Studio interactive notebook), choose the appropriate initialization pattern.

#### Option B1: Standard PySpark SparkSession (Batch / Local)
For traditional Spark batches or local testing, configure properties directly via `.config()` on the standard `SparkSession.builder`:

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("IcebergRESTCatalogDemo") \
    .config("spark.sql.catalog.CATALOG_NAME", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.CATALOG_NAME.type", "rest") \
    .config("spark.sql.catalog.CATALOG_NAME.uri", "https://biglake.googleapis.com/iceberg/v1/restcatalog") \
    .config("spark.sql.catalog.CATALOG_NAME.warehouse", "gs://BUCKET_NAME") \
    .config("spark.sql.catalog.CATALOG_NAME.rest.auth.type", "org.apache.iceberg.gcp.auth.GoogleAuthManager") \
    .config("spark.sql.catalog.CATALOG_NAME.io-impl", "org.apache.iceberg.gcp.gcs.GCSFileIO") \
    .config("spark.sql.catalog.CATALOG_NAME.header.x-goog-user-project", "PROJECT_ID") \
    .config("spark.sql.catalog.CATALOG_NAME.header.X-Iceberg-Access-Delegation", "vended-credentials") \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .getOrCreate()
```

#### Option B2: Dataproc Serverless Spark Connect (BigQuery Studio / Colab Enterprise Interactive Kernel) ⭐
When running in the official interactive Jupyter Notebook runtime of BigQuery Studio or Colab Enterprise on GCP, the environment uses a remote Spark Connect kernel. Initialize the session using the `google.cloud.dataproc_spark_connect` module and the custom `Session` object:

```python
from google.cloud.dataproc_spark_connect import DataprocSparkSession
from google.cloud.dataproc_v1 import Session

# 1. Create a Dataproc Serverless session configuration object
session = Session()

# 2. Assign the Iceberg REST Catalog properties to runtime_config.properties
session.runtime_config.version = "3.0"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME"] = "org.apache.iceberg.spark.SparkCatalog"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.type"] = "rest"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.uri"] = "https://biglake.googleapis.com/iceberg/v1/restcatalog"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.warehouse"] = "gs://BUCKET_NAME"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.rest.auth.type"] = "org.apache.iceberg.gcp.auth.GoogleAuthManager"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.io-impl"] = "org.apache.iceberg.gcp.gcs.GCSFileIO"  # Ensure the dot before io-impl is present!
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.header.X-Iceberg-Access-Delegation"] = "vended-credentials"
session.runtime_config.properties["spark.sql.catalog.CATALOG_NAME.header.x-goog-user-project"] = "PROJECT_ID"
session.runtime_config.properties["spark.sql.extensions"] = "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"

# 3. Build the Spark Connect Session using the configuration object
spark = (
   DataprocSparkSession.builder
     .appName("IcebergReadWrite")
     .dataprocSessionConfig(session)
     .getOrCreate()
)
```

---

## 🧊 Schema & Table Creation (DML & Table Management Preview)

To enable read/write interoperability and automated table optimization (compaction, clustering), you must enable table management and BigQuery DML properties when creating your tables.

### Creating Namespace (Schema)
Before creating tables, ensure the Iceberg namespace exists:
```python
spark.sql("CREATE NAMESPACE IF NOT EXISTS CATALOG_NAME.NAMESPACE_NAME;")
```

### Table Creation in Spark
Configure the table with custom `TBLPROPERTIES` flags to opt-in to the preview capabilities:
```sql
CREATE TABLE CATALOG_NAME.NAMESPACE_NAME.TABLE_NAME (
  id INT,
  data STRING
) 
USING ICEBERG
TBLPROPERTIES (
  'gcp.biglake.bigquery-dml.enabled' = true,
  'gcp.biglake.table-management.enabled' = true
);
```

### Table Creation in BigQuery
In BigQuery, these features are implicitly enabled by default, but you can explicitly specify the options:
```sql
CREATE TABLE `PROJECT_ID.CATALOG_ID.NAMESPACE_NAME.TABLE_NAME` (
  id INT,
  data STRING
)
USING ICEBERG
TBLPROPERTIES (
  'gcp.biglake.bigquery-dml.enabled' = true,
  'gcp.biglake.table-management.enabled' = true
);
```

---

## 🔄 Interoperable DML Operations

Once the catalog, namespaces, and tables are created with the correct properties, both engines can execute ACID transactions and DML commands.

### Spark PySpark/SQL:
```python
# Write (Append) via Spark SQL
spark.sql("INSERT INTO CATALOG_NAME.NAMESPACE_NAME.TABLE_NAME VALUES (1, 'Spark Record');")

# Read via Spark
df = spark.read.table("CATALOG_NAME.NAMESPACE_NAME.TABLE_NAME")
df.show()
```

### BigQuery (%%bqsql or GoogleSQL):
```sql
# Write (DML Update) via BigQuery SQL
UPDATE `PROJECT_ID.CATALOG_ID.NAMESPACE_NAME.TABLE_NAME`
SET data = 'Updated from BigQuery'
WHERE id = 1;

# Query state via BigQuery SQL
SELECT * FROM `PROJECT_ID.CATALOG_ID.NAMESPACE_NAME.TABLE_NAME`;
```

---

## 💎 Best Practices

1. **Auth and Delegation**: Always use `--credential-mode=vended-credentials` when creating catalogs. This enforces fine-grained access control and removes the need for distribution of persistent GCS credentials.
2. **Namespace Creation**: Standardize namespace creation in Spark or BigQuery, keeping names identical across catalogs.
3. **Region Match**: Ensure your GCS bucket, BigQuery datasets, and Dataproc resources reside in the same GCP region (e.g., `us-central1`) to prevent cross-region network egress costs and minimize latency.
