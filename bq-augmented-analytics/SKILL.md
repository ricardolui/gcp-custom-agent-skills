---
name: bq-augmented-analytics
description: Use when building, querying, validating, or provisioning BigQuery Augmented Analytics SQL pipelines (AI.CAUSAL_EFFECT, ML.CORRELATION, ML.DETECT_CHANGE_POINTS, ML.TREND, ML.SEASONALITY) or Conversational Analytics Data Agents grounded on time-series and financial datasets.
license: Apache-2.0
metadata:
  version: "1.0.0"
  publisher: "google"
---

# BigQuery Augmented Analytics & Conversational Data Agents (`bq-augmented-analytics`)

## Overview

BigQuery Augmented Analytics provides five native GoogleSQL Table-Valued Functions (TVFs) for automated statistical discovery, causal inference, correlation analysis, structural breakpoint detection, and time-series decomposition directly inside BigQuery without manual ML model lifecycle management (`CREATE MODEL`).

**Core Architectural Principles:**
1. **Namespace Disambiguation**: Causal inference uses the `AI.*` namespace (`AI.CAUSAL_EFFECT`), whereas multi-dimensional correlation and time-series structural decomposition strictly use the `ML.*` namespace (`ML.CORRELATION`, `ML.DETECT_CHANGE_POINTS`, `ML.TREND`, `ML.SEASONALITY`).
2. **TVF Input Contract**: Every function takes a positional first argument `{ TABLE project.dataset.table | (SELECT ... subquery) }` followed by named arguments using the GoogleSQL arrow operator (`arg_name => value`). When passing a table identifier directly, the `TABLE` keyword is mandatory; subqueries must be enclosed in parentheses `(SELECT ...)`.
3. **Dual-Mode Auth & Network Resilience**: Automation scripts and runners automatically probe active Google Cloud OAuth scopes (`gcloud auth application-default print-access-token` / `tokeninfo`). When full write scopes (`cloud-platform` or `bigquery`) are active, queries execute live on BigQuery; when running under read-only scopes (`API_CLOUD_PLATFORM_READ_ONLY` / `cloud-platform.read-only`), tools seamlessly switch to **Offline Verification & Dry-Run AST Validation Mode** using `sqlglot` (`read="bigquery"`) and statistical validation.
4. **Mandatory Resource Attribution**: Every `gcloud` command MUST be prefixed with `CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski` (dot separator). Every mutating or job-creating `bq` command (`query`, `load`, `extract`, `mk`, `update`, `cp`) MUST include `--label datacloud:jetski` (colon separator). Never pass `--label` to read-only `bq` commands (`ls`, `show`, `head`, `rm`, `cancel`, `version`).

---

## Quick Reference: The 5 Augmented Analytics TVFs

| TVF Name | Namespace | Purpose | Required Named Arguments | Key Output Columns |
|---|---|---|---|---|
| `AI.CAUSAL_EFFECT` | `AI` | Post-intervention causal impact (`ARIMA_PLUS` counterfactual) | `data_col`, `timestamp_col`, `intervention_timestamp` | `p_value`, `prob_causal_effect`, `absolute_effect`, `relative_effect`, `status` (+ pointwise cols if `output_time_series => TRUE`) |
| `ML.CORRELATION` | `ML` | Multi-dimensional correlation matrix across `GROUP BY CUBE` | `target_col`, `target_correlation_cols` | `segment`, `[*dimension_cols]`, `target_col`, `corr_col`, `correlation`, `segment_size`, `segment_proportion` |
| `ML.DETECT_CHANGE_POINTS` | `ML` | Structural regime shifts & level change windows | `data_col`, `timestamp_col` | `[*id_cols]`, `begin_timestamp`, `end_timestamp`, `metrics` (`STRUCT<avg, min, max, stddev, count>`), `status` |
| `ML.TREND` | `ML` | Long-term directional trend extraction & forecast | `data_col`, `timestamp_col` | `[*id_cols]`, `<timestamp_col>`, `time_series_type`, `<data_col>`, `trend`, `status` |
| `ML.SEASONALITY` | `ML` | Cyclical/periodic seasonal decomposition | `data_col`, `timestamp_col` | `[*id_cols]`, `<timestamp_col>`, `time_series_type`, `<data_col>`, `yearly`, `quarterly`, `monthly`, `weekly`, `daily`, `status` |

---

## Detailed TVF Specifications & Output Schemas

### 1. `AI.CAUSAL_EFFECT`

