# Golden Queries (Verified Queries) — 10 Architectural Patterns

Verified Queries (Golden Queries) serve as grounded, few-shot examples for the Conversational Analytics LLM. They dictate how natural language questions translate to BigQuery SQL and GoogleSQL GQL queries.

---

## 1. The 10 Archetypes & SQL/GQL Templates

### Archetype 1: Top-N Rankings / Categorical Comparison (Triggers Bar Chart)
- **Visual Trigger**: 1 string dimension + 1 aggregate metric. `ORDER BY <metric> DESC LIMIT 10`.
- **Natural Language**: *"Quais são os 10 fornecedores com maior volume de compras comprometido?"*
- **SQL / GQL**:
```sql
SELECT
  Supplier_supplier_name AS fornecedor,
  AGG(PurchaseOrderItem_total_committed_spend) AS spend_total
FROM GRAPH_EXPAND("`my-project.dataset_gold.procurement_graph`")
GROUP BY fornecedor
ORDER BY spend_total DESC
LIMIT 10;
```

### Archetype 2: Temporal Trends & Time Series (Triggers Line/Area Chart)
- **Visual Trigger**: 1 date/timestamp dimension + 1 aggregate metric. `ORDER BY <date> ASC`.
- **Natural Language**: *"Como evoluiu o faturamento mensal ao longo do último ano?"*
- **SQL / GQL**:
```sql
SELECT
  DATE_TRUNC(InvoiceNFe_emission_date, MONTH) AS mes,
  AGG(InvoiceNFe_total_invoiced_spend) AS total_faturado
FROM GRAPH_EXPAND("`my-project.dataset_gold.procurement_graph`")
GROUP BY mes
ORDER BY mes ASC;
```

### Archetype 3: Share of Total & Composition (Triggers Donut/Pie Chart)
- **Visual Trigger**: 1 dimension with $\le 7$ unique values + 1 sum metric.
- **Natural Language**: *"Qual a distribuição percentual do spend por categoria de risco de fornecedor?"*
- **SQL / GQL**:
```sql
SELECT
  Supplier_risk_tier AS nivel_risco,
  AGG(PurchaseOrderItem_total_committed_spend) AS spend_comprometido
FROM GRAPH_EXPAND("`my-project.dataset_gold.procurement_graph`")
GROUP BY nivel_risco
ORDER BY spend_comprometido DESC;
```

### Archetype 4: Graph Relationship / Direct Entity Match
- **Natural Language**: *"Quais ordens de compra estão vinculadas ao contrato CTR-2026-001?"*
- **SQL / GQL**:
```sql
GRAPH `my-project.dataset_gold.procurement_graph`
MATCH (po:PurchaseOrder)-[e:GOVERNED_BY]->(c:Contract {contract_id: 'CTR-2026-001'})
RETURN po.po_number AS numero_pedido, c.max_commitment_val AS teto_contrato
LIMIT 10;
```

### Archetype 5: Multi-Hop Graph Traversal ($A \to B \to C$)
- **Natural Language**: *"Quais fornecedores classificados como HIGH RISK faturaram itens para o departamento de TI?"*
- **SQL / GQL**:
```sql
SELECT
  Supplier_supplier_name AS fornecedor,
  CostCenter_department_name AS departamento,
  AGG(PurchaseOrderItem_total_committed_spend) AS total_gasto
FROM GRAPH_EXPAND("`my-project.dataset_gold.procurement_graph`")
WHERE Supplier_risk_tier IN ('HIGH', 'CRITICAL')
  AND CostCenter_department_name = 'Tecnologia da Informação'
GROUP BY fornecedor, departamento
ORDER BY total_gasto DESC
LIMIT 10;
```

### Archetype 6: Outlier & Anomaly Detection
- **Natural Language**: *"Liste as notas fiscais que geraram anomalias críticas com score de severidade acima de 0.85."*
- **SQL / GQL**:
```sql
SELECT
  InvoiceNFe_invoice_key AS nota_fiscal,
  AuditAnomaly_anomaly_type AS tipo_anomalia,
  AuditAnomaly_severity_score AS score_severidade
FROM GRAPH_EXPAND("`my-project.dataset_gold.procurement_graph`")
WHERE AuditAnomaly_severity_score >= 0.85
ORDER BY score_severidade DESC
LIMIT 10;
```

### Archetype 7: Segment & Status Distribution
- **Natural Language**: *"Quantos pedidos de compra existem em cada status de aprovação?"*
- **SQL / GQL**:
```sql
SELECT
  po_status AS status_pedido,
  COUNT(po_number) AS total_pedidos
FROM `my-project.dataset_gold.fact_purchase_orders`
GROUP BY status_pedido
ORDER BY total_pedidos DESC;
```

### Archetype 8: Source-to-Destination Flow Aggregation
- **Natural Language**: *"Qual o volume físico de mercadorias transferido entre depósitos de origem e destino?"*
- **SQL / GQL**:
```sql
SELECT
  source_plant AS centro_origem,
  destination_plant AS centro_destino,
  SUM(transfer_qty) AS volume_transferido
FROM `my-project.dataset_gold.fact_stock_transfers`
GROUP BY centro_origem, centro_destino
ORDER BY volume_transferido DESC
LIMIT 10;
```

### Archetype 9: Global Financial & Volume Summary
- **Natural Language**: *"Qual o volume total de divergências retidas por auditoria em conciliação tripla?"*
- **SQL / GQL**:
```sql
SELECT
  AGG(InvoiceNFe_total_divergence_blocked) AS total_retido_auditoria,
  AGG(InvoiceNFe_total_invoiced_spend) AS total_faturado
FROM GRAPH_EXPAND("`my-project.dataset_gold.procurement_graph`");
```

### Archetype 10: Recent Activity Stream
- **Natural Language**: *"Quais foram os 10 pedidos de compra mais recentes emitidos?"*
- **SQL / GQL**:
```sql
SELECT
  po_number AS numero_pedido,
  created_at AS data_emissao,
  total_amount AS valor_total
FROM `my-project.dataset_gold.fact_purchase_orders`
ORDER BY created_at DESC
LIMIT 10;
```

---

## 2. Dry-Run & Self-Healing Execution Rules

1. **No Markdown Fences in API**: The `sqlQuery` string inside `exampleQueries` must be raw SQL, **never** enclosed in backticks or markdown fences (` ```sql `).
2. **Deterministic Dry-Run Validation**: Always execute `bq.createQueryJob({ query, dryRun: true })` on each golden query. A valid query consumes 0 bytes and returns job metadata.
3. **Compiler Error Auto-Heal**: If BigQuery rejects a query with a semantic error (e.g., unrecognized column name), send the exact compiler message to `gemini-3.7-flash` to generate the corrected projection.
