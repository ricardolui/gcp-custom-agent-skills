---
name: bigquery-agentic-e2e-tester
description: Automated headless test runner for the BigQuery Agentic Demo Engine. Executes end-to-end company research (8 use cases), regional systems validation, BigQuery Property Graph generation, and Gemini Enterprise A2A provisioning, outputting deep console links.
---

# BigQuery Agentic Demo Engine — Automated Headless E2E Tester

This skill automates the validation and end-to-end verification of any enterprise demo target without requiring manual UI clicking or waiting for Cloud Run deployments.

## Quick Execution

To run an automated end-to-end test on any company:

```bash
python3 scripts/run_e2e_company_headless.py "<company_domain_or_name>" "<data_project_id>" "<gemini_enterprise_project_id>"
```

### Example:
```bash
python3 scripts/run_e2e_company_headless.py "www.boticario.com.br" "bq-agents-ripley" "dataml-latam-argolis"
```

## What this Skill Verifies:
1. **Regional Systems & Localized Schemas**: Inspects country-specific schemas (e.g. `VTEX`, `SEFAZ NF-e`, `TOTVS` for Brazil; `Shopify`, `NetSuite`, `Stripe` for US; `DIAN`, `PSE` for Latam).
2. **8 Researched Use Cases**: Validates the presence of 3 Standard Industry Showcase Blueprints (`ind_1` to `ind_8`) + 5 Custom Strategic Big Data & AI Use Cases.
3. **BigQuery Property Graph & GQL Rules**: Validates `GRAPH_EXPAND` Table-Valued Functions and pre-defined Semantic Measures (`AGG()`).
4. **Canonical BigQuery GDA A2A Protocol**: Checks the 10 official Google extensions and `INTERNAL_HTTP+JSON` transport.
5. **Discovery Engine Authorizations & Permissions**: Verifies OAuth 2.0 authorizations with `https://www.googleapis.com/auth/cloud-platform` scope.
6. **Console Deep Links Output**: Generates Google Account Chooser wrapped URLs for:
   - 🔗 Dataform Studio & Data Engineering Workspace
   - 🔗 BigQuery Conversational Agents Hub
   - 🔗 Gemini Enterprise Assistant with A2A