Quantifies the causal impact of a specific event or intervention on a time series by training an `ARIMA_PLUS` counterfactual baseline on pre-intervention observations and comparing it against post-intervention actuals.

#### Exact GoogleSQL Syntax
```sql
SELECT *
FROM AI.CAUSAL_EFFECT(
  { TABLE project_id.dataset_id.table_name | (query_statement) },
  data_col => 'data_col_name',
  timestamp_col => 'timestamp_col_name',
  intervention_timestamp => TIMESTAMP('YYYY-MM-DD HH:MM:SS UTC') -- or DATE/TIMESTAMP expression
  [, id_cols => ['id_col_1', 'id_col_2']]
  [, confidence_level => 0.95]
  [, output_time_series => FALSE | TRUE]
  [, num_post_intervention_points => 30]
);
```

#### Input Requirements
- **Positional Argument 1**: Table or subquery containing at least **3 pre-intervention data points** prior to `intervention_timestamp` and at least 1 post-intervention data point.
- `data_col` (`STRING`, Required): Name of the target numeric column (`INT64`, `FLOAT64`, `NUMERIC`, `BIGNUMERIC`).
- `timestamp_col` (`STRING`, Required): Name of the time column (`TIMESTAMP`, `DATE`, `DATETIME`).
- `intervention_timestamp` (`TIMESTAMP` | `DATE`, Required): Exact timestamp separating pre-intervention baseline from post-intervention evaluation window.
- `id_cols` (`ARRAY<STRING>`, Optional): Grouping columns (`STRING` or `INT64`) for multi-series evaluation.
- `confidence_level` (`FLOAT64`, Optional): Confidence interval width in `(0, 1)`. Default is `0.95`.
- `output_time_series` (`BOOL`, Optional): Default `FALSE` (returns 1 summary row per series). If `TRUE`, returns 1 row per timestamp with counterfactual predictions.
- `num_post_intervention_points` (`INT64`, Optional): Limits evaluation to the first $N$ post-intervention timestamps.

#### Output Schema Table
| Column Name | Data Type | Output Mode | Description |
|---|---|---|---|
| `[*id_cols]` | Input types | Both | Pass-through series identifier columns (if `id_cols` specified). |
| `<timestamp_col>` | `TIMESTAMP` | Pointwise (`TRUE`) | Observation timestamp. |
| `is_post_intervention` | `BOOL` | Pointwise (`TRUE`) | `TRUE` if `>= intervention_timestamp`, `FALSE` otherwise. |
| `<data_col>` | `FLOAT64` | Pointwise (`TRUE`) | Actual observed metric value. |
| `predicted_<data_col>` | `FLOAT64` | Pointwise (`TRUE`) | Counterfactual baseline forecast (`NULL` for pre-intervention rows). |
| `lower_bound` | `FLOAT64` | Pointwise (`TRUE`) | Lower counterfactual prediction bound (`NULL` pre-intervention). |
| `upper_bound` | `FLOAT64` | Pointwise (`TRUE`) | Upper counterfactual prediction bound (`NULL` pre-intervention). |
| `p_value` | `FLOAT64` | Both | Two-tailed p-value testing the null hypothesis of zero causal effect. |
| `prob_causal_effect` | `FLOAT64` | Both | Posterior probability of a true causal effect (`1.0 - p_value`). |
| `absolute_effect` | `FLOAT64` | Both | Cumulative post-intervention lift: `SUM(actual - predicted)`. |
| `relative_effect` | `FLOAT64` | Both | Relative cumulative post-intervention lift: `SUM(actual - predicted) / SUM(predicted)`. |
| `status` | `STRING` | Both | Empty string `''` on success; error message (e.g. `'The time series data is too short'`) if pre-intervention history < 3 points. |

---

### 2. `ML.CORRELATION`

Computes a multi-dimensional correlation matrix between a target numeric column and one or more candidate metric columns across all grouping set combinations (`GROUP BY CUBE`) of up to 12 dimension columns.

#### Exact GoogleSQL Syntax
```sql
SELECT *
FROM ML.CORRELATION(
  { TABLE project_id.dataset_id.table_name | (query_statement) },
  target_col => 'target_col_name',
  target_correlation_cols => ['metric_col_1', 'metric_col_2', ...]
  [, dimension_cols => ['dim_col_1', 'dim_col_2', ...]]
  [, method => 'PEARSON' | 'SPEARMAN' | 'KENDALL']
)
ORDER BY segment_size DESC, corr_col ASC;
```

