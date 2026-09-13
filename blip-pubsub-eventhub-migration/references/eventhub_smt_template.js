/**
 * Google Cloud Pub/Sub JavaScript UDF Single Message Transform (SMT)
 * Maps Azure Event Hubs ingested messages to canonical BigQuery / BigLake Iceberg schema.
 * 
 * Injected BigQuery Columns:
 * - data: STRING (original message payload)
 * - messageKey: STRING (ordering key if present)
 * - _meta_partition_id: STRING (from azure.eventhubs.partition_id or "0")
 * - _meta_sequence_number: INTEGER (from azure.eventhubs.sequence_number or 0)
 * - _meta_enqueued_time: TIMESTAMP (from azure.eventhubs.enqueued_time or publish_time)
 * - _meta_ingestion_time: TIMESTAMP (current UTC ISO string)
 * - _meta_source_signature: STRING (legacy Dataflow cluster signature, e.g. "maltes", "seq-blipprod")
 * - _meta_namespace: STRING (Azure EventHub namespace, e.g. "evhns-msging-desk-prd-maltes", "da-seq-eventhub")
 */
function transform(message, metadata) {
  var rawData = message.data;
  var attrs = message.attributes || {};
  var now = new Date().toISOString();
  
  var enqueued = attrs["azure.eventhubs.enqueued_time"] || (metadata && metadata.publish_time) || now;
  var partitionId = attrs["azure.eventhubs.partition_id"] || "0";
  var seqNum = attrs["azure.eventhubs.sequence_number"] ? parseInt(attrs["azure.eventhubs.sequence_number"], 10) : 0;
  
  // Custom metadata variables mapped per topic/tenant
  var sourceSignature = "${META_SOURCE_SIGNATURE}";
  var namespace = "${META_NAMESPACE}";
  
  var transformed = {
    data: rawData,
    messageKey: message.orderingKey || null,
    _meta_partition_id: partitionId,
    _meta_sequence_number: seqNum,
    _meta_enqueued_time: enqueued,
    _meta_ingestion_time: now,
    _meta_source_signature: sourceSignature,
    _meta_namespace: namespace
  };
  
  message.data = JSON.stringify(transformed);
  return message;
}
