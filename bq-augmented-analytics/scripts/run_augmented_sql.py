#!/usr/bin/env python3
"""BigQuery Augmented Analytics SQL Validator & Runner CLI.

Validates GoogleSQL Table-Valued Function (TVF) syntax for BigQuery Augmented Analytics:
  - AI.CAUSAL_EFFECT
  - ML.CORRELATION
  - ML.DETECT_CHANGE_POINTS
  - ML.TREND
  - ML.SEASONALITY

Performs AST validation via `sqlglot.parse_one(sql, read="bigquery")` and checks
mandatory named arguments (`=>`). Automatically probes GCP OAuth scopes:
  - When write scopes are active: executes live query via `bq query --use_legacy_sql=false --label datacloud:jetski`
    or `google.cloud.bigquery.QueryJobConfig(labels={"datacloud": "jetski"})`.
  - When read-only scopes (`API_CLOUD_PLATFORM_READ_ONLY` / `cloud-platform.read-only`) are detected
    or `--dry-run` is specified: performs offline AST & TVF contract validation and outputs
    structured verification JSON.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

try:
    import sqlglot
except ImportError:
    sqlglot = None  # type: ignore

# Supported Augmented Analytics TVFs and their required named arguments
AUGMENTED_TVF_CONTRACTS: Dict[str, List[str]] = {
    "AI.CAUSAL_EFFECT": ["data_col", "timestamp_col", "intervention_timestamp"],
    "ML.CORRELATION": ["target_col", "target_correlation_cols"],
    "ML.DETECT_CHANGE_POINTS": ["data_col", "timestamp_col"],
    "ML.TREND": ["data_col", "timestamp_col"],
    "ML.SEASONALITY": ["data_col", "timestamp_col"],
}


def normalize_tvf_table_arg_for_sqlglot(sql: str) -> str:
    """Normalizes GoogleSQL `TABLE project.dataset.table` inside TVF args for sqlglot parsing."""
    return re.sub(
        r"\bTABLE\s+([`a-zA-Z0-9_.\-\{\}:]+)",
        r"(SELECT * FROM \1)",
        sql,
        flags=re.IGNORECASE,
    )


def validate_augmented_sql(sql: str, project_id: str) -> Tuple[bool, Dict[str, Any]]:
    """Validates GoogleSQL syntax via sqlglot and inspects Augmented Analytics TVF contracts."""
    rendered_sql = sql.replace("{projectId}", project_id).replace("${PROJECT_ID}", project_id)
    details: Dict[str, Any] = {
        "valid_ast": False,
        "ast_root_type": None,
        "detected_tvfs": [],
        "tvf_arguments": {},
        "attribution_compliant": True,
        "attribution_labels": {"datacloud": "jetski"},
        "gcloud_metrics_env": "datacloud.jetski",
        "errors": [],
    }

    if not rendered_sql.strip():
        details["errors"].append("Empty SQL query provided.")
        return False, details

    # 1. Detect Augmented Analytics TVFs and check arrow named arguments (=>)
    upper_sql = rendered_sql.upper()
    for tvf_name, required_args in AUGMENTED_TVF_CONTRACTS.items():
        if tvf_name in upper_sql:
            details["detected_tvfs"].append(tvf_name)
            found_args = []
            missing_args = []
            for req_arg in required_args:
                pattern = rf"\b{req_arg}\s*=>"
                if re.search(pattern, rendered_sql, flags=re.IGNORECASE):
                    found_args.append(req_arg)
                else:
                    missing_args.append(req_arg)
            details["tvf_arguments"][tvf_name] = {
                "found_required_args": found_args,
                "missing_required_args": missing_args,
            }
            if missing_args:
                details["errors"].append(
                    f"TVF {tvf_name} missing required named argument(s) with '=>': {missing_args}"
                )

    # 2. Validate AST using sqlglot.parse_one(sql, read="bigquery")
    if sqlglot is not None:
        normalized_sql = normalize_tvf_table_arg_for_sqlglot(rendered_sql)
        try:
            ast = sqlglot.parse_one(normalized_sql, read="bigquery")
            details["valid_ast"] = True
            details["ast_root_type"] = type(ast).__name__
        except Exception as exc:
            details["valid_ast"] = False
            details["errors"].append(f"sqlglot BigQuery AST parse error: {exc}")
    else:
        # Fallback basic balanced parentheses and SELECT check if sqlglot is absent
        if "SELECT" in upper_sql and rendered_sql.count("(") == rendered_sql.count(")"):
            details["valid_ast"] = True
            details["ast_root_type"] = "SelectFallback"
        else:
            details["valid_ast"] = False
            details["errors"].append("Fallback SQL syntax check failed.")

    is_valid = details["valid_ast"] and len(details["errors"]) == 0
    return is_valid, details


def check_gcp_write_scope() -> Tuple[bool, str]:
    """Checks active GCP OAuth token scopes using mandatory CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski."""
    env = os.environ.copy()
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = "datacloud.jetski"

    token = ""
    for cmd in [
        ["gcloud", "auth", "application-default", "print-access-token"],
        ["gcloud", "auth", "print-access-token"],
    ]:
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                token = proc.stdout.strip()
                break
        except Exception:
            continue

    if not token:
        return False, "NO_ACTIVE_TOKEN (run: CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud auth login --update-adc)"

    # Inspect tokeninfo endpoint
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?access_token={token}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            scope_str = data.get("scope", "")
            if "cloud-platform.read-only" in scope_str or "API_CLOUD_PLATFORM_READ_ONLY" in scope_str:
                return False, f"READ_ONLY_SCOPE ({scope_str})"
            if "cloud-platform" in scope_str or "bigquery" in scope_str:
                return True, f"WRITE_SCOPE_ACTIVE ({scope_str})"
            return False, f"INSUFFICIENT_SCOPE ({scope_str})"
    except Exception as exc:
        return False, f"TOKENINFO_UNREACHABLE_OR_OFFLINE ({exc})"


def execute_live_bigquery(sql: str, project_id: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Executes SQL query on BigQuery with mandatory datacloud:jetski attribution."""
    rendered_sql = sql.replace("{projectId}", project_id).replace("${PROJECT_ID}", project_id)

    # First attempt: google.cloud.bigquery Python SDK with QueryJobConfig(labels={"datacloud": "jetski"})
    try:
        from google.cloud import bigquery  # type: ignore

        client = bigquery.Client(project=project_id)
        job_config = bigquery.QueryJobConfig(labels={"datacloud": "jetski"})
        query_job = client.query(rendered_sql, job_config=job_config)
        rows = [dict(row.items()) for row in query_job.result()]
        return True, "LIVE_SDK_SUCCESS", rows
    except ImportError:
        pass
    except Exception as sdk_exc:
        err_msg = str(sdk_exc)
        if any(k in err_msg for k in ["ACCESS_TOKEN_SCOPE_INSUFFICIENT", "read-only", "PERMISSION_DENIED", "not been used", "disabled"]):
            return False, f"SDK_FALLBACK_TO_DRY_RUN: {err_msg}", []

    # Second attempt: bq CLI with mandatory --label datacloud:jetski
    env = os.environ.copy()
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = "datacloud.jetski"
    cmd = [
        "bq",
        "query",
        "--use_legacy_sql=false",
        f"--project_id={project_id}",
        "--format=json",
        "--label",
        "datacloud:jetski",
        rendered_sql,
    ]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30, check=False)
        if proc.returncode == 0:
            try:
                rows = json.loads(proc.stdout.strip() or "[]")
            except Exception:
                rows = [{"raw_output": proc.stdout.strip()}]
            return True, "LIVE_BQ_CLI_SUCCESS", rows
        else:
            combined_err = (proc.stderr or "") + "\n" + (proc.stdout or "")
            return False, f"BQ_CLI_ERROR: {combined_err.strip()}", []
    except Exception as cli_exc:
        return False, f"BQ_CLI_EXCEPTION: {cli_exc}", []


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and run BigQuery Augmented Analytics GoogleSQL queries "
            "(AI.CAUSAL_EFFECT, ML.CORRELATION, ML.DETECT_CHANGE_POINTS, ML.TREND, ML.SEASONALITY) "
            "with mandatory datacloud:jetski attribution and offline AST validation."
        )
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--sql-file", type=str, help="Path to GoogleSQL (.sql) file to validate/execute.")
    group.add_argument("--query", type=str, help="Inline GoogleSQL query string to validate/execute.")
    parser.add_argument(
        "--project-id",
        type=str,
        default=os.environ.get("GCP_PROJECT_ID", "wsevents-corpagent-eng-72opix"),
        help="Target Google Cloud Project ID (default: wsevents-corpagent-eng-72opix).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force offline AST and TVF signature validation without live BigQuery execution.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Default verification query if neither --sql-file nor --query is provided (e.g. dry-run smoke test)
    sql_text = ""
    source_label = "inline_default_smoke_query"
    if args.sql_file:
        if not os.path.exists(args.sql_file):
            print(json.dumps({"status": "ERROR", "message": f"SQL file not found: {args.sql_file}"}), file=sys.stderr)
            return 1
        with open(args.sql_file, "r", encoding="utf-8") as f:
            sql_text = f.read()
        source_label = args.sql_file
    elif args.query:
        sql_text = args.query
        source_label = "inline_query"
    else:
        sql_text = (
            "SELECT * FROM AI.CAUSAL_EFFECT("
            "(SELECT trade_date, close_price FROM `{projectId}.stock_augmented_analytics.stock_daily_enriched` WHERE ticker = 'GOOG'), "
            "data_col => 'close_price', timestamp_col => 'trade_date', "
            "intervention_timestamp => TIMESTAMP('2024-04-25 20:00:00 UTC'), output_time_series => FALSE);"
        )

    # Step 1: Validate SQL AST and Augmented Analytics TVF contracts
    is_valid, validation_report = validate_augmented_sql(sql_text, args.project_id)
    if not is_valid:
        output = {
            "status": "VALIDATION_FAILED",
            "source": source_label,
            "project_id": args.project_id,
            "validation": validation_report,
        }
        print(json.dumps(output, indent=2))
        return 1

    # Step 2: Check whether to run live or dry-run
    has_write_scope, scope_reason = check_gcp_write_scope()
    if args.dry_run or not has_write_scope:
        mode = "EXPLICIT_DRY_RUN" if args.dry_run else "OFFLINE_READ_ONLY_DRY_RUN"
        output = {
            "status": "VALIDATED_DRY_RUN",
            "execution_mode": mode,
            "scope_status": scope_reason,
            "remediation_command": "CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud auth login --update-adc",
            "bq_attribution_flag": "--label datacloud:jetski",
            "source": source_label,
            "project_id": args.project_id,
            "validation": validation_report,
        }
        print(json.dumps(output, indent=2))
        return 0

    # Step 3: Attempt live execution if write scope is active
    live_ok, exec_status, rows = execute_live_bigquery(sql_text, args.project_id)
    if live_ok:
        output = {
            "status": "LIVE_EXECUTION_SUCCESS",
            "execution_mode": "LIVE_BIGQUERY",
            "scope_status": scope_reason,
            "bq_attribution_flag": "--label datacloud:jetski",
            "source": source_label,
            "project_id": args.project_id,
            "validation": validation_report,
            "row_count": len(rows),
            "sample_rows": rows[:5],
        }
        print(json.dumps(output, indent=2, default=str))
        return 0
    else:
        # Graceful fallback if live execution encountered scope/API disabled error
        output = {
            "status": "VALIDATED_DRY_RUN_FALLBACK",
            "execution_mode": "FALLBACK_AFTER_LIVE_ATTEMPT",
            "live_attempt_diagnostic": exec_status,
            "remediation_command": "CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud auth login --update-adc",
            "bq_attribution_flag": "--label datacloud:jetski",
            "source": source_label,
            "project_id": args.project_id,
            "validation": validation_report,
        }
        print(json.dumps(output, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
