# BigQuery Graph Schema Best Practices

This document outlines best practices for designing and defining Property Graph
and Semantic Graph schemas in BigQuery. Following these guidelines improves
graph query performance, ensures referential integrity, and avoids common
pitfalls in flattened views (`GRAPH_EXPAND`).

--------------------------------------------------------------------------------

## 1. Scope Property Definitions (Critical for Performance)

Properties are key-value pairs attached to nodes or edges. By default, or if
using `PROPERTIES ALL COLUMNS`, all columns from the source table are attached.

*   **The Pitfall**: Exposing unnecessary properties forces BigQuery to perform
    redundant column scans in graph queries, severely degrading performance.
*   **Best Practice**: **Only include properties that are actually needed for
    querying.** Use the explicit `PROPERTIES (col1, col2, ...)` syntax to
    restrict the property list.
*   **Example**:

```sql
-- POOR: Exposes all columns including large text or metadata
NODE TABLES ( my_dataset.users PROPERTIES ALL COLUMNS )

-- GOOD: Only exposes relevant querying attributes
NODE TABLES ( my_dataset.users PROPERTIES (user_id, name, age) )
```

--------------------------------------------------------------------------------

## 2. Define Key Constraints (PK / FK)

BigQuery doesn't strictly enforce Primary Key (PK) or Foreign Key (FK)
constraints at runtime, but it uses them to optimize execution plans.

*   **Optimization**: If PK/FK constraints are defined on the underlying tables,
    the query engine can leverage them to eliminate unnecessary table scans and
    prune join paths.
*   **Referential Integrity**: Ensure your application guarantees the uniqueness
    of primary keys and referential integrity of foreign keys. If they are
    violated, graph query results may be incorrect.
*   **Best Practice**: Always define PK on node tables and FK on edge tables in
    their source DDL, and reference them in `CREATE PROPERTY GRAPH`.

--------------------------------------------------------------------------------

## 3. Avoid Column Name Collisions in Flattened Schema (`GRAPH_EXPAND`)

The `GRAPH_EXPAND` TVF flattens the graph by prefixing each property with the
Node/Edge alias (e.g., `NodeAlias_propertyName`).

*   **The Danger**: If the combination of alias and property name results in
    identical column names, the query will fail with a generic internal Dremel
    error: `Error encountered during execution. Retrying may solve the problem.`
*   **Scenario**:
    *   Node `N` with property `a_b` -> Generated column: `N_a_b`
    *   Node `N_a` with property `b` -> Generated column: `N_a_b` (Collision!)
*   **Best Practice**: Design your node/edge aliases and property names
    carefully to avoid prefix-induced collisions. Renaming properties or using
    distinct aliases in the DDL resolves this.

--------------------------------------------------------------------------------

## 4. Always Use Safe Aliases (`AS alias`)

If you omit the `AS alias` clause, BigQuery defaults to using the full table
path as the alias (e.g., `project.dataset.table`).

*   **The Pitfall**: The generated column names in the flattened view will
    contain dots and hyphens (e.g., `project.dataset.table_property`). This
    violates standard SQL output schema rules, and queries like `SELECT *` will
    fail with `Invalid field name`.
*   **Best Practice**: **Always specify a simple, alphanumeric alias** using
    standard SQL naming conventions (no dots, hyphens, or special characters).
*   **Example**:

```sql
-- POOR (Omitted alias):
NODE TABLES ( `my-project.my_dataset.user_profiles` KEY(id) ... )

-- GOOD (Safe alias):
NODE TABLES ( `my-project.my_dataset.user_profiles` AS User KEY(id) ... )
```

*   **TODO(b/493238936)**: This explicit safe alias requirement can be omitted
    once the BigQuery engine natively resolves default column names containing
    dots/hyphens.

--------------------------------------------------------------------------------

## 5. Reusing the Same Physical Table as Node and Edge Tables

In hierarchical schemas (such as employee-manager org charts or product category
trees), the same physical table often represents both the entity (Node) and the
parent-child relationship (Edge).

When modeling this in DDL, you must decide how the reused table is exposed in
`GRAPH_EXPAND`:

1.  **Explicit Edges (Special/Explicit Properties)**:
    *   **Approach**: Declare the table as an edge table and list specific
        property columns in the `PROPERTIES(...)` clause.
    *   **Result**: These property columns will be exposed in the flattened
        output view as `EdgeAlias_propertyName`. Use this when the
        self-referential relationship itself carries important metadata (e.g.,
        `assignment_date`, `relation_type`).
