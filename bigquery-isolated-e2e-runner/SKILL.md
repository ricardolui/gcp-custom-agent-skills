---
name: bigquery-isolated-e2e-runner
description: Automated E2E test runner executing against a temporary isolated local server, validating BigQuery data foundation, Property Graph DDL, Conversational Agents with Verified Golden Queries, and Gemini Enterprise A2A bindings, tracking all created assets in a manifest JSON ledger with on-demand 1-click cleanup.
---

# BigQuery Agentic Demo Engine — Isolated Local E2E Runner & Cleanup Skill

This skill automates end-to-end testing of the entire BigQuery Agentic Demo Engine platform by launching an isolated Node.js backend server on a temporary, dynamically allocated local port, executing the complete multi-step generation and deployment pipeline against Google Cloud, validating BigQuery Conversational Data Agents and Gemini Enterprise A2A bindings, logging all created assets to a manifest JSON ledger, and providing 1-click teardown/cleanup of provisioned cloud resources.

---

## 1. Quick Execution

To run a complete end-to-end test against a fresh local server instance on a temporary port:

```bash
python3 scripts/run_e2e_local_isolated.py --company "<company_domain_or_name>" --data-project "<data_project_id>" --ge-project "<gemini_enterprise_project_id>"
```

### Example:
```bash
python3 scripts/run_e2e_local_isolated.py \
  --company "www.vivo.com.br" \
  --data-project "bigquery-agentic-backend-001" \
  --ge-project "dataml-latam-argolis" \
  --language "Portuguese"
```

---

## 2. Options & Parameters

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--company` | `www.americanas.com.br` | Target company name or domain for agentic research |
| `--data-project` | `bigquery-agentic-backend-001` | Target Google Cloud project for BigQuery datasets and tables |
| `--ge-project` | `dataml-latam-argolis` | Target Gemini Enterprise project for A2A agent registration |
| `--port` | `0` (Auto) | Local port for the temporary Node.js backend (auto-allocates free port if 0) |
| `--language` | `Portuguese` | Language for agent instructions, prompts, and verified queries |
| `--user-email` | `admin@gricardo.altostrat.com` | User email wrapped inside Google Account Chooser links |
| `--cleanup` | `false` | Automatically delete all provisioned GCP assets immediately after verification |
| `--keep-server` | `false` | Keep local backend server running after test completion for manual inspection |

---

## 3. What this Flow Verifies End-to-End:

1. **Temporary Local Server Isolation**:
   - Spawns a dedicated Node.js (`server.js`) process on a random or specified local port.
   - Waits for health check readiness before executing API calls.
2. **Stage 1: Multi-System Enterprise Research (`POST /api/research`)**:
   - Identifies localized industry profile (e.g. BR with SEFAZ/VTEX/Pix/TOTVS).
   - Generates 8 strategic data and AI use cases.
3. **Stage 2: Medallion Lakehouse Foundation (`POST /api/generate-data`)**:
   - Generates 10k synthetic Bronze schemas and SQLX files (including BigQuery Property Graph with `MEASURE(AGG_FUNC(col)) AS measure_name` and `GRAPH_EXPAND`).
4. **Stage 3: Bronze Table Materialization (`POST /api/deploy-bronze`)**:
   - Ingests and materializes tables directly into the target BigQuery dataset.
5. **Stage 4: BigQuery Conversational Agent with Verified Queries (`POST /api/vertex/create-bq-data-agent`)**:
   - Generates and compiler dry-run validates 3 verified golden queries (Ranking/Bar, Time Series/Line, Distribution/Donut).
   - Persists verified queries in both `publishedContext.exampleQueries` and `stagingContext.exampleQueries` with label `published_context: 'true'`.
6. **Stage 5: Gemini Enterprise A2A Agent Provisioning (`POST /api/gemini-enterprise/deploy-agent`)**:
   - Registers/binds the agent card into the target Gemini Enterprise project with `INTERNAL_HTTP+JSON` transport and OAuth `cloud-platform` scope.
7. **Control Manifest & Ledger Tracking (`tests/e2e_runs/run_<timestamp>.json`)**:
   - Logs all provisioned datasets, tables, agents, and console URLs into a persistent JSON manifest.
8. **Graceful Server Teardown**:
   - Automatically terminates the local server process upon test completion (unless `--keep-server` is specified).

---

## 4. On-Demand Teardown & Resource Cleanup

To delete all cloud resources provisioned during a test run:

### Clean up the latest test run:
```bash
python3 scripts/cleanup_e2e_run.py
```

### Clean up a specific test run:
```bash
python3 scripts/cleanup_e2e_run.py --manifest tests/e2e_runs/run_20260813_133221.json
```

### Dry-run preview of what will be deleted:
```bash
python3 scripts/cleanup_e2e_run.py --dry-run
```

### Clean up all past recorded test runs:
```bash
python3 scripts/cleanup_e2e_run.py --all
```

---

## 5. Artifacts and Output Links

Every test run outputs Google Account Chooser wrapped URLs for:
- 🔗 **BigQuery Conversational Agents Hub** (`https://console.cloud.google.com/bigquery/conversational-agents?project=...`)
- 🔗 **Gemini Enterprise Assistant (A2A Live)** (`https://console.cloud.google.com/gemini-enterprise/...`)
- 🔗 **Dataform & Data Engineering Studio** (`https://console.cloud.google.com/bigquery/dataform?project=...`)
