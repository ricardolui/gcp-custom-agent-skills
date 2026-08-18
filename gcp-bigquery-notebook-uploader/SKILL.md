---
name: gcp-bigquery-notebook-uploader
description: Uploads and commits Jupyter Notebook (.ipynb) files programmatically into Google Cloud Dataform repositories and workspaces, making them natively accessible as Code Assets inside BigQuery Studio / Colab Enterprise, with support for emulating native single-file-assets.
---

# GCP Notebook Dataform Uploader & Emulator

This skill provides a programmatic, automated workflow to upload, sync, and commit Jupyter Notebooks (`.ipynb`) directly into **Google Cloud Dataform**. It supports two distinct operational modes:

1.  **Workspace Mode (`--mode workspace`)**: Writes and commits notebooks directly into an existing Dataform development workspace (useful for standard Dataform/Git pipelines).
2.  **Emulated Single-File-Asset Mode (`--mode emulated`)**: Programmatically replicates Colab Enterprise & BigQuery Studio's internal asset creation engine. It automatically provisions a dedicated UUID-based Dataform repository, tags it with `"single-file-asset-type": "notebook"`, commits and pushes the notebook as `content.ipynb`, and deletes the temporary workspace—making the notebook **instantly and natively visible** in the Google Cloud Console's notebook catalog.

---

## 🛠️ Reusable Python Automation CLI

The skill contains a dependency-free, robust Python 3 CLI script that wraps all required REST API operations.

### Script Path
[`scripts/upload_notebook.py`](scripts/upload_notebook.py)

### How to Execute (Workspace Mode)

Committed to an existing repository and workspace:

```bash
python3 scripts/upload_notebook.py \
  --mode "workspace" \
  --project "<PROJECT_ID>" \
  --location "us-central1" \
  --repository "<REPO_ID>" \
  --workspace "<WORKSPACE_ID>" \
  --file "/path/to/local/notebook.ipynb" \
  --author-email "<AUTHOR_EMAIL_OR_SERVICE_ACCOUNT>"
```

### How to Execute (Emulated Single-File-Asset Mode) ⭐

Creates a brand-new, natively integrated Colab/BigQuery Studio Notebook:

```bash
python3 scripts/upload_notebook.py \
  --mode "emulated" \
  --project "<PROJECT_ID>" \
  --location "us-central1" \
  --file "/path/to/local/notebook.ipynb" \
  --display-name "Interactive PySpark Demo" \
  --author-email "<AUTHOR_EMAIL_OR_SERVICE_ACCOUNT>"
```

### How to Update an Existing Emulated Notebook Asset 🔄

If you want to update an existing notebook without creating a duplicate asset, pass the existing asset UUID into the `--repository` parameter:

```bash
python3 scripts/upload_notebook.py \
  --mode "emulated" \
  --project "<PROJECT_ID>" \
  --location "us-central1" \
  --repository "<EXISTING_ASSET_UUID>" \
  --file "/path/to/local/notebook.ipynb" \
  --author-email "<AUTHOR_EMAIL_OR_SERVICE_ACCOUNT>"
```

### How to Sync Changes Back to Local (Pull Mode) 📥

If you or a colleague made changes directly inside the BigQuery Notebooks (Colab Enterprise) UI and you want to pull those changes back to your local filesystem, use the companion download script:

```bash
python3 scripts/download_notebook.py \
  --project "<PROJECT_ID>" \
  --location "us-central1" \
  --repository "<EXISTING_ASSET_UUID>" \
  --file "/path/to/local/notebook.ipynb"
```

---

## 📋 CLI Parameter Reference

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `--mode` | `workspace` | Either `workspace` (standard) or `emulated` (Colab UI bypass). |
| `--project` | *Required* | The Google Cloud Project ID. |
| `--location` | `us-central1` | The target GCP region. |
| `--file` | *Required* | Full absolute path to your local Jupyter Notebook `.ipynb` file. |
| `--repository` | *N/A* | Dataform Repository ID (Strictly required in `workspace` mode). |
| `--workspace` | *N/A* | Dataform Workspace ID (Strictly required in `workspace` mode). |
| `--remote-path`| *Basename* | Destination filename inside the workspace (defaults to local file basename, only used in `workspace` mode). |
| `--display-name`| *Basename* | Friendly display name shown in the Cloud Console UI (only used in `emulated` mode). |
| `--author-name`| `AI Assistant`| Commit author display name. |
| `--author-email`| *Required* | Commit author email address (strictly validated by Dataform). |
| `--commit-message`| *N/A* | Custom commit description message. |

---

## 📡 REST API Reference (The Core Logic)

If executing directly via API requests, the workflows are structured as follows:

### 1. Repository Creation with Special Tags (Emulated Mode Only)
*   **HTTP Method**: `POST`
*   **URL**: `https://dataform.googleapis.com/v1beta1/projects/{project}/locations/{location}/repositories?repositoryId={UUID}`
*   **Payload JSON**:
    ```json
    {
      "labels": {
        "single-file-asset-type": "notebook"
      },
      "displayName": "My Native Notebook Name"
    }
    ```

### 2. Write File to Development Workspace
Writes the file inside a temporary development workspace (always writes to `content.ipynb` in `emulated` mode).
*   **HTTP Method**: `POST`
*   **URL**: `https://dataform.googleapis.com/v1beta1/projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}:writeFile`
*   **Payload JSON**:
    ```json
    {
      "path": "content.ipynb",
      "contents": "<BASE64_ENCODED_NOTEBOOK_BYTES>"
    }
    ```

### 3. Commit Workspace Changes
*   **HTTP Method**: `POST`
*   **URL**: `https://dataform.googleapis.com/v1beta1/projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}:commit`
*   **Payload JSON**:
    ```json
    {
      "commitMessage": "Initial commit",
      "author": {
        "name": "Commit Author Name",
        "emailAddress": "author-email@project.iam.gserviceaccount.com"
      }
    }
    ```

### 4. Push Workspace Changes (CRITICAL STEP)
Synchronizes the workspace's local commit with the repository's main/default branch. Without this step, deleting the workspace deletes the changes.
*   **HTTP Method**: `POST`
*   **URL**: `https://dataform.googleapis.com/v1beta1/projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}:push`
*   **Payload JSON**: `{}` *(Empty JSON block required)*

### 5. Workspace Clean-up (Emulated Mode Only)
Deletes the workspace, leaving the repository with 0 workspaces, mirroring native GCP-created notebooks.
*   **HTTP Method**: `DELETE`
*   **URL**: `https://dataform.googleapis.com/v1beta1/projects/{project}/locations/{location}/repositories/{repository}/workspaces/{workspace}`

---

## 💎 Best Practices

1.  **ADC and Authentication**: Ensure you are authenticated with active credentials (`gcloud auth application-default login` or active token retrieval with `gcloud auth print-access-token`) and that your identity has the `roles/dataform.editor` role on the target repository.
2.  **No Extra Libraries**: The `upload_notebook.py` script relies solely on Python's built-in `urllib` to guarantee immediate compatibility inside shell sandboxes.
3.  **Cross-Project Billing**: Always specify the billing project via the `x-goog-user-project` header when performing programmatic API requests.