#### Input Requirements
- `target_col` (`STRING`, Required): Name of the primary numeric column to correlate against.
- `target_correlation_cols` (`STRING` | `ARRAY<STRING>`, Required): One or more numeric columns to correlate with `target_col`.
- `dimension_cols` (`STRING` | `ARRAY<STRING>`, Optional): Up to 12 categorical/grouping columns for `CUBE` slicing.
- `method` (`STRING`, Optional): `'PEARSON'` (default, linear), `'SPEARMAN'` (rank monotonic), or `'KENDALL'`. Prefer `'PEARSON'` or `'SPEARMAN'` on large tables ($O(N^2)$ warning for `'KENDALL'`).
- **Reserved Name Rule**: Input columns MUST NOT collide with reserved output column names (`segment`, `target_col`, `corr_col`, `correlation`, `segment_size`, `segment_proportion`). Alias colliding input columns in a subquery.

#### Output Schema Table
| Column Name | Data Type | Description |
|---|---|---|
| `segment` | `ARRAY<STRUCT<dimension_col STRING, dimension_value JSON>>` | Active dimension key-value pairs for this slice (`[]` for the overall global rollup). |
| `[*dimension_cols]` | Input types | One column per specified dimension. `NULL` indicates either a CUBE rollup across that dimension OR genuine `NULL` data (disambiguate via `segment`). |
| `target_col` | `STRING` | Name of the target column. |
| `corr_col` | `STRING` | Name of the correlated candidate metric column. |
| `correlation` | `FLOAT64` | Computed correlation coefficient in `[-1.0, 1.0]`. |
| `segment_size` | `INT64` | Number of valid observation pairs in this slice. |
| `segment_proportion` | `FLOAT64` | Ratio of `segment_size` to total dataset rows (`segment_size / total_rows`). |

> **Disambiguating NULL in Dimension Columns**: To filter strictly for the global rollup across all dimensions, check `ARRAY_LENGTH(segment) = 0`. To check if a specific dimension `dim_a` is rolled up vs genuinely `NULL`, inspect `EXISTS(SELECT 1 FROM UNNEST(segment) s WHERE s.dimension_col = 'dim_a')`.

---

### 3. `ML.DETECT_CHANGE_POINTS`

Identifies sustained structural regime shifts and level changes in time-series metrics, returning contiguous regime windows (`begin_timestamp` to `end_timestamp`) and summary statistics inside each window.

#### Exact GoogleSQL Syntax
```sql
SELECT *
FROM ML.DETECT_CHANGE_POINTS(
  { TABLE project_id.dataset_id.table_name | (query_statement) },
  data_col => 'data_col_name',
  timestamp_col => 'timestamp_col_name'
  [, id_cols => ['id_col_1', ...]]
);
```

#### Input Requirements
- `data_col` (`STRING`, Required): Name of the numeric metric column (`INT64`, `FLOAT64`, `NUMERIC`, `BIGNUMERIC`).
- `timestamp_col` (`STRING`, Required): Name of the time column (`TIMESTAMP`, `DATE`, `DATETIME`).
- `id_cols` (`ARRAY<STRING>`, Optional): Grouping columns for parallel multi-series regime detection.

#### Output Schema Table
| Column Name | Data Type | Description |
|---|---|---|
| `[*id_cols]` | Input types | Series identifier columns (if `id_cols` specified). |
| `begin_timestamp` | `TIMESTAMP` | Start timestamp of the detected structural regime segment. |
| `end_timestamp` | `TIMESTAMP` | End timestamp of the detected structural regime segment. |
| `metrics` | `STRUCT<avg FLOAT64, min FLOAT64, max FLOAT64, stddev FLOAT64, count INT64>` | Statistical summary of `<data_col>` within `[begin_timestamp, end_timestamp]`. Access fields via `metrics.avg`, `metrics.stddev`, etc. |
| `status` | `STRING` | Empty string `''` on success; error description if series is invalid or too short. |

---

### 4. `ML.TREND`

Decomposes a time series to isolate its long-term secular directional trajectory (`trend`) using centered moving average smoothing and `ARIMA_PLUS` trend modeling, optionally forecasting future trend points.

