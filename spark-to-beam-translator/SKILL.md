---
name: spark-to-beam-translator
description: 'Expert guidance for analyzing, translating, and migrating PySpark Delta Lake medallion streaming pipelines (Databricks) to Apache Beam pipelines running on Google Cloud Dataflow, including architectural optimization, cost modeling, and performance comparisons.'
license: Apache-2.0
metadata:
  version: v1
  publisher: gcp-custom-skills
---

# Spark-to-Beam Migration and Architectural Optimizer

This skill provides comprehensive methodologies, pattern mappings, and financial/performance models for migrating PySpark Delta Lake streaming applications from Databricks to Apache Beam on Google Cloud Dataflow.

## 1. Architectural Mapping: Spark Medallion vs. Native GCP Beam

When migrating from a Databricks Delta Lake environment, **do NOT attempt a literal 1-to-1 conversion** of every Delta table stream. Delta Lake is designed for Spark's batch-microbatch paradigm. In a native GCP environment, Apache Beam streams directly into BigQuery, which serves as the storage, deduplication, and analytics engine.

| Databricks Delta Layer / Stream | Google Cloud Native (Beam + BigQuery) Equivalent | Migration Strategy & Rationale |
| :--- | :--- | :--- |
| **Bronze Raw** (Stream 1 & 2)<br>Kafka → Delta Table | **KafkaIO → BigQuery Bronze Table** (Partitioned & Clustered) | Stream directly from Kafka using Beam's `KafkaIO`. Write raw JSON/Avro to BigQuery using the **Storage Write API** (or `BigQueryIO.write()`). Partitions and clusters are managed natively in BigQuery. |
| **Silver Deduplicated** (Stream 3 & 4)<br>Delta MERGE via `foreachBatch` | **Beam Stateful Deduplication OR BigQuery MERGE (Dataform/dbt)** | **Option A (Inline Beam):** Use Beam's stateful `Deduplicate` PTransform with a time-to-live (TTL) state to deduplicate inline.<br>**Option B (SQL-centric):** Ingest raw events into BQ Bronze, and use **Dataform/dbt incremental materialization** with MERGE keys to materialize the Silver deduplicated view. |
| **Gold Consolidation** (Stream 5)<br>CDF + Dimension Left Join + ST Lookup | **Beam Side Inputs / CoGroupByKey OR BigQuery SQL Views/Joins** | **Option A (Inline Beam):** Use Beam `SideInputs` (for slow-moving dimensions like merchants/countries) or `CoGroupByKey` (for Payment/Transaction matching), then enrich and stream to BigQuery Gold.<br>**Option B (ELT):** Perform all joins and business logic inside BigQuery using dbt/Dataform SQLX, eliminating Spark Connect cluster session cloning workarounds. |
| **BigQuery Sync** (Stream 6)<br>Gold Delta → GCS → BigQuery MERGE | **Completely Eliminated** | The data is already in BigQuery! This eliminates the GCS staging bucket, temporary schemas, Spark BigQuery connector overhead, and continuous reconciliation queries. |

---

## 2. Core Coding Translation Patterns

### 2.1. Kafka Ingestion & Avro Deserialization
* **PySpark:**
  ```python
  raw_stream = spark.readStream.format("kafka").options(**kafka_opts).load()
  deserialized_df = raw_stream.select(from_avro(expr("substring(kafka_value, 6)"), avro_schema).alias("parsed"))
  ```
* **Apache Beam (Python):**
  ```python
  import apache_beam as beam
  from apache_beam.io.kafka import ReadFromKafka
  from apache_beam.io.gcp.internal.clients import bigquery

  # Using Confluent Schema Registry or inline Avro parser
  class DeserializeAvro(beam.DoFn):
      def __init__(self, schema_str):
          self.schema_str = schema_str
      def setup(self):
          import fastavro
          import io
          self.parsed_schema = fastavro.parse_schema(json.loads(self.schema_str))
      def process(self, element):
          # Skip 5 bytes magic header
          payload = element[1][5:] 
          bytes_io = io.BytesIO(payload)
          for record in fastavro.reader(bytes_io, self.parsed_schema):
              yield record
  ```

