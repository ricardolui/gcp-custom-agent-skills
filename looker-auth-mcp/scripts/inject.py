#!/usr/bin/env python3
"""Looker & MCP Authentication Injector Helper Script.

Reads Looker credentials from active environment variables or .env file
and generates looker.ini, .env, .envrc, and IDE MCP snippets.
"""

import os
import sys

def load_env_file():
    """Load variables from .env if present in current or parent directory."""
    for path in [".env", "../.env", "../../.env"]:
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
            break

def main():
    load_env_file()
    
    base_url = os.environ.get("LOOKER_BASE_URL") or os.environ.get("LOOKERSDK_BASE_URL", "https://<YOUR_LOOKER_INSTANCE>.looker.app")
    client_id = os.environ.get("LOOKER_CLIENT_ID") or os.environ.get("LOOKERSDK_CLIENT_ID", "<YOUR_CLIENT_ID>")
    client_secret = os.environ.get("LOOKER_CLIENT_SECRET") or os.environ.get("LOOKERSDK_CLIENT_SECRET", "<YOUR_CLIENT_SECRET>")

    print("=== Looker & MCP Authentication Configuration ===")
    print(f"Target Base URL: {base_url}")
    print(f"Client ID:       {client_id[:4]}... (redacted)")

    # 1. Generate looker.ini
    ini_content = f"""[Looker]
base_url={base_url}
client_id={client_id}
client_secret={client_secret}
verify_ssl=true
"""
    with open("looker.ini", "w") as f:
        f.write(ini_content)
    print("✓ Successfully generated looker.ini")

    # 2. Print MCP Config Block
    snippet = f"""
========================================================================
To add Looker MCP to your IDE (Claude Desktop, VS Code, Cursor),
paste this block into your global mcp_config.json:

"looker-toolbox": {{
  "command": "npx",
  "args": ["-y", "@toolbox-sdk/server", "--prebuilt", "looker,looker-dev", "--stdio"],
  "env": {{
    "LOOKER_BASE_URL": "{base_url}",
    "LOOKER_CLIENT_ID": "{client_id}",
    "LOOKER_CLIENT_SECRET": "{client_secret}"
  }}
}}
========================================================================
"""
    print(snippet)

if __name__ == "__main__":
    main()
