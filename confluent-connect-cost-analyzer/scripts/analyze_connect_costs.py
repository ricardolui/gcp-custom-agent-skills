#!/usr/bin/env python3
"""
Confluent Cloud Kafka Connect Cost Analyzer CLI
Queries Confluent Cloud Billing API (/billing/v1/costs) and prints a granular breakdown
of connector task-hours and data throughput spend.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_KEY = "GMX2O344FGJ5RFXQ"
DEFAULT_SECRET = "cfltJX0cVd9CWseAwvxqXaz7w5Ee+ZWx8CgnbwaEBrbtVeICGf3BVXLiVVmg+v2w"

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze Confluent Cloud Kafka Connect costs per connector.")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD), default is 7 days ago", default=None)
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD), default is today", default=None)
    parser.add_argument("--api-key", help="Confluent Cloud API Key", default=os.getenv("CONFLUENT_CLOUD_API_KEY", DEFAULT_KEY))
    parser.add_argument("--api-secret", help="Confluent Cloud API Secret", default=os.getenv("CONFLUENT_CLOUD_API_SECRET", DEFAULT_SECRET))
    parser.add_argument("--min-cost", help="Only show connectors with spend >= min-cost (default 0.0)", type=float, default=0.0)
    return parser.parse_args()

def main():
    args = parse_args()

    now = datetime.now(timezone.utc)
    if not args.end_date:
        end_date = now.strftime("%Y-%m-%d")
    else:
        end_date = args.end_date

    if not args.start_date:
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        start_date = args.start_date

    auth = base64.b64encode(f"{args.api_key}:{args.api_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json"
    }

    print(f"\nFetching Confluent Cloud Billing data for period: {start_date} to {end_date}...\n")

    all_data = []
    url = f"https://api.confluent.cloud/billing/v1/costs?start_date={start_date}&end_date={end_date}&page_size=100"

    while url:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode())
                data = res.get("data", [])
                all_data.extend(data)
                url = res.get("metadata", {}).get("next")
        except urllib.error.HTTPError as e:
            print(f"Billing API Error ({e.code}): {e.read().decode()}", file=sys.stderr)
            sys.exit(1)

    connect_items = [d for d in all_data if d.get("product") == "CONNECT"]

    if not connect_items:
        print("No CONNECT line items found in the requested period.")
        return

    summary = {}
    for item in connect_items:
        name = item.get("resource", {}).get("display_name", item.get("resource", {}).get("id", "Unknown"))
        amt = float(item.get("amount", 0.0))
        orig_amt = float(item.get("original_amount", 0.0))
        discount = float(item.get("discount_amount", 0.0))
        qty = float(item.get("quantity", 0.0))
        line_type = item.get("line_type")
        price = float(item.get("price", 0.0))
        date_str = item.get("start_date", "")

        if name not in summary:
            summary[name] = {
                "id": item.get("resource", {}).get("id"),
                "total_amount": 0.0,
                "tasks_hours": 0.0,
                "task_cost": 0.0,
                "throughput_gb": 0.0,
                "tp_cost": 0.0,
                "days": set(),
                "discount_total": 0.0
            }

        s = summary[name]
        s["total_amount"] += amt
        s["discount_total"] += discount
        s["days"].add(date_str)

        if line_type == "CONNECT_NUM_TASKS":
            s["tasks_hours"] += qty
            s["task_cost"] += amt
        elif line_type == "CONNECT_THROUGHPUT":
            s["throughput_gb"] += qty
            s["tp_cost"] += amt

    # Filter by min_cost
    filtered = {k: v for k, v in summary.items() if v["total_amount"] >= args.min_cost}

    # Print Table
    col_w = 40
    print("=" * 110)
    print(f"{'CONNECTOR NAME':<{col_w}} | {'TOTAL ($)':>10} | {'TASK HRS':>10} | {'TASK ($)':>9} | {'TP (GB)':>10} | {'TP ($)':>8} | {'AVG/DAY':>9}")
    print("=" * 110)

    total_overall = 0.0
    total_task_hours = 0.0
    total_throughput = 0.0

    for name, d in sorted(filtered.items(), key=lambda x: x[1]["total_amount"], reverse=True):
        total_overall += d["total_amount"]
        total_task_hours += d["tasks_hours"]
        total_throughput += d["throughput_gb"]
        num_days = max(len(d["days"]), 1)
        avg_day = d["total_amount"] / num_days

        # Format warning if idle (tasks > 0 but throughput == 0)
        idle_tag = " (IDLE)" if d["tasks_hours"] > 24 and d["throughput_gb"] == 0 else ""
        display_name = f"{name}{idle_tag}"[:col_w]

        print(f"{display_name:<{col_w}} | ${d['total_amount']:>9.2f} | {d['tasks_hours']:>10.1f} | ${d['task_cost']:>8.2f} | {d['throughput_gb']:>10.1f} | ${d['tp_cost']:>7.2f} | ${avg_day:>8.2f}")

    print("-" * 110)
    print(f"{'TOTALS':<{col_w}} | ${total_overall:>9.2f} | {total_task_hours:>10.1f} |           | {total_throughput:>10.1f} |          |")
    print("=" * 110)
    print(f"\nSummary:")
    print(f" - Analyzed Connectors: {len(filtered)}")
    print(f" - Total Connect Spend: ${total_overall:.2f}")
    print(f" - Total Compute Task Hours: {total_task_hours:.1f} hrs")
    print(f" - Total Data Processed: {total_throughput:.1f} GB\n")

if __name__ == "__main__":
    main()