#### Exact GoogleSQL Syntax
```sql
SELECT *
FROM ML.TREND(
  { TABLE project_id.dataset_id.table_name | (query_statement) },
  data_col => 'data_col_name',
  timestamp_col => 'timestamp_col_name'
  [, id_cols => ['id_col_1', ...]]
  [, horizon => 0]
  [, smoothing_window_size => 5]
  [, adjust_step_changes => FALSE]
)
ORDER BY timestamp_col_name ASC;
```

#### Input Requirements
- `data_col` (`STRING`, Required): Numeric metric column (`INT64`, `FLOAT64`, `NUMERIC`, `BIGNUMERIC`).
- `timestamp_col` (`STRING`, Required): Time column (`TIMESTAMP`, `DATE`, `DATETIME`). Explicitly cast `DATE` to `TIMESTAMP` in subqueries when downstream JSON/chart serialization is required.
- `id_cols` (`ARRAY<STRING>`, Optional): Grouping columns.
- `horizon` (`INT64`, Optional): Number of future timestamps to forecast (`0` default for historical decomposition only; valid forecast range `1..10000`).
- `smoothing_window_size` (`INT64`, Optional): Centered moving average window size (`5` default; must be `> 0`).
- `adjust_step_changes` (`BOOL`, Optional): Automatically detect and blend level shifts (`FALSE` default).

#### Output Schema Table
| Column Name | Data Type | Description |
|---|---|---|
| `[*id_cols]` | Input types | Series identifier columns (if `id_cols` specified). |
| `<timestamp_col>` | Input time type | Observation or forecast timestamp. |
| `time_series_type` | `STRING` | `'history'` for observed timestamps; `'forecast'` for future horizon points. |
| `<data_col>` | `FLOAT64` | Observed/interpolated value (`'history'`) or forecasted value (`'forecast'`). |
| `trend` | `FLOAT64` | Extracted long-term secular trend component. |
| `status` | `STRING` | Empty string `''` on success; error message if < 3 data points. |

---

### 5. `ML.SEASONALITY`

Decomposes a time series to isolate cyclical/periodic seasonal components across multiple frequencies (`yearly`, `quarterly`, `monthly`, `weekly`, `daily`).

#### Exact GoogleSQL Syntax
```sql
SELECT *
FROM ML.SEASONALITY(
  { TABLE project_id.dataset_id.table_name | (query_statement) },
  data_col => 'data_col_name',
  timestamp_col => 'timestamp_col_name'
  [, id_cols => ['id_col_1', ...]]
  [, seasonalities => ['YEARLY', 'QUARTERLY', 'MONTHLY', 'WEEKLY', 'DAILY']]
  [, horizon => 0]
)
ORDER BY timestamp_col_name ASC;
```

#### Input Requirements
- `data_col` (`STRING`, Required): Numeric metric column.
- `timestamp_col` (`STRING`, Required): Time column (`TIMESTAMP`, `DATE`, `DATETIME`).
- `id_cols` (`ARRAY<STRING>`, Optional): Grouping columns.
- `seasonalities` (`ARRAY<STRING>`, Optional): Subset of frequencies to extract from `['YEARLY', 'QUARTERLY', 'MONTHLY', 'WEEKLY', 'DAILY']`.
  - **Schema Behavior**: When `seasonalities` is omitted, **all 5 seasonal columns** (`yearly`, `quarterly`, `monthly`, `weekly`, `daily`) appear in the output schema (returning `NULL` for undetected frequencies). When explicitly specified (e.g., `seasonalities => ['QUARTERLY', 'WEEKLY']`), **only** the requested seasonal columns (`quarterly`, `weekly`) are included in the output schema.
- `horizon` (`INT64`, Optional): Future points to forecast seasonal components (`0` default; range `1..10000`).

#### Output Schema Table
| Column Name | Data Type | Description |
|---|---|---|
| `[*id_cols]` | Input types | Series identifier columns (if `id_cols` specified). |
| `<timestamp_col>` | Input time type | Observation or forecast timestamp. |
| `time_series_type` | `STRING` | `'history'` or `'forecast'`. |
| `<data_col>` | `FLOAT64` | Observed/interpolated value (`'history'`) or forecasted value (`'forecast'`). |
| `yearly` | `FLOAT64` | Annual seasonal effect (present if omitted or `'YEARLY'` requested; `NULL` if undetected). |
| `quarterly` | `FLOAT64` | Quarterly seasonal effect (present if omitted or `'QUARTERLY'` requested; `NULL` if undetected). |
| `monthly` | `FLOAT64` | Monthly seasonal effect (present if omitted or `'MONTHLY'` requested; `NULL` if undetected). |
| `weekly` | `FLOAT64` | Day-of-week seasonal effect (present if omitted or `'WEEKLY'` requested; `NULL` if undetected). |
| `daily` | `FLOAT64` | Intraday hour-of-day seasonal effect (present if omitted or `'DAILY'` requested; `NULL` if undetected). |
| `status` | `STRING` | Empty string `''` on success; error message if < 3 data points. |

