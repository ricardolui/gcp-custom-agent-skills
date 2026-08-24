# Google Cloud Custom Agent Skills 🚀

A curated collection of production-grade, enterprise-ready **AI Agent Skills** designed for Google Cloud data engineering, BigQuery Property Graphs, Conversational Analytics, streaming pipelines, Lakehouse architectures, and cloud security.

These skills empower AI coding assistants (Google Antigravity, Gemini CLI, Claude Desktop, Cursor, VS Code) with deep domain knowledge, hardened execution scripts, and field-tested architectural blueprints.

> [!NOTE]
> **Complement to Data Agent Kit**: These skills complement the official [GoogleCloudPlatform/data-agent-kit](https://github.com/GoogleCloudPlatform/data-agent-kit) by focusing on specialized production workflows, migration frameworks, and advanced cross-service integrations.

---

## 📚 Curated Skills Catalog

### 🧠 BigQuery Conversational Analytics & Property Graphs

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`bigquery-graph`](bigquery-graph/SKILL.md)** | BigQuery Property Graph & Semantic Graph Engineering | Production GoogleSQL GQL DDL, `MEASURE(...)` declarations, Pre-Flight Topology Audits (Zero-Degree Island Node resolution, Symmetrical Multientity Edges), and Column Content Profiling (Jaccard Similarity & Cardinality heuristics). |
| **[`bigquery-conversational-agent-builder`](bigquery-conversational-agent-builder/SKILL.md)** | Gemini Data Analytics API & Agent2Agent (A2A) Federation | Mandatory Graph-First grounding standard, automated 10 Golden Query Archetypes generation, compiler dry-run auto-healing loop, and Gemini Enterprise Discovery Engine OAuth A2A federation. |
| **[`bigquery-bigtable-compact-reverse-etl`](bigquery-bigtable-compact-reverse-etl/SKILL.md)** | High-Efficiency Reverse ETL to Cloud Bigtable | Maximizes Bigtable SSD storage savings (40–50% cost reduction) using persistent Avro Binary and Deflate UDFs (`EXPORT DATA format='CLOUD_BIGTABLE'`). |
| **[`bigquery-sql`](bigquery-sql/SKILL.md)** | BigQuery SQL Optimization & Performance Tuning | Query execution tuning, anti-pattern prevention, slot compute reduction, and cost optimization rules. |
| **[`bigquery-bigframes`](bigquery-bigframes/SKILL.md)** | BigQuery DataFrames (BigFrames) Python Development | Scalable pandas and scikit-learn APIs executing in-engine against BigQuery compute. |
| **[`bigquery-ai-ml`](bigquery-ai-ml/SKILL.md)** | BigQuery In-Engine Machine Learning & GenAI | Time-series forecasting, outlier detection, LLM generation, and semantic search directly in SQL. |

---

### 📊 Looker & Semantic Modeling

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`looker-auth-mcp`](looker-auth-mcp/SKILL.md)** | Looker Authentication & Local MCP Toolbox Integration | Connects AI agents to Looker via `@toolbox-sdk/server` and Python SDK without remote credential forwarding. Includes automated credential injection helper. |
| **[`looker-pop-modeling`](looker-pop-modeling/SKILL.md)** | Period-over-Period (PoP) Modeling & Semantic Reconciliation | Best practices for dynamic SHA256 Surrogate Key resolution in BigQuery, LookML `extends` inheritance clash elimination, and delta metrics logic. |
| **[`looker-mcp-gemini-enterprise`](looker-mcp-gemini-enterprise/SKILL.md)** | Looker MCP Platform with Gemini Enterprise | End-to-end setup for connecting Looker semantic layer with Gemini Enterprise using OAuth/PKCE and no-code analytical agents. |

---

### ⚡ Real-Time Streaming & Apache Beam

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`gcp-dataflow-scd-kafka-migration`](gcp-dataflow-scd-kafka-migration/SKILL.md)** | Production Apache Beam Pipelines on Cloud Dataflow | Low-latency streaming blueprints covering Google Managed Kafka `SASL/OAUTHBEARER` (JDK 21 sidecar overrides), 3-flag high-throughput tuning, SCD Type 1 via CDC multimap side-inputs, and BigQuery Storage Write API type-conformity guards. |
| **[`spark-to-beam-translator`](spark-to-beam-translator/SKILL.md)** | Databricks PySpark to Apache Beam Dataflow Migration | Architectural mapping, stateful deduplication, slow-moving dimension enrichment, and cost optimization framework for migrating from Delta Lake to Google Cloud native streaming. |

---

