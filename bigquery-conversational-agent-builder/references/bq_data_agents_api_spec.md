# BigQuery Conversational Analytics (Data Agents) API Specification

Service: `geminidataanalytics.googleapis.com`  
Default Version: `v1beta` / `v1`  
Location: `global` (or regional: `us-central1`, `eu`, `us`)

---

## 1. REST Endpoints

### 1.1. Create Data Agent
- **Method**: `POST https://geminidataanalytics.googleapis.com/v1beta/projects/{projectId}/locations/{location}/dataAgents?dataAgentId={dataAgentId}`
- **Headers**:
  - `Authorization: Bearer <GCP_OAUTH_TOKEN>`
  - `Content-Type: application/json`

```json
{
  "name": "projects/{projectId}/locations/{location}/dataAgents/{dataAgentId}",
  "displayName": "Enterprise - Inventory Optimization Specialist",
  "description": "Conversational agent grounded on BigQuery Property Graph",
  "labels": {
    "published_context": "true"
  },
  "dataAnalyticsAgent": {
    "publishedContext": {
      "datasourceReferences": {
        "bq": {
          "propertyGraphReferences": [
            {
              "projectId": "my-project",
              "datasetId": "dataset_gold",
              "propertyGraphId": "enterprise_graph"
            }
          ]
        }
      },
      "systemInstruction": "You are an expert BI analyst...",
      "exampleQueries": [
        {
          "naturalLanguageQuestion": "Qual o spend total faturado por departamento?",
          "sqlQuery": "SELECT department, AGG(total_spend) FROM GRAPH_EXPAND(...) GROUP BY department"
        }
      ]
    },
    "stagingContext": {
      "datasourceReferences": { ... },
      "systemInstruction": "...",
      "exampleQueries": [ ... ]
    }
  }
}
```

### 1.2. Update (Patch) Data Agent
- **Method**: `PATCH https://geminidataanalytics.googleapis.com/v1beta/projects/{projectId}/locations/{location}/dataAgents/{dataAgentId}?updateMask=data_analytics_agent.published_context,data_analytics_agent.staging_context,labels,description,display_name`

### 1.3. Get Data Agent Card (A2A)
- **Method**: `GET https://geminidataanalytics.googleapis.com/v1beta/a2a/projects/{projectId}/locations/{location}/dataAgents/{dataAgentId}/v1/card`

---

---

## 3. BigQuery Enterprise Reservation & Dry-Run Validation Rules

### 3.1. Internal Backend Validation Mechanism
When `propertyGraphReferences` is supplied in `datasourceReferences.bq`, the backend (`IamUtil.kt`) validates read access by issuing an internal dry-run query:
```sql
SELECT * FROM GRAPH_TABLE(`{projectId}`.`{datasetId}`.`{propertyGraphId}` MATCH (n) RETURN 1 AS dummy_col LIMIT 0)
```

### 3.2. Enterprise Edition Constraint
- **Rule**: BigQuery strictly requires an active **Enterprise or Enterprise Plus reservation slot assignment** (`edition = ENTERPRISE | ENTERPRISE_PLUS`) in the target location to execute or dry-run GQL (`GRAPH_TABLE`).
- **On-Demand Behavior**: On pure on-demand projects without an Enterprise reservation, BigQuery throws:
  `BigQuery Graph queries require a reservation with Enterprise or Enterprise Plus edition.`
- **API Impact**: This causes `geminidataanalytics.googleapis.com` to fail with `400 BadRequestException: User does not have read access to one or more BigQuery resources...`.

### 3.3. Pre-Flight Command Workflow
```bash
# 1. Create Enterprise reservation with autoscale max slots:
bq mk --project_id=<PROJECT> --location=<LOCATION> --reservation --edition=ENTERPRISE --slots=0 <RESERVATION_NAME>
bq update --project_id=<PROJECT> --location=<LOCATION> --reservation --autoscale_max_slots=50 <RESERVATION_NAME>

# 2. Assign QUERY jobs to Enterprise reservation:
bq mk --project_id=<PROJECT> --location=<LOCATION> --reservation_assignment --reservation_id=<RESERVATION_NAME> --assignee_type=PROJECT --assignee_id=<PROJECT> --job_type=QUERY
```