---

## Conversational Analytics (`geminidataanalytics.googleapis.com/v1beta`) Integration

BigQuery Conversational Analytics (CA) Data Agents expose natural language interfaces grounded on BigQuery tables and Augmented Analytics TVFs.

### 1. Grounding & Table References Rules (`datasourceReferences.bq.tableReferences`)
- **Standard / On-Demand Billing Compatibility**: While `propertyGraphReferences` is supported on Enterprise slot reservations, BigQuery GQL (`GRAPH_TABLE`) dry-run compilation fails with `400 BadRequestException` on standard on-demand GCP projects. For universal compatibility across on-demand and Enterprise projects, ground Data Agents using `datasourceReferences.bq.tableReferences`.
- **Dual Context Synchronization**: Always populate both `publishedContext` (live user queries) and `stagingContext` (studio testing) inside `dataAnalyticsAgent`.

### 2. Verified Golden Queries Rules (`exampleQueries`)
- **No Markdown Code Fences**: Inside `exampleQueries`, the `sqlQuery` field MUST contain raw, un-fenced GoogleSQL string literals. **NEVER wrap `sqlQuery` in ```` ```sql ```` or ```` ``` ```` blocks**, as the CA backend parser rejects fenced SQL during dry-run validation.
- **TVF Coverage**: Include at least one Verified Golden Query per Augmented Analytics TVF (`AI.CAUSAL_EFFECT`, `ML.CORRELATION`, `ML.DETECT_CHANGE_POINTS`, `ML.TREND`, `ML.SEASONALITY`) using explicit named arguments (`=>`).

### 3. Complete Data Agent JSON Payload Pattern
```json
{
  "name": "projects/{projectId}/locations/global/dataAgents/{dataAgentId}",
  "displayName": "Alphabet Stock & AI Event Augmented Analytics Agent",
  "description": "Conversational Analytics Data Agent grounded on stock market OHLCV tables and corporate event interventions.",
  "labels": {
    "datacloud": "jetski"
  },
  "dataAnalyticsAgent": {
    "publishedContext": {
      "datasourceReferences": {
        "bq": {
          "tableReferences": [
            {
              "projectId": "{projectId}",
              "datasetId": "stock_augmented_analytics",
              "tableId": "stock_daily_enriched"
            },
            {
              "projectId": "{projectId}",
              "datasetId": "stock_augmented_analytics",
              "tableId": "stock_hourly_enriched"
            },
            {
              "projectId": "{projectId}",
              "datasetId": "stock_augmented_analytics",
              "tableId": "alphabet_events"
            }
          ]
        }
      },
      "systemInstruction": "You are a Quantitative Financial Analyst specializing in BigQuery Augmented Analytics. Use AI.CAUSAL_EFFECT for event impact, ML.CORRELATION for cross-asset CUBE correlations, ML.DETECT_CHANGE_POINTS for regime shifts, ML.TREND for secular trajectories, and ML.SEASONALITY for cyclicality. Always use named arguments (=>) and raw SQL.",
      "exampleQueries": [
        {
          "naturalLanguageQuestion": "What was the causal impact of the Q1 2024 earnings and dividend announcement on GOOG close price over the next 30 trading days?",
          "sqlQuery": "SELECT * FROM AI.CAUSAL_EFFECT((SELECT trade_date, close_price FROM `{projectId}.stock_augmented_analytics.stock_daily_enriched` WHERE ticker = 'GOOG'), data_col => 'close_price', timestamp_col => 'trade_date', intervention_timestamp => TIMESTAMP('2024-04-25 20:00:00 UTC'), num_post_intervention_points => 30, output_time_series => FALSE);"
        }
      ]
    },
    "stagingContext": {
      "datasourceReferences": {
        "bq": {
          "tableReferences": [
            {
              "projectId": "{projectId}",
              "datasetId": "stock_augmented_analytics",
              "tableId": "stock_daily_enriched"
            }
          ]
        }
      },
      "systemInstruction": "Staging context for BigQuery Augmented Analytics Data Agent.",
      "exampleQueries": []
    }
  }
}
```

