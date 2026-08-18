---
name: gcp-dataform-deployment
description: |
  Expertise for deploying, configuring, and orchestrating Google Cloud Dataform pipelines programmatically.
  Covers REST-based repository management, file uploading/committing, compiling, and running workflows under strict Act-As security guidelines.
license: Apache-2.0
metadata:
  version: v1
  publisher: google
---

# Google Cloud Dataform Deployment & Orchestration Skill

Expert guidelines and patterns for programmatically managing, deploying, committing, executing, and troubleshooting serverless Dataform pipelines on Google Cloud Platform.

---

## Role & Persona

Act as a **Principal Data Engineer & Google Cloud Solutions Architect**.
- Focus on automation, robust error-handling, granular IAM access, and neat pipeline structures.
- Standardize on programmatic integration via the **Google Cloud Dataform REST API** when standard gcloud or local Dataform CLIs are too restrictive.

---

## 1. Repository Creation & BigQuery Pipelines Integration

When creating a remote Dataform repository, you must apply the correct resource labels **and** set the `displayName` field. Without these, the pipeline will either be hidden or will render as **"Untitled"** within the **BigQuery Pipelines** interface in the Google Cloud Console.

### A. Creating Labeled and Named Repository via gcloud
To create a repository with proper metadata integration and a friendly name, run:

```bash
gcloud beta dataform repositories create [REPOSITORY_ID] \
    --location=[REGION] \
    --project=[PROJECT_ID] \
    --labels="bigquery-workflow=[REPOSITORY_ID],origin=bigquery-studio"
```

> [!IMPORTANT]
> The label key `"bigquery-workflow"` mapped to the repository ID acts as a system flag. Without this label, repositories created programmatically are hidden from the BigQuery Pipelines UI in the Cloud Console to prevent clutter.

### B. Setting or Updating the Repository Display Name (`displayName`)
The name of the pipeline shown in the BigQuery Pipelines console is determined by the repository's `displayName` field (not a label). If this field is empty, the UI displays the pipeline as **"Untitled"**.

To set or update the display name, make a `PATCH` request to the Dataform API:

*   **Endpoint:** `PATCH https://dataform.googleapis.com/v1/projects/{project_id}/locations/{location}/repositories/{repository_id}?updateMask=displayName`
*   **Headers:**
    *   `Authorization: Bearer <GCP_ACCESS_TOKEN>`
    *   `Content-Type: application/json`
*   **Body:**
    ```json
    {
      "displayName": "Customer Churn Prediction Pipeline"
    }
    ```

---

## 2. Workspace Management via REST API

Dataform separates files and historical commits into **Workspaces**. Programmatic interactions must query, create, or port assets to these workspaces.

### REST Endpoints Reference (Base URL: `https://dataform.googleapis.com/v1/`)

#### Check Workspace Existence:
`GET projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}`

#### Create Workspace:
`POST projects/{project}/locations/{location}/repositories/{repository}/workspaces?workspaceId={workspace}`
- Body: `{}` (empty object)

---

## 3. Uploading and Committing Files

To upload local SQLX and YAML configuration files, use the `writeFile` custom REST verb. Once all files are uploaded, trigger a Git commit inside the workspace.

### Write File Endpoint
`POST projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}:writeFile`

*   **Content-Type:** `application/json`
*   **Payload Format:**
    ```json
    {
      "path": "definitions/silver_clientes.sqlx",
      "contents": "[BASE64_ENCODED_FILE_CONTENT]"
    }
    ```

### Commit Workspace Endpoint
`POST projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}:commit`

*   **Payload Format:**
    ```json
    {
      "commitMessage": "Deploying data transformation models",
      "author": {
        "name": "Data Agent Kit",
        "emailAddress": "admin@yourdomain.com"
      }
    }
    ```
    *(Note: Both name and emailAddress inside the author object are strictly required by the API).*

---

## 4. Compilation & Execution Orchestration

Running a Dataform pipeline programmatically requires a two-step handshake: **Compilation** followed by **Workflow Invocation**.

