---
name: antigravity-arcade
description: "Interactive Agentic Data Arcade runner for Google Cloud Summit 2026. Executes real BigQuery queries, Property Graph DDLs, BigFrames pushdown workloads, and Google Cloud operations with live console visibility."
metadata:
  version: v1
  publisher: google
---

# Antigravity Data Arcade (Summit São Paulo 2026)

This skill enables Antigravity and AI agents to run interactive, 6-stage gamified scenarios against live Google Cloud infrastructure in the configured project (`gricardo-next26-demos`).

## Capabilities
1. **Live Dataset Provisioning**: Creates real BigQuery datasets (`summit_arcade_2026_logistics`, `summit_arcade_2026_fintech`) with seed tables.
2. **Real Property Graph Compilation**: Compiles DDLs (`CREATE OR REPLACE PROPERTY GRAPH`) with `MEASURE(AGG(...))` measures.
3. **Live Job Attribution**: Runs queries with mandatory labels (`datacloud:antigravity`, `summit:2026-arcade`) so all jobs appear in BigQuery Studio Query History.
4. **Interactive Branching Choices**: Evaluates Golden Path (Option A) vs Sub-optimal Path (Option B) vs Meme Path (Option C) with live slot compute and execution metrics.

## CLI Usage
```bash
# Start interactive terminal session
python3 /usr/local/google/home/gricardo/summit-2026-agentic-arcade/arcade_engine.py --live

# Deploy all live datasets and seeds to GCP
python3 /usr/local/google/home/gricardo/summit-2026-agentic-arcade/deploy_live_gcp_assets.py
```
