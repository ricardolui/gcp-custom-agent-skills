-- ==============================================================================
-- Compatibility Views DDL: Bridging Confluent Cloud SMT to Dataform Declarations
-- ==============================================================================
-- When Confluent Kafka Connect prefixes tables with `prod_` or tenant names,
-- create a zero-cost compatibility view to prevent `Table not found` in Dataform.
-- ==============================================================================

-- Copilot Ticket End Summary
CREATE OR REPLACE VIEW `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_ticket_end_summary_created` AS
SELECT * FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_prod_copilot_ticket_end_summary_created`;

-- Copilot Ticket Start Summary
CREATE OR REPLACE VIEW `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_ticket_start_summary_created` AS
SELECT * FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_prod_copilot_ticket_start_summary_created`;

-- Copilot Event Tracked
CREATE OR REPLACE VIEW `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_event_tracked` AS
SELECT * FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_prod_copilot_event_tracked`;

-- Active Campaign
CREATE OR REPLACE VIEW `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_activecampaign` AS
SELECT * FROM `blip-dpl-prd-sam-i-plt-str-0.raw_platform_kfkconn.imt_prod_active_campaign`;
