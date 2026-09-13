#!/usr/bin/env python3
"""
Verification script for Google Cloud Pub/Sub -> BigQuery Managed Iceberg streaming parity.
Validates row counts, metadata column completeness, and zero NULL constraints.

Usage:
  python3 verify_pubsub_iceberg_parity.py \
    --project_id blip-dpl-prd-sam-i-plt-str-0 \
    --dataset raw_platform_pubsub \
    --table imt_segment \
    --expected_signature seq-blipprod \
    --expected_namespace da-seq-eventhub
"""

import argparse
import os
import subprocess
import sys

def get_token(impersonate_sa=None):
    cmd = ["gcloud", "auth", "print-access-token"]
    if impersonate_sa:
        cmd.append(f"--impersonate-service-account={impersonate_sa}")
    env = os.environ.copy()
    env["CLOUDSDK_ACTIVE_CONFIG_NAME"] = os.environ.get("CLOUDSDK_ACTIVE_CONFIG_NAME", "blip")
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = "datacloud.jetski"
    res = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    return res.stdout.strip()

def main():
    parser = argparse.ArgumentParser(description="Verify Pub/Sub to BigQuery Iceberg metadata parity.")
    parser.add_argument("--project_id", default="blip-dpl-prd-sam-i-plt-str-0", help="GCP Project ID")
    parser.add_argument("--dataset", default="raw_platform_pubsub", help="BigQuery Dataset ID")
    parser.add_argument("--table", required=True, help="BigQuery Table Name")
    parser.add_argument("--expected_signature", required=True, help="Expected _meta_source_signature value")
    parser.add_argument("--expected_namespace", required=True, help="Expected _meta_namespace value")
    parser.add_argument("--impersonate_sa", default="blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com")
    args = parser.parse_args()

    token = get_token(args.impersonate_sa)
    env = os.environ.copy()
    env["CLOUDSDK_ACTIVE_CONFIG_NAME"] = "blip"
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = "datacloud.jetski"

    query = f"""
    SELECT 
      '{args.table}' as table_name,
      count(*) as total_rows,
      countif(_meta_source_signature = '{args.expected_signature}') as with_correct_sig,
      countif(_meta_namespace = '{args.expected_namespace}') as with_correct_ns,
      countif(_meta_enqueued_time IS NOT NULL) as with_enqueued,
      countif(_meta_ingestion_time IS NOT NULL) as with_ingestion,
      countif(_meta_partition_id IS NOT NULL) as with_partition,
      countif(_meta_sequence_number IS NOT NULL) as with_seq
    FROM `{args.project_id}.{args.dataset}.{args.table}`
    """

    cmd = [
        "bq", "query", "--use_legacy_sql=false",
        f"--oauth_access_token={token}",
        f"--project_id={args.project_id}",
        query
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        print(f"Error executing query: {res.stderr}", file=sys.stderr)
        sys.exit(1)

    print(res.stdout)

if __name__ == "__main__":
    main()
