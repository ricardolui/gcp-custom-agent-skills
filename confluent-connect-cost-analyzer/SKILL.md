---
name: confluent-connect-cost-analyzer
description: Inspect, analyze, and forecast Kafka Connect costs per connector, task, and throughput on Confluent Cloud using the Confluent Cloud Billing API (`/billing/v1/costs`). Covers querying cost line items (`CONNECT_NUM_TASKS`, `CONNECT_THROUGHPUT`), calculating daily/monthly run rates per connector, identifying idle or over-provisioned connectors, and auditing enterprise discounts. Use whenever the user asks about Kafka Connect costs, connector spending, task-hour expenses, or Confluent billing optimization.
metadata:
  version: "1.0.0"
---

# Confluent Cloud Kafka Connect Cost Analyzer

A comprehensive guide, operational reference, and automation toolkit for querying, analyzing, and optimizing Kafka Connect costs per connector on Confluent Cloud.

---

## 1. Kafka Connect Pricing Model

Confluent Cloud bills managed connectors using a consumption-based model driven by two distinct billable dimensions:

| Billing Dimension (`line_type`) | Metric Unit | Typical Rate (Enterprise) | Description |
| :--- | :---: | :---: | :--- |
| **`CONNECT_NUM_TASKS`** | **Task-hour** | **~$0.179 – $0.195 / hr** | Billed for every active connector task running per hour. Charged regardless of whether messages are flowing. |
| **`CONNECT_THROUGHPUT`** | **GB** | **~$0.043 / GB** | Billed for the total pre-compression volume of data read or written by the connector. |

### Cost Projections per Task Configuration

Since task hours accrue 24/7 as long as the connector is in `RUNNING` or `PAUSED` state:

$$\text{Task Compute Cost (Daily)} = \text{tasks.max} \times 24 \times \text{Price per Task-Hour}$$
$$\text{Task Compute Cost (Monthly)} = \text{tasks.max} \times 730 \times \text{Price per Task-Hour}$$

| Tasks (`tasks.max`) | Daily Compute Cost | Monthly Compute Cost | Notes |
| :---: | :---: | :---: | :--- |
| **1 Task** | ~$4.30 / day | ~$130.00 / month | Ideal for dev/sandbox or low-throughput topics (< 5 MB/s) |
| **2 Tasks** | ~$8.60 / day | ~$260.00 / month | Standard redundancy for moderate workloads |
| **4 Tasks** | ~$17.20 / day | ~$520.00 / month | High-throughput platform topics or multi-topic sinks |
| **8 Tasks** | ~$34.40 / day | ~$1,040.00 / month | Very high volume ingestion (> 50 MB/s) |

> [!IMPORTANT]
> **Over-provisioning Warning**: If a connector is configured with `tasks.max: 4` but processes only 1 GB of data per day, the user pays **$17.20/day in compute** to process **$0.04 of data**. Auditing task counts against actual throughput is the single highest-impact optimization.

---

## 2. Programmatic Cost Auditing via Confluent Cloud Billing API

The Confluent Cloud Billing API (`/billing/v1/costs`) returns aggregated, granular cost line items for all resources in an organization, tagged by resource ID and connector display name.

### Authentication
- **Endpoint**: `https://api.confluent.cloud/billing/v1/costs`
- **Method**: `GET`
- **Credentials**: Global Cloud API Key & Secret (passed as HTTP Basic Auth).
- **Required Permission**: `OrganizationAdmin` or `BillingAdmin`.

### Request Parameters
- `start_date` (`YYYY-MM-DD`, UTC inclusive): Starting date of the billing window.
- `end_date` (`YYYY-MM-DD`, UTC inclusive): Ending date of the billing window.
- `page_size`: Number of records per page (up to `100`).
- Pagination cursor via `metadata.next`.

