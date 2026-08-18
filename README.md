# Google Cloud Custom Agent Skills 🚀

A curated collection of production-grade, enterprise-ready **AI Agent Skills** designed for Google Cloud data engineering, analytics modeling, streaming pipelines, Lakehouse architectures, and cloud security.

These skills empower AI coding assistants (Google Antigravity, Gemini CLI, Claude Desktop, Cursor, VS Code) with deep domain knowledge, hardened execution scripts, and field-tested architectural blueprints.

> [!NOTE]
> **Complement to Data Agent Kit**: These skills complement the official [GoogleCloudPlatform/data-agent-kit](https://github.com/GoogleCloudPlatform/data-agent-kit) by focusing on specialized production workflows, migration frameworks, and advanced cross-service integrations.

---

## 📚 Curated Skills Catalog

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

### 🧊 Lakehouse & BigQuery Development

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`google-iceberg-spark-bigquery`](google-iceberg-spark-bigquery/SKILL.md)** | Lakehouse Integration: Iceberg, Spark & BigQuery | Implements Google Cloud Lakehouse architecture using Lakehouse Iceberg REST Catalogs via Credential Vending with Dataproc Serverless (Spark Connect) and BigQuery DML / Table Management. |
| **[`gcp-bigquery-notebook-uploader`](gcp-bigquery-notebook-uploader/SKILL.md)** | Notebook Dataform Uploader & Colab Emulator | Programmatic Python CLI to upload and commit Jupyter Notebooks (`.ipynb`) into Dataform repositories, instantly making them native code assets in BigQuery Studio & Colab Enterprise. |
| **[`gcp-dataform-deployment`](gcp-dataform-deployment/SKILL.md)** | Dataform REST Deployment & Act-As IAM Orchestration | Programmatic REST API workflow for workspace management, code compilation, execution orchestration, and resolving strict IAM Act-As permissions. |

---

### 🔒 Security, Infrastructure & UX

| Skill | Description | Key Features |
| :--- | :--- | :--- |
| **[`gcp-cloudrun-iap-loadbalancer`](gcp-cloudrun-iap-loadbalancer/SKILL.md)** | Cloud Run + HTTPS Load Balancer + IAP Security | Resolves JWT Client ID mismatch conflicts when securing Cloud Run behind an External HTTPS Load Balancer with Identity-Aware Proxy (IAP). |
| **[`cloud-cost-dashboard-ux`](cloud-cost-dashboard-ux/SKILL.md)** | Cloud Cost & Daily Telemetry Dashboard UX | Design patterns for telemetry explorers: overcoming the D-1 asynchronous billing lag dilemma, client-side data slicing, and absolute delta sorting. |
| **[`gcp-custom-skills-sync`](gcp-custom-skills-sync/SKILL.md)** | Skills Governance & Git Repository Synchronization | Memory and operational commands for managing and synchronizing custom agent skills with version control. |

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
