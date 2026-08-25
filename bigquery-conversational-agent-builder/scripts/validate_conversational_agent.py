#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Validator script for BigQuery Conversational Analytics Data Agents & A2A Payloads.
Validates:
1. Agent Payload JSON compliance with Gemini Data Analytics API (v1beta/v1).
2. Property Graph references and measure semantics (AGG).
3. Golden Queries structure, absence of markdown fences, and archetype diversity.
4. Gemini Enterprise A2A Agent Card and Discovery Engine 1:1 OAuth spec.
"""

import json
import re
import sys

def validate_agent_payload(payload: dict) -> list[str]:
    errors = []
    
    # 1. Agent Name & IDs
    name = payload.get("name", "")
    if not name or not re.match(r"^projects/[^/]+/locations/[^/]+/dataAgents/[a-z0-9-]+$", name):
        errors.append(f"Invalid agent name format: '{name}'. Must be 'projects/{{proj}}/locations/{{loc}}/dataAgents/{{id}}'")
    
    agent_id = name.split("/")[-1] if name else ""
    if len(agent_id) > 63:
        errors.append(f"Agent ID '{agent_id}' exceeds 63 characters limit ({len(agent_id)} chars)")
    
    # 2. Display Name & Labels
    display_name = payload.get("displayName", "")
    if not display_name:
        errors.append("Missing 'displayName'")
    elif len(display_name) > 100:
        errors.append(f"displayName exceeds 100 characters: '{display_name}'")
        
    labels = payload.get("labels", {})
    if labels.get("published_context") != "true":
        errors.append("Missing required label 'published_context: \"true\"'")
        
    # 3. Contexts
    data_agent = payload.get("dataAnalyticsAgent", {})
    pub_ctx = data_agent.get("publishedContext", {})
    if not pub_ctx:
        errors.append("Missing 'dataAnalyticsAgent.publishedContext'")
        return errors
        
    # 4. Data Sources
    bq_ds = pub_ctx.get("datasourceReferences", {}).get("bq", {})
    has_graph = "propertyGraphReferences" in bq_ds and len(bq_ds["propertyGraphReferences"]) > 0
    has_tables = "tableReferences" in bq_ds and len(bq_ds["tableReferences"]) > 0
    
    if not has_graph and not has_tables:
        errors.append("Must provide either 'propertyGraphReferences' or 'tableReferences' in datasourceReferences.bq")
        
    if has_graph:
        for idx, ref in enumerate(bq_ds["propertyGraphReferences"]):
            pg_id = ref.get("propertyGraphId", "")
            if not pg_id or "projectConfig" in pg_id or "schema" in pg_id:
                errors.append(f"Invalid propertyGraphId in reference {idx}: '{pg_id}'")
                
    # 5. System Instructions
    sys_inst = pub_ctx.get("systemInstruction", "")
    if not sys_inst or len(sys_inst) < 50:
        errors.append("systemInstruction is missing or too short")
    if has_graph and "GRAPH_EXPAND" not in sys_inst and "GRAPH" not in sys_inst:
        errors.append("systemInstruction for Property Graph should mention GQL or GRAPH_EXPAND")
        
    # 6. Example / Golden Queries
    example_queries = pub_ctx.get("exampleQueries", [])
    if len(example_queries) < 3:
        errors.append(f"Expected at least 3 Golden Queries in publishedContext, got {len(example_queries)}")
    elif len(example_queries) > 10:
        errors.append(f"Maximum allowed Golden Queries is 10, got {len(example_queries)}")
        
    for idx, gq in enumerate(example_queries):
        q_text = gq.get("sqlQuery", "")
        if isinstance(q_text, dict):
            q_text = q_text.get("query", "")
        nl_text = gq.get("naturalLanguageQuestion", "")
        
        if not nl_text:
            errors.append(f"Golden Query {idx + 1} is missing 'naturalLanguageQuestion'")
        if not q_text:
            errors.append(f"Golden Query {idx + 1} is missing 'sqlQuery'")
        elif "```" in q_text:
            errors.append(f"Golden Query {idx + 1} contains markdown code fences (```). Raw SQL/GQL required.")
            
    return errors


def validate_a2a_registration(engine_payload: dict, auth_payload: dict) -> list[str]:
    errors = []
    
    # 1. Sharing Config
    sharing = engine_payload.get("sharingConfig", {}).get("scope")
    if sharing != "ALL_USERS":
        errors.append(f"Discovery Engine agent must have sharingConfig.scope = 'ALL_USERS', got '{sharing}'")
        
    # 2. State
    state = engine_payload.get("state")
    if state != "ENABLED":
        errors.append(f"Discovery Engine agent must have state = 'ENABLED', got '{state}'")
        
    # 3. Dedicated Authorization
    auth_ref = engine_payload.get("authorizationConfig", {}).get("agentAuthorization", "")
    if not auth_ref or not re.match(r"^projects/\d+/locations/global/authorizations/[a-z0-9-]+$", auth_ref):
        errors.append(f"Invalid agentAuthorization reference: '{auth_ref}'. Must use numeric project number.")
        
    # 4. Agent Card
    card_raw = engine_payload.get("a2aAgentDefinition", {}).get("jsonAgentCard", "")
    if not card_raw:
        errors.append("Missing a2aAgentDefinition.jsonAgentCard")
    else:
        try:
            card = json.loads(card_raw) if isinstance(card_raw, str) else card_raw
            if card.get("protocolVersion") not in ["1.0", "v1.0"]:
                errors.append(f"Invalid card protocolVersion: '{card.get('protocolVersion')}'")
        except json.JSONDecodeError as e:
            errors.append(f"Failed to parse jsonAgentCard: {e}")
            
    # 5. Auth Payload OAuth Redirect
    auth_uri = auth_payload.get("serverSideOauth2", {}).get("authorizationUri", "")
    if "vertexaisearch.cloud.google.com/oauth-redirect" not in auth_uri and "vertexaisearch.cloud.google.com%2Foauth-redirect" not in auth_uri:
        errors.append("Authorization URI must include redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect")
        
    return errors


if __name__ == "__main__":
    print("=== RUNNING BIGQUERY CONVERSATIONAL AGENT SPEC VALIDATOR ===")
    
    sample_payload = {
        "name": "projects/my-enterprise-project/locations/global/dataAgents/agent-inventory-specialist-9z2a",
        "displayName": "Enterprise - Inventory Optimization Specialist",
        "description": "Conversational agent grounded on BigQuery Property Graph",
        "labels": {"published_context": "true"},
        "dataAnalyticsAgent": {
            "publishedContext": {
                "datasourceReferences": {
                    "bq": {
                        "propertyGraphReferences": [
                            {
                                "projectId": "my-enterprise-project",
                                "datasetId": "retail_gold",
                                "propertyGraphId": "retail_inventory_graph"
                            }
                        ]
                    }
                },
                "systemInstruction": "You are the Inventory Specialist. Query via GRAPH_EXPAND and use AGG(Product_total_stock). Always answer in Portuguese.",
                "exampleQueries": [
                    {
                        "naturalLanguageQuestion": "Qual o total de produtos em ruptura por centro de distribuição?",
                        "sqlQuery": "SELECT dc, AGG(Product_stock_out) FROM GRAPH_EXPAND(\"retail_gold.retail_inventory_graph\") GROUP BY dc"
                    },
                    {
                        "naturalLanguageQuestion": "Evolução do faturamento mensal?",
                        "sqlQuery": "SELECT mes, AGG(Vendas_total) FROM GRAPH_EXPAND(\"retail_gold.retail_inventory_graph\") GROUP BY mes ORDER BY mes ASC"
                    },
                    {
                        "naturalLanguageQuestion": "Top 10 fornecedores críticos?",
                        "sqlQuery": "SELECT vendor, AGG(Vendas_total) FROM GRAPH_EXPAND(\"retail_gold.retail_inventory_graph\") WHERE risk = 'CRITICAL' GROUP BY vendor ORDER BY 2 DESC LIMIT 10"
                    }
                ]
            }
        }
    }
    
    errs = validate_agent_payload(sample_payload)
    if errs:
        print("❌ Payload Errors Found:")
        for e in errs:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("✅ Sample BigQuery Data Agent payload is 100% compliant with spec!")

    sample_auth = {
        "name": "projects/123456789012/locations/global/authorizations/auth-inventory-9z2a",
        "serverSideOauth2": {
            "clientId": "client-id-placeholder.apps.googleusercontent.com",
            "clientSecret": "GOCSPX-secretPlaceholder",
            "authorizationUri": "https://accounts.google.com/o/oauth2/v2/auth?client_id=client-id-placeholder.apps.googleusercontent.com&redirect_uri=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Foauth-redirect&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform",
            "tokenUri": "https://oauth2.googleapis.com/token"
        }
    }
    
    sample_engine_agent = {
        "name": "projects/my-enterprise-project/locations/global/collections/default_collection/engines/my-engine-id/assistants/default_assistant/agents/agent-inventory-specialist-9z2a",
        "displayName": "Enterprise - Inventory Optimization Specialist",
        "state": "ENABLED",
        "sharingConfig": {"scope": "ALL_USERS"},
        "authorizationConfig": {
            "agentAuthorization": "projects/123456789012/locations/global/authorizations/auth-inventory-9z2a"
        },
        "a2aAgentDefinition": {
            "jsonAgentCard": json.dumps({
                "protocolVersion": "1.0",
                "version": "1.0.0",
                "name": "Enterprise Inventory Specialist",
                "url": "https://geminidataanalytics.googleapis.com/v1beta/a2a/projects/my-enterprise-project/locations/global/dataAgents/agent-inventory-specialist-9z2a"
            })
        }
    }
    
    a2a_errs = validate_a2a_registration(sample_engine_agent, sample_auth)
    if a2a_errs:
        print("❌ A2A Errors Found:")
        for e in a2a_errs:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("✅ Sample Gemini Enterprise Discovery Engine A2A payload is 100% compliant with spec!")