2.  **Logical/Structural Edges (No Properties)**:
    *   **Approach**: Declare the table as an edge table but specify `NO
        PROPERTIES`.
    *   **Result**: The edge remains "invisible" in the output columns of the
        flattened view, while still correctly representing the hierarchical
        structure for navigation and query path resolution in the backend. Use
        this to avoid cluttering the output view when only the connectivity
        matters.

*   **Example**: Self-referential organizational chart:

```sql
CREATE OR REPLACE PROPERTY GRAPH `my-project.my_dataset.org_chart`
  NODE TABLES (
    `my-project.my_dataset.employees` AS Employee
      KEY(emp_id)
      LABEL Employee
      PROPERTIES(emp_id, name, department)
  )
  EDGE TABLES (
    -- Reusing 'employees' table purely to represent the 'reports_to' edge
    `my-project.my_dataset.employees` AS ReportsTo
      KEY(emp_id)
      SOURCE KEY(emp_id) REFERENCES Employee(emp_id)
      DESTINATION KEY(manager_id) REFERENCES Employee(emp_id)
      LABEL ReportsTo
      NO PROPERTIES -- Logical edge (structural only)
  );
```

--------------------------------------------------------------------------------

## 6. Handling Special Characters in Aliases

If you absolutely must use special characters (like hyphens or spaces) in your
aliases, you must be extremely careful with quoting.

*   **DDL Quoting**: Quoting is required in the DDL:

```sql
NODE TABLES ( my_table AS `My-Node` ... )
```

*   **Querying Quoting**: You **MUST** use backticks when referencing these
    columns in queries:

```sql
SELECT `My-Node_property` FROM GRAPH_EXPAND(...)
```

*   **Pitfall**: Omitting backticks (e.g., `SELECT My-Node_property`) causes the
    query engine to interpret the hyphen as a subtraction operator (`My` minus
    `Node_property`), throwing syntax errors.

--------------------------------------------------------------------------------

## 7. Graph Topology Pre-Flight Audit & Anti-Pattern Detection

Before generating or deploying a Property Graph DDL, execute a pre-flight topological audit to catch common modeling anti-patterns:

1.  **Zero-Degree / Island Node Check (Mandatory)**:
    *   *Anti-Pattern*: A node table declared under `NODE TABLES` has zero incident edges (no incoming and no outgoing references in `EDGE TABLES`).
    *   *Consequence*: The node cannot be reached or traversed in multi-hop GQL queries (`MATCH (a)-[r]->(b)`).
    *   *Rule*: Every node must participate in at least one edge, or be explicitly documented as a standalone lookup.

2.  **Symmetrical Multientity Edge Matching**:
    *   *Anti-Pattern*: A transaction or fact table contains foreign keys to multiple distinct entity nodes (e.g., `FactPremiosCanjeados` has `ClaveDistribuidora` AND `ClaveAsociada`), but the edge table only connects to one entity.
    *   *Consequence*: Events or spending belonging to the omitted entity become orphaned (e.g., 67.9% of prize redemptions made directly by Distributors become unreachable).
    *   *Rule*: Create dedicated, symmetrical edge tables for each participating entity (e.g., `CANJEO_PREMIO_ASOCIADA` and `CANJEO_PREMIO_DISTRIBUIDORA`).

3.  **Canonical Network vs. Temporal Facts Decoupling**:
    *   *Anti-Pattern*: Using a weekly snapshot table (e.g., `FactLinajeDistribuidoras` with 46M rows) directly as the structural edge table for network traversals.
    *   *Consequence*: Generates millions of parallel edges between the same nodes (one per week), severely degrading GQL graph traversal performance (`*1..4`).
    *   *Rule*: Create a conformed structural view (`dim_linaje_vigente`) for topological graph traversal, and keep the weekly fact table for time-series / point-in-time filtering.

4.  **Unstructured AI Rules Binding (`rel_regla_programa`)**:
    *   *Anti-Pattern*: Extracting unstructured business rules via GenAI/PDF into a `ReglaNegocio` node without bridging them to structured commercial program nodes.
    *   *Rule*: Generate a bridge relation (`rel_regla_programa`) linking `rule_id` to `program_id` with an edge `(ReglaNegocio)-[:RIGE_PROGRAMA]->(ProgramaOportunidad)`.