### 2.2. Stateful Deduplication
* **PySpark (MERGE):**
  Uses Spark `foreachBatch` + `DeltaTable.merge()`.
* **Apache Beam (State & Timers):**
  ```python
  from apache_beam.transforms.userstate import ReadModifyWriteStateSpec, TimerSpec
  from apache_beam.transforms.timeutil import TimeDomain

  class DeduplicateWithState(beam.DoFn):
      STATE_SPEC = ReadModifyWriteStateSpec('seen_keys', beam.coders.VarIntCoder())
      TIMER_SPEC = TimerSpec('expiry_timer', TimeDomain.REAL_TIME)

      def process(self, element, state=beam.DoFn.StateParam(STATE_SPEC), timer=beam.DoFn.TimerParam(TIMER_SPEC)):
          key, val = element # key = payment_id + operation_id
          seen = state.read()
          if seen is None:
              state.write(1)
              timer.set(time.time() + 86400) # Expiry in 24h
              yield element
  ```

### 2.3. Slow-Moving Dimension Join (Enrichment)
* **PySpark (UC Delta table Overwrite + Load):**
  ```python
  countries = spark.table("gold.dim_countries")
  enriched = payments.join(countries, "country_id", "left")
  ```
* **Apache Beam (Side Inputs):**
  ```python
  # Periodically loaded or static side input
  countries_side_input = beam.pvalue.AsDict(countries_pcollection)
  
  def enrich_payment(payment, countries):
      country_id = payment.get('country_id')
      country_info = countries.get(country_id, {})
      payment.update(country_info)
      return payment

  enriched_payments = (
      payments_pcoll 
      | "Enrich" >> beam.Map(enrich_payment, countries=countries_side_input)
  )
  ```

---

## 3. Cost & Performance Comparison Framework

To run a comparative financial and performance model, use the following standardized formulas:

### 3.1. Databricks (Spark) Cost Model
$$Cost_{Databricks} = \sum (VM_{cost} + DBU_{cost}) \times Hours_{running} + Storage_{Delta} + Networking + BQ_{SyncCost}$$
* **Constant Cost:** Because it is an NRT streaming pipeline, the cluster (Driver + at least 1-2 Worker nodes) must run **24/7/365**, regardless of real-time throughput.
* **DBU Premium:** Databricks charges a high markup per core-hour (DBUs) on top of the cloud VM cost.
* **Staging Overhead:** Stream 6 reads Delta CDF, writes to GCS, and calls BigQuery API Load/Merge. This generates persistent I/O charges in both GCS and BigQuery DML.

### 3.2. Google Cloud Dataflow (Beam) Cost Model
$$Cost_{Dataflow} = (vCPU_{hours} \times vCPU_{rate} + Mem_{hours} \times Mem_{rate} + StreamingEngine_{GB} \times Rate) \times Hours_{active} + Storage_{BQ}$$
* **Serverless Autoscaling:** Dataflow automatically scales down to a single worker during low-traffic periods (e.g., nights/weekends) and scales up instantly on backlog spikes.
* **No Premium Markup:** No third-party licensing fee (like DBUs).
* **Zero-Sync Architecture:** Data is streamed directly to BigQuery using the **Storage Write API** (which has an extremely generous free tier and low ingestion cost). There are no GCS staging writes or continuous BigQuery DML MERGE charges.

### 3.3. Performance Metrics Comparison
* **Latency (NRT SLA):**
  * **Spark:** Micro-batch-based (configured via `.trigger(processingTime="1 minute")`). Minimum latency is limited by the overhead of scheduling Spark jobs per micro-batch (usually 10s to 60s).
  * **Dataflow:** True record-by-record streaming. Latency is sub-second (usually < 2 seconds from Kafka publish to BigQuery write).
* **Resource Overhead:**
  * **Spark:** Driver node coordinates tasks, and workers pull/push data in micro-batches. Connect session cloning overhead.
  * **Dataflow:** Streaming Engine offloads shuffle and state management from the worker VMs, reducing worker memory usage and CPU bottlenecks.
