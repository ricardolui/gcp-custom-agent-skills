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
        description="Download/Pull a Jupyter Notebook from Google Cloud BigQuery Notebooks (Colab Enterprise) back to your local filesystem.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--location", default="us-central1", help="GCP Region/Location")
    parser.add_argument("--repository", required=True, help="Notebook Asset ID / Repository ID (UUID)")
    parser.add_argument("--file", required=True, help="Local file path where the notebook should be saved")

    args = parser.parse_args()

    # 1. Retrieve access token
    token = get_access_token()
    if not token:
        exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-goog-user-project": args.project
    }

    # 2. Construct Repository readFile URL
    # Colab Enterprise/BigQuery Studio stores single-file assets as 'content.ipynb'
    remote_path = "content.ipynb"
    read_url = f"https://dataform.googleapis.com/v1beta1/projects/{args.project}/locations/{args.location}/repositories/{args.repository}:readFile?path={remote_path}"

    print(f"\n📡 Pulling Notebook Asset from Google Cloud...")
    print(f"📦 Repo/Asset ID (UUID): {args.repository}")
    print(f"🌐 Location: {args.location}")
    print(f"📄 Target File inside Repo: {remote_path}")

    req = urllib.request.Request(
        read_url,
        headers=headers,
        method="GET"
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            b64_contents = res_data.get("contents")
            if not b64_contents:
                print("❌ Error: Received empty file contents from Google Cloud API.")
                exit(1)
            
            notebook_bytes = base64.b64decode(b64_contents)
            
            # Validate JSON before saving to protect against corrupt files
            try:
                json.loads(notebook_bytes.decode("utf-8"))
            except Exception as je:
                print(f"❌ Error: Downloaded content is not a valid Jupyter Notebook JSON: {je}")
                exit(1)

            # 3. Save to local file
            local_dir = os.path.dirname(os.path.abspath(args.file))
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
                
            with open(args.file, "wb") as f:
                f.write(notebook_bytes)
                
            print(f"💾 File successfully downloaded and saved to: {args.file} ({len(notebook_bytes)} bytes)")
            print("\n✨========================================================================✨")
            print("🎉 SUCCESS: Notebook synchronized from GCP to Local environment successfully!")
            print("✨========================================================================✨\n")

    except urllib.error.HTTPError as e:
        print(f"❌ Failed to download file from Dataform: {e.code} - {e.read().decode('utf-8')}")
        exit(1)
    except Exception as e:
        print(f"❌ Connection error during download: {e}")
        exit(1)

if __name__ == "__main__":
    main()