5.  **1-Hop Direct Aggregation Shortcuts**:
    *   *Rule*: If business users frequently aggregate group metrics at a higher hierarchy level (e.g. Distributor group sales), provide a direct 1-hop edge `(Distribuidora)-[:CONSOLIDA_VENTA]->(VentaSemanal)` alongside the 2-hop associate edge `(Distribuidora)-[:DISTRIBUYE_A]->(Asociada)-[:REALIZO_VENTA]->(VentaSemanal)`.

--------------------------------------------------------------------------------

## 8. Column Content Profiling & Cardinality Heuristics for Relationship Matching

When tables have heterogeneous column names (e.g., `categoria` in Table A vs. `cat_xpto` in Table B), naming conventions alone cannot determine relationships. Use **Data Profiling & Value Set Matching Heuristics**:

### A. Mathematical Overlap Metrics

1.  **Jaccard Similarity (Symmetric Overlap)**:
    $$J(A, B) = \frac{|A \cap B|}{|A \cup B|}$$
    *   Used to detect if two categorical columns share the exact same domain of values (e.g., `{'bronze', 'silver', 'gold'}`).
    *   Threshold: $J(A, B) \ge 0.80 \implies$ High confidence shared categorical domain.

2.  **Containment / Inclusion Ratio (Asymmetric Key Subsetting)**:
    $$C(A \subseteq B) = \frac{|A \cap B|}{|A|}$$
    *   Used to test if Table A's foreign key column is a valid subset of Table B's primary key column.
    *   Threshold: $C(A \subseteq B) \ge 0.95 \implies$ High confidence Primary Key $\rightarrow$ Foreign Key candidate.

### B. Cardinality & Distribution Profiling Matrix

| Cardinality Tier | Value Uniqueness | Overlap Ratio ($C$) | Inferred Semantic Role & Graph Modeling |
| :--- | :--- | :--- | :--- |
| **Low Cardinality** ($< 50$ distinct values) | Low ($< 1\%$ unique) | High ($J \ge 0.80$) | **Shared Categorical Dimension / Lookup Node.** Model as a shared Node (e.g. `CategoriaNivel`) or unified property enum. |
| **High Cardinality** ($> 1000$ distinct values) | Table B: $\approx 100\%$ unique, Table A: repeats | High ($C \ge 0.95$) | **Primary Key $\rightarrow$ Foreign Key Edge.** Model as an Edge Table linking `TableA` (Source) to `TableB` (Destination). |
| **High Cardinality** ($> 1000$ distinct values) | Both $\approx 100\%$ unique | High ($J \ge 0.95$) | **1:1 Entity Extension / Identity Merge.** Candidates for node consolidation or 1:1 identity edge. |
| **Temporal / Composite Format** (Matches Regex `^\d{6}$` or `^\d{4}-\d{2}$`) | Monotonic increments | High ($C \ge 0.90$) | **Temporal Coordinate.** Model as Calendar Node (`CatalogoCampana`) or integer partition key `anio_semana_key`. |

### C. BigQuery Automated Profiling SQL Pattern

```sql
-- Automated Value Set Overlap Profiler
WITH values_a AS (
  SELECT DISTINCT CAST(col_a AS STRING) AS val FROM `project.dataset.table_a` WHERE col_a IS NOT NULL
),
values_b AS (
  SELECT DISTINCT CAST(col_b AS STRING) AS val FROM `project.dataset.table_b` WHERE col_b IS NOT NULL
),
intersection_set AS (
  SELECT val FROM values_a INTERSECT DISTINCT SELECT val FROM values_b
),
union_set AS (
  SELECT val FROM values_a UNION DISTINCT SELECT val FROM values_b
)
SELECT
  (SELECT COUNT(*) FROM values_a) AS count_distinct_a,
  (SELECT COUNT(*) FROM values_b) AS count_distinct_b,
  (SELECT COUNT(*) FROM intersection_set) AS intersection_count,
  SAFE_DIVIDE((SELECT COUNT(*) FROM intersection_set), (SELECT COUNT(*) FROM union_set)) AS jaccard_similarity,
  SAFE_DIVIDE((SELECT COUNT(*) FROM intersection_set), (SELECT COUNT(*) FROM values_a)) AS containment_a_in_b,
  SAFE_DIVIDE((SELECT COUNT(*) FROM intersection_set), (SELECT COUNT(*) FROM values_b)) AS containment_b_in_a;
```