### Key JSON Response Schema
```json
{
  "amount": 17.204,
  "original_amount": 18.700,
  "discount_amount": 1.496,
  "price": 0.19479167,
  "product": "CONNECT",
  "line_type": "CONNECT_NUM_TASKS",
  "quantity": 96.0,
  "unit": "Task-hour",
  "start_date": "2026-09-01",
  "end_date": "2026-09-02",
  "granularity": "DAILY",
  "resource": {
    "id": "lcc-0xj5g0p",
    "display_name": "bq-sink-silver-prod",
    "environment": {
      "id": "env-m62nqq"
    }
  }
}
```

---

## 3. Quick CLI Inspection (cURL + jq)

To query the spend of all connectors across the last 3 days directly from the shell:

```bash
curl -s -u "$CONFLUENT_CLOUD_API_KEY:$CONFLUENT_CLOUD_API_SECRET" \
  "https://api.confluent.cloud/billing/v1/costs?start_date=$(date -d '3 days ago' +%F)&end_date=$(date +%F)" \
  | jq -r '.data[] | select(.product=="CONNECT") | 
      "\(.start_date) | \(.resource.display_name // .resource.id) | \(.line_type) | \(.quantity) \(.unit) | $\(.amount)"'
```

---

## 4. Automated Python Cost Analyzer Script

A production-ready analysis script is provided in `scripts/analyze_connect_costs.py`. It fetches all pages, groups by connector, separates task compute from data throughput, and prints a formatted cost breakdown with daily run-rate averages.

### Execution:
```bash
python3 /usr/local/google/home/gricardo/.gemini/config/skills/confluent-connect-cost-analyzer/scripts/analyze_connect_costs.py \
  --start-date 2026-08-28 \
  --end-date 2026-09-03
```

### Script Implementation:
The script handles:
1. Basic Auth encoding with `CONFLUENT_CLOUD_API_KEY` and `CONFLUENT_CLOUD_API_SECRET`.
2. Automatic cursor pagination via `metadata.next`.
3. Granular aggregation by connector name (`resource.display_name`).
4. Breakdown of Task Compute vs Throughput Volume.
5. Detection of zero-throughput (idle) connectors.

---

## 5. Console UI Inspection Steps

If checking costs via the web interface:

1. Log into [Confluent Cloud Console](https://confluent.cloud/).
2. In the top right navigation menu, click **Administration** (or the Organization name) -> **Billing & payment**.
3. Select the **Cost analysis** tab.
4. Apply the following filters:
   - **Product**: Select `Connect`.
   - **Group by**: Select `Resource` (or `Connector Name`).
   - **Granularity**: Select `Daily` or `Monthly`.
5. Hover over individual bar charts or review the summary table below to view exact line-item spend per connector.

---

## 6. Cost Optimization Checklist

When reviewing connector expenses, follow these four optimization rules:

1. **Eliminate Zombie Connectors**:
   - Query connectors where `CONNECT_NUM_TASKS > 0` but `CONNECT_THROUGHPUT == 0.0 GB` across 7 days.
   - Any test/dev connector left running without traffic costs ~$130/month per task doing nothing.
2. **Right-Size `tasks.max`**:
   - Check throughput per task. If 4 tasks are processing < 2 MB/s, reduce to `tasks.max: 1` or `tasks.max: 2` to immediately cut compute cost by 50–75% without impacting latency.
3. **Consolidate Multi-Topic Sinks**:
   - Instead of deploying 16 separate connectors (1 per topic, each with `tasks.max: 1` = 16 tasks = ~$2,080/month), deploy a single multi-topic connector with `tasks.max: 4` ($520/month) using `topic2table.map`. This reduces task compute costs by 75%.
4. **Pause Inactive Sinks**:
   - Note: Confluent Cloud may still charge for allocated task hours if a connector is merely paused rather than deleted, depending on connector class. Deleting and recreating via IaC (Terraform) or REST API is the cleanest way to zero out charges for transient workloads.
