# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import base64
import json
import os
import subprocess
import uuid
import urllib.request
import urllib.error

def get_access_token():
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode("utf-8").strip()
        return token
    except Exception as e:
        print(f"❌ Error obtaining access token from gcloud: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(
        description="Upload and commit a Jupyter Notebook to Google Cloud Dataform programmatically.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--mode", choices=["workspace", "emulated"], default="workspace",
                        help="Upload mode: 'workspace' commits to an existing repository/workspace; 'emulated' creates a native single-file-asset UUID repository natively integrated into Colab Enterprise 'My Notebooks'")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--location", default="us-central1", help="GCP Region/Location")
    parser.add_argument("--file", required=True, help="Local path to the .ipynb file")
    
    # Mode-specific parameters
    parser.add_argument("--repository", help="Dataform Repository ID / Notebook Asset ID (Required for 'workspace' mode, optional for 'emulated' mode to update an existing notebook asset)")
    parser.add_argument("--workspace", help="Dataform Workspace ID (Required for 'workspace' mode)")
    parser.add_argument("--remote-path", help="Destination path inside the workspace (defaults to filename, e.g. definitions/nb.ipynb. Only used in 'workspace' mode)")
    parser.add_argument("--display-name", help="Friendly display name shown in GCP console UI (Only used in 'emulated' mode; defaults to file name)")
    
    # Commit parameters
    parser.add_argument("--author-name", default="AI Assistant", help="Author name for the commit")
    parser.add_argument("--author-email", required=True, help="Author email address for the commit (Dataform strictly validates email formatting)")
    parser.add_argument("--commit-message", help="Custom commit message")

    args = parser.parse_args()

    # Basic validations
    if not os.path.exists(args.file):
        print(f"❌ Local file does not exist: {args.file}")
        exit(1)

    if args.mode == "workspace":
        if not args.repository or not args.workspace:
            print("❌ Error: Both '--repository' and '--workspace' are required when '--mode workspace' is selected.")
            exit(1)
    
    # 1. Read and encode local notebook
    try:
        with open(args.file, "rb") as f:
            file_bytes = f.read()
        b64_contents = base64.b64encode(file_bytes).decode("utf-8")
        print(f"📖 Loaded local file '{args.file}' ({len(file_bytes)} bytes) and encoded to Base64.")
    except Exception as e:
        print(f"❌ Failed to load local file: {e}")
        exit(1)

    # 2. Retrieve token
    token = get_access_token()
    if not token:
        exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-goog-user-project": args.project
    }

    # ================= WORKSPACE MODE =================
    if args.mode == "workspace":
        remote_path = args.remote_path if args.remote_path else os.path.basename(args.file)
        
        # 3a. Write File API
        write_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{args.repository}/workspaces/{args.workspace}:writeFile"
        write_payload = {
            "path": remote_path,
            "contents": b64_contents
        }

        print(f"📡 Uploading to Dataform Workspace: {args.workspace}/{remote_path}...")
        req_write = urllib.request.Request(
            write_url,
            data=json.dumps(write_payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req_write) as response:
                print("✅ File successfully written to workspace!")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to write file: {e.code} - {e.read().decode('utf-8')}")
            exit(1)
        except Exception as e:
            print(f"❌ Connection error during write: {e}")
            exit(1)

        # 4a. Commit API
        commit_msg = args.commit_message if args.commit_message else f"Upload {remote_path} via automated Dataform sync"
        commit_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{args.repository}/workspaces/{args.workspace}:commit"
        commit_payload = {
            "commitMessage": commit_msg,
            "author": {
                "name": args.author_name,
                "emailAddress": args.author_email
            }
        }

        print("📡 Committing workspace changes...")
        req_commit = urllib.request.Request(
            commit_url,
            data=json.dumps(commit_payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req_commit) as response:
                response.read()
                print(f"🎉 Workspace committed successfully! Notebook '{remote_path}' is now version-controlled and available under BigQuery Studio.")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to commit workspace changes: {e.code} - {e.read().decode('utf-8')}")
            exit(1)
        except Exception as e:
            print(f"❌ Connection error during commit: {e}")
            exit(1)

    # ================= EMULATED SINGLE-FILE-ASSET MODE =================
    elif args.mode == "emulated":
        # 1. Determine Display Name & Repo ID (UUID)
        display_name = args.display_name if args.display_name else os.path.splitext(os.path.basename(args.file))[0]
        
        is_update = False
        if args.repository:
            repo_id = args.repository
            is_update = True
            print(f"\n🔄 Updating Existing Emulated Single-File Asset...")
            print(f"📦 Existing Repo/Asset ID (UUID): {repo_id}")
        else:
            repo_id = str(uuid.uuid4())
            print(f"\n🚀 Creating Emulated Single-File Asset Repository...")
            print(f"🧬 Generated Repo UUID: {repo_id}")
            print(f"🏷️ Display Name: {display_name}")

        workspace_id = "default-workspace"
        
        # 2. Create the Dataform Repository with native notebook labels (Only if NOT an update)
        if not is_update:
            create_repo_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories?repositoryId={repo_id}"
            repo_payload = {
                "labels": {
                    "single-file-asset-type": "notebook"
                },
                "displayName": display_name
            }
            
            print("📡 Creating Dataform repository with label 'single-file-asset-type: notebook'...")
            req_repo = urllib.request.Request(
                create_repo_url,
                data=json.dumps(repo_payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            
            try:
                with urllib.request.urlopen(req_repo) as res:
                    res_data = json.loads(res.read().decode("utf-8"))
                    print(f"✅ Repository created: {res_data.get('name')}")
            except urllib.error.HTTPError as e:
                print(f"❌ Failed to create repo: {e.code} - {e.read().decode('utf-8')}")
                exit(1)
            
        # 3. Create a temporary developer workspace
        create_ws_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{repo_id}/workspaces?workspaceId={workspace_id}"
        print(f"📡 Creating temporary workspace '{workspace_id}'...")
        req_ws = urllib.request.Request(
            create_ws_url,
            data=json.dumps({}).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req_ws) as res:
                print("✅ Temporary workspace created successfully!")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to create workspace: {e.code} - {e.read().decode('utf-8')}")
            exit(1)
            
        # 4. Write content to 'content.ipynb' inside the workspace (Hardcoded filename required by Colab UI)
        write_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{repo_id}/workspaces/{workspace_id}:writeFile"
        write_payload = {
            "path": "content.ipynb",
            "contents": b64_contents
        }
        
        print("📡 Writing notebook content to 'content.ipynb'...")
        req_write = urllib.request.Request(
            write_url,
            data=json.dumps(write_payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req_write) as res:
                print("✅ File 'content.ipynb' written successfully!")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to write file: {e.code} - {e.read().decode('utf-8')}")
            exit(1)
            
        # 5. Commit the workspace changes
        commit_msg = args.commit_message if args.commit_message else f"Initial commit of emulated notebook: {display_name}"
        commit_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{repo_id}/workspaces/{workspace_id}:commit"
        commit_payload = {
            "commitMessage": commit_msg,
            "author": {
                "name": args.author_name,
                "emailAddress": args.author_email
            }
        }
        
        print("📡 Committing workspace changes...")
        req_commit = urllib.request.Request(
            commit_url,
            data=json.dumps(commit_payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req_commit) as res:
                res.read()
                print("✅ Workspace committed successfully!")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to commit changes: {e.code} - {e.read().decode('utf-8')}")
            exit(1)

        # 6. Push the committed changes to the repository's default branch (CRITICAL STEP)
        push_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{repo_id}/workspaces/{workspace_id}:push"
        print("📡 Pushing workspace changes to remote repository default branch...")
        req_push = urllib.request.Request(
            push_url,
            data=json.dumps({}).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req_push) as res:
                res.read()
                print("✅ Changes pushed successfully to remote branch!")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to push changes to remote: {e.code} - {e.read().decode('utf-8')}")
            exit(1)
            
        # 7. Delete the workspace to clean up (leaving 0 active workspaces, matching native Colab behavior)
        delete_ws_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{repo_id}/workspaces/{workspace_id}"
        print(f"📡 Deleting temporary workspace '{workspace_id}'...")
        req_delete = urllib.request.Request(
            delete_ws_url,
            headers=headers,
            method="DELETE"
        )
        
        try:
            with urllib.request.urlopen(req_delete) as res:
                print("✅ Temporary workspace deleted! Asset is now finalized and clean.")
        except urllib.error.HTTPError as e:
            print(f"❌ Failed to delete workspace: {e.code} - {e.read().decode('utf-8')}")
            exit(1)

        print("\n✨========================================================================✨")
        print(f"🎉 SUCCESS: Single-File Notebook Asset Emulated Successfully!")
        print(f"📦 Repository/Asset ID (UUID): {repo_id}")
        print(f"🏷️ Notebook Title: {display_name}")
        print(f"🗺️ Region/Location: {args.location}")
        print(f"💡 This notebook is now IMMEDIATELY visible in Colab Enterprise / BigQuery Studio!")
        print("✨========================================================================✨\n")

if __name__ == "__main__":
    main()
