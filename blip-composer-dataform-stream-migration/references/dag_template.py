# -*- coding: utf-8 -*-
"""
DAG Template: Pure Incremental Dataform Routine (Dataflow Eliminated)
Target: Google Cloud Composer (Airflow 2.x)
Repository: gcp-dpl-dataform-blip-stream-ingestion

Usage:
  1. Replace `<ENTITY_UPPERCASE>`, `<entity_lowercase>`, and `<silver_schema>`.
  2. For Phase A/B, set schema_suffix='__kfkconn_test'.
  3. Post-validation, set schema_suffix='' and git_commitish='main'.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup
from airflow.providers.google.cloud.operators.dataform import (
    DataformCreateCompilationResultOperator,
    DataformCreateWorkflowInvocationOperator,
)

# Constants & Configuration
DAG_ID = "ING_EVH_KAFKA_<ENTITY_UPPERCASE>_KFKCONN"
PROJECT_ID = "blip-dpl-prd-sam-i-plt-str-0"
LOCATION = "southamerica-east1"
REPOSITORY_ID = "gcp-dpl-dataform-blip-stream-ingestion"
IMPERSONATION_SA = "blip-dpl-prd-sam-ingestion@blip-dpl-prd-sam-i-plt-str-0.iam.gserviceaccount.com"
INCLUDED_TAGS = ["<entity_tag>"]

default_args = {
    "owner": "data-engineers",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    schedule_interval="40 0 * * *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    max_active_runs=1,
    tags=["kfkconn", "incremental", "dataform", "<domain>"],
) as dag:

    start_task = EmptyOperator(task_id="start_incremental_routine")
    end_task = EmptyOperator(task_id="end_dag")

    with TaskGroup(group_id="<entity_lowercase>_silver") as tg:
        with TaskGroup(group_id="<entity_lowercase>_dataform_group") as df_group:
            create_compilation = DataformCreateCompilationResultOperator(
                task_id="create_compilation",
                project_id=PROJECT_ID,
                region=LOCATION,
                repository_id=REPOSITORY_ID,
                compilation_result={
                    "git_commitish": "main",  # or 'feat/kfkconn-...' during pilot
                    "code_compilation_config": {
                        "vars": {
                            "project_id": PROJECT_ID,
                            "raw_source_dataset": "raw_platform_kfkconn",
                            "schema_suffix": "",  # '__kfkconn_test' for shadow A/B phase
                            "REGION": "sam",
                            "ENV": "prd",
                        },
                    },
                },
                impersonation_chain=IMPERSONATION_SA,
            )

            create_invocation = DataformCreateWorkflowInvocationOperator(
                task_id="create_invocation",
                project_id=PROJECT_ID,
                region=LOCATION,
                repository_id=REPOSITORY_ID,
                workflow_invocation={
                    "compilation_result": (
                        "{{ task_instance.xcom_pull(task_ids='"
                        + "<entity_lowercase>_silver.<entity_lowercase>_dataform_group.create_compilation"
                        + "')['name'] }}"
                    ),
                    "invocation_config": {
                        "service_account": IMPERSONATION_SA,
                        "included_tags": INCLUDED_TAGS,
                        "transitive_dependencies_included": False,
                        "fully_refresh_incremental_tables_enabled": False,
                    },
                },
                impersonation_chain=IMPERSONATION_SA,
            )

            create_compilation >> create_invocation

    start_task >> tg >> end_task