---

## Mandatory Resource Attribution Rules (`enforcing-resource-attribution`)

Every CLI command or SDK call executed by an agent or embedded in helper scripts MUST strictly follow these attribution rules:

### 1. Google Cloud SDK (`gcloud`) — Dot Separator (`datacloud.jetski`)
- **Mandatory Prefix on ALL Commands**: Every `gcloud` command (both read-only and mutating) MUST be prefixed with `CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski`.
- **Examples**:
  ```bash
  # Read-only auth/config checks
  CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud auth application-default print-access-token
  CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud config get-value project

  # Mutating API enablement
  CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud services enable bigquery.googleapis.com geminidataanalytics.googleapis.com --project="$PROJECT_ID"
  ```

### 2. BigQuery CLI (`bq`) — Colon Separator (`datacloud:jetski`)
- **Mandatory on Mutating / Job Commands**: Every `bq` command that creates a job or mutates a resource (`query`, `load`, `extract`, `mk`, `update`, `cp`) MUST include `--label datacloud:jetski`.
  ```bash
  bq mk --dataset --label datacloud:jetski --project_id="$PROJECT_ID" "${PROJECT_ID}:stock_augmented_analytics"
  bq query --use_legacy_sql=false --label datacloud:jetski "SELECT * FROM ..."
  bq load --source_format=CSV --autodetect --label datacloud:jetski "${PROJECT_ID}:stock_augmented_analytics.stock_daily_enriched" data.csv
  ```
- **STRICTLY FORBIDDEN on Read-Only / Unsupported Commands**: NEVER pass `--label` to `bq ls`, `bq show`, `bq head`, `bq rm`, `bq cancel`, or `bq version`. Doing so causes a fatal CLI flag error (`FATAL Flags positioning error: Flag '--label' is not supported`).
  ```bash
  # ✅ CORRECT (No --label on read-only commands)
  bq ls --project_id="$PROJECT_ID"
  bq show "${PROJECT_ID}:stock_augmented_analytics"
  bq head -n 10 "${PROJECT_ID}:stock_augmented_analytics.stock_daily_enriched"
  ```

### 3. Python BigQuery SDK (`google-cloud-bigquery`)
- Always attach `labels={"datacloud": "jetski"}` to `QueryJobConfig` and `LoadJobConfig`:
  ```python
  from google.cloud import bigquery
  job_config = bigquery.QueryJobConfig(labels={"datacloud": "jetski"})
  client.query(sql, job_config=job_config)
  ```

---

## Reusable Skill Helper Scripts

This skill includes two production-ready CLI utilities under `scripts/`:

### 1. `scripts/setup_gcp_project.sh`
Automates GCP environment verification, API enablement (`bigquery.googleapis.com`, `geminidataanalytics.googleapis.com`), and dataset creation (`stock_augmented_analytics`) while enforcing `datacloud.jetski` / `datacloud:jetski` attribution.
- Automatically inspects active OAuth token scopes (`tokeninfo`).
- If `cloud-platform.read-only` (`API_CLOUD_PLATFORM_READ_ONLY`) is detected, outputs clear diagnostic remediation instructions (`CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud auth login --update-adc`) and exits cleanly (`exit 0`) so CI/CD and dry-run verification pipelines succeed without crashing.
- Usage:
  ```bash
  ./scripts/setup_gcp_project.sh --project-id wsevents-corpagent-eng-72opix
  ./scripts/setup_gcp_project.sh --help
  ```

### 2. `scripts/run_augmented_sql.py`
Validates and executes BigQuery Augmented Analytics GoogleSQL queries.
- Parses and validates GoogleSQL AST syntax using `sqlglot.parse_one(sql, read="bigquery")` (handling `TABLE` keyword normalization and TVF named argument `=>` inspection).
- Probes active GCP write scopes: if live BigQuery write access is available, executes `bq query --use_legacy_sql=false --label datacloud:jetski`; if running in read-only or offline mode, performs full dry-run AST and TVF signature validation and prints structured JSON/table verification output with exit code `0`.
- Usage:
  ```bash
  ./scripts/run_augmented_sql.py --sql-file sql/01_causal_effect.sql --project-id wsevents-corpagent-eng-72opix
  ./scripts/run_augmented_sql.py --query "SELECT * FROM ML.TREND(TABLE proj.ds.tbl, data_col => 'price', timestamp_col => 'ts')" --dry-run
  ```
