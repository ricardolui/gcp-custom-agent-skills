-- ==============================================================================
-- A/B Parity Audit Template: Production Silver vs Shadow Test Silver
-- ==============================================================================
-- Parameters:
--   - <PROJECT_ID>: e.g. blip-dpl-prd-sam-i-plt-str-0
--   - <SILVER_DATASET>: e.g. silver_copilot
--   - <TABLE_NAME>: e.g. ticket_end_summary_created
--   - <PRIMARY_KEY>: e.g. ticket_id
--   - <PARTITION_DATE_FIELD>: e.g. storage_date_br or storage_date_day_br
-- ==============================================================================

WITH prod AS (
  SELECT 
    DATE(<PARTITION_DATE_FIELD>) AS dt,
    COUNT(1) AS prod_count,
    COUNT(DISTINCT <PRIMARY_KEY>) AS prod_unique_keys,
    COUNTIF(<PRIMARY_KEY> IS NULL) AS prod_null_keys
  FROM `<PROJECT_ID>.<SILVER_DATASET>.<TABLE_NAME>`
  WHERE DATE(<PARTITION_DATE_FIELD>) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY 1
),

shadow AS (
  SELECT 
    DATE(<PARTITION_DATE_FIELD>) AS dt,
    COUNT(1) AS shadow_count,
    COUNT(DISTINCT <PRIMARY_KEY>) AS shadow_unique_keys,
    COUNTIF(<PRIMARY_KEY> IS NULL) AS shadow_null_keys
  FROM `<PROJECT_ID>.<SILVER_DATASET>__kfkconn_test.<TABLE_NAME>`
  WHERE DATE(<PARTITION_DATE_FIELD>) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY 1
)

SELECT 
  COALESCE(p.dt, s.dt) AS partition_date,
  p.prod_count,
  s.shadow_count,
  (s.shadow_count - p.prod_count) AS diff_rows,
  ROUND(SAFE_DIVIDE(s.shadow_count - p.prod_count, p.prod_count) * 100, 2) AS diff_percentage,
  p.prod_unique_keys,
  s.shadow_unique_keys,
  CASE 
    WHEN p.prod_count IS NULL THEN 'SHADOW_ONLY (Pending Prod Execution)'
    WHEN s.shadow_count IS NULL THEN 'PROD_ONLY (Pending Shadow Ingestion)'
    WHEN s.shadow_count = p.prod_count THEN '100% PARITY (EXACT MATCH)'
    WHEN DATE(COALESCE(p.dt, s.dt)) = CURRENT_DATE() THEN 'IN_FLIGHT (Open Ingestion Window)'
    ELSE 'INVESTIGATE_DRIFT'
  END AS validation_status
FROM prod p
FULL OUTER JOIN shadow s ON p.dt = s.dt
ORDER BY partition_date DESC;