### 🧊 Lakehouse & Orchestration

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`google-iceberg-spark-bigquery`](google-iceberg-spark-bigquery/SKILL.md)** | Lakehouse Integration: Iceberg, Spark & BigQuery | Implements Google Cloud Lakehouse architecture using Lakehouse Iceberg REST Catalogs via Credential Vending with Dataproc Serverless (Spark Connect) and BigQuery DML / Table Management. |
| **[`federate-lakehouse-catalog`](federate-lakehouse-catalog/SKILL.md)** | Lakehouse Federated REST Catalogs (Unity / Glue) | Configures BigQuery Lakehouse federation to remote Apache Iceberg REST Catalogs (Databricks Unity Catalog, AWS Glue) across clouds. |
| **[`gcp-managed-airflow-migrations`](gcp-managed-airflow-migrations/SKILL.md)** | Cloud Composer / Managed Service for Apache Airflow (MSAA) | Automated scanning and migration playbooks for Airflow 2.11 (MSAA Gen 2/3) and Airflow 3 (MSAA Gen 3). |
| **[`gcp-bigquery-notebook-uploader`](gcp-bigquery-notebook-uploader/SKILL.md)** | Notebook Dataform Uploader & Colab Emulator | Programmatic Python CLI to upload and commit Jupyter Notebooks (`.ipynb`) into Dataform repositories, instantly making them native code assets in BigQuery Studio & Colab Enterprise. |
| **[`gcp-dataform-deployment`](gcp-dataform-deployment/SKILL.md)** | Dataform REST Deployment & Act-As IAM Orchestration | Programmatic REST API workflow for workspace management, code compilation, execution orchestration, and resolving strict IAM Act-As permissions. |

---

### 🔒 Security, Governance & Operations

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`gemini-enterprise-cleanup`](gemini-enterprise-cleanup/SKILL.md)** | Gemini Enterprise / Discovery Engine Agent Governance | Operational playbooks and CLI scripts for safely listing, auditing, and cleaning conversational data agents, A2A authorizations, and OAuth bindings. |
| **[`gcs-security-assessment`](gcs-security-assessment/SKILL.md)** | Cloud Storage SAIF & Security Posture Assessment | Security vulnerability scanning, IAM posture evaluation, and Secure AI Framework (SAIF) compliance checks for GCS. |
| **[`enforcing-resource-attribution`](enforcing-resource-attribution/SKILL.md)** | CLI Resource Attribution & Mandatory Labeling | Enforces mandatory `--label datacloud:jetski` tagging across `bq` and `gcloud` provisioning and data execution jobs. |
| **[`gcp-cloudrun-iap-loadbalancer`](gcp-cloudrun-iap-loadbalancer/SKILL.md)** | Cloud Run + HTTPS Load Balancer + IAP Security | Resolves JWT Client ID mismatch conflicts when securing Cloud Run behind an External HTTPS Load Balancer with Identity-Aware Proxy (IAP). |
| **[`cloud-cost-dashboard-ux`](cloud-cost-dashboard-ux/SKILL.md)** | Cloud Cost & Daily Telemetry Dashboard UX | Design patterns for telemetry explorers: overcoming the D-1 asynchronous billing lag dilemma, client-side data slicing, and absolute delta sorting. |
| **[`gcp-custom-skills-sync`](gcp-custom-skills-sync/SKILL.md)** | Skills Governance & Git Repository Synchronization | Memory and operational commands for managing and synchronizing custom agent skills with version control. |

---

### 🧪 Automated Testing & Pre-Deployment Release Gates

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`bigquery-predeploy-e2e-gate`](bigquery-predeploy-e2e-gate/SKILL.md)** | 4-Tier Automated Pre-Deployment Verification Gate | Automated gate running TDD unit tests, isolated local server E2E pipeline, git commit safety, and Cloud Run live smoke checks. |
| **[`bigquery-isolated-e2e-runner`](bigquery-isolated-e2e-runner/SKILL.md)** | Isolated Headless E2E Verification Engine | Executes end-to-end tests against temporary servers, tracking all created BigQuery/Vertex assets in a manifest JSON ledger with on-demand cleanup. |
| **[`bigquery-agentic-e2e-tester`](bigquery-agentic-e2e-tester/SKILL.md)** | Automated Headless Agentic Demo Tester | Validates multi-case company research, regional systems, Property Graph generation, and Gemini Enterprise provisioning with deep console links. |

---

## 🛠️ Installation & Usage

### 1. In Google Antigravity / Gemini CLI
Clone or copy this repository into your local agent configuration directory:

```bash
mkdir -p ~/.gemini/config/skills
git clone https://github.com/ricardolui/gcp-custom-agent-skills.git ~/.gemini/config/skills
```

### 2. Private Credentials Configuration
To configure local private credentials (such as Looker API keys or default project profiles) without ever committing them:

1. Copy the example environment template or create a `.env` file in the root directory:
   ```bash
   cp .env.example .env
   ```
2. Populate your local `.env` variables:
   ```env
   LOOKER_BASE_URL="https://<YOUR_INSTANCE>.looker.app"
   LOOKER_CLIENT_ID="<YOUR_CLIENT_ID>"
   LOOKER_CLIENT_SECRET="<YOUR_CLIENT_SECRET>"
   ```
   *(Note: `.env` is permanently ignored by `.gitignore` and will never be tracked by Git).*

---

## 📄 License

Apache-2.0 License. See [LICENSE](LICENSE) for details.