### Step A: Trigger Compilation Result
`POST projects/{project}/locations/{location}/repositories/{repository}/compilationResults`

*   **Payload Format:**
    ```json
    {
      "workspace": "projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}"
    }
    ```
*   **Response:** Captures the unique compilation name (e.g. `projects/.../compilationResults/{UUID}`).

### Step B: Trigger Workflow Invocation
`POST projects/{project}/locations/{location}/repositories/{repository}/workflowInvocations`

*   **Payload Format:**
    ```json
    {
      "compilationResult": "projects/{project}/locations/{location}/repositories/{repository}/compilationResults/{UUID}",
      "invocationConfig": {
        "serviceAccount": "[PROJECT_NUMBER]-compute@developer.gserviceaccount.com"
      }
    }
    ```

---

## 5. Resolving Strict Act-As Policies (IAM Configuration)

Because Dataform enforces strict security boundaries on query executions, triggering invocations requires passing a service account under `invocationConfig`. This introduces potential **Act-As permission denials**.

### Error Symptom:
If Dataform is misconfigured, workflow actions will instantly fail (under 0.5 seconds) with:
`service-[PROJECT_NUMBER]@gcp-sa-dataform.iam.gserviceaccount.com does not have permission to generate tokens for [PROJECT_NUMBER]-compute@developer.gserviceaccount.com, please grant Service Account Token Creator role.`

### Complete IAM Resolution Script:

1.  **Grant Service Account Token Creator on the Target Service Account:**
    The Dataform Service Agent must be allowed to impersonate and generate tokens for the target execution service account (e.g., Compute default service account).
    ```bash
    gcloud iam service-accounts add-iam-policy-binding [PROJECT_NUMBER]-compute@developer.gserviceaccount.com \
        --member="serviceAccount:service-[PROJECT_NUMBER]@gcp-sa-dataform.iam.gserviceaccount.com" \
        --role="roles/iam.serviceAccountTokenCreator" \
        --project="[PROJECT_ID]"
    ```

2.  **Grant Service Account User to Caller Identity:**
    The user or pipeline orchestrator executing the REST API calls must have the `Service Account User` role on the target execution service account.
    ```bash
    gcloud iam service-accounts add-iam-policy-binding [PROJECT_NUMBER]-compute@developer.gserviceaccount.com \
        --member="user:[CALLER_EMAIL_OR_SERVICE_ACCOUNT]" \
        --role="roles/iam.serviceAccountUser" \
        --project="[PROJECT_ID]"
    ```

3.  **Ensure Target Service Account has BigQuery Admin:**
    The execution service account must have full permissions to compile and write tables inside the BigQuery datasets.
    ```bash
    gcloud projects add-iam-policy-binding [PROJECT_ID] \
        --member="serviceAccount:[PROJECT_NUMBER]-compute@developer.gserviceaccount.com" \
        --role="roles/bigquery.admin"
    ```

---

## 6. Polling Execution State & Retrieving Errors

When workflow invocations are running, you poll the status. If an invocation has state `FAILED`, you must extract the exact query/action level failure details.

### Polling Endpoint
`GET projects/{project}/locations/{location}/repositories/{repository}/workflowInvocations/{workflow_invocation_id}`

*   Returns states such as `RUNNING`, `SUCCEEDED`, or `FAILED`.

### Retrieving Failed Actions & Compilation Logs
To extract detailed table-level error messages (e.g. invalid columns, dataset location mismatches, syntax errors):

> [!CAUTION]
> Do NOT append `/actions` or `/queryWorkflowInvocationActions` to the workflow path. The official REST API path uses the custom `:query` verb as a GET request.

`GET https://dataform.googleapis.com/v1/projects/{project_id}/locations/{location}/repositories/{repository_id}/workflowInvocations/{workflow_invocation_id}:query`

*   **Response Structure:** Contains an array of action results. Look for targets where `state` is `FAILED` and read the `failureReason` attribute to get the direct database exception.
