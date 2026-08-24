# Gemini Enterprise & Discovery Engine A2A (Agent2Agent) Integration

This document defines the configuration rules for registering BigQuery Conversational Analytics Data Agents as federated **Agent2Agent (A2A)** resources in **Gemini Enterprise (Discovery Engine)**.

---

## 1. REST Endpoints & Service Names

- **Discovery Engine Endpoint**: `https://discoveryengine.googleapis.com/v1alpha/projects/{hostProjectId}/locations/global/authorizations`
- **Assistant Resource**: `projects/{hostProjectId}/locations/global/collections/default_collection/engines/{engineId}/assistants/default_assistant`
- **Agent Resource URI**: `https://geminidataanalytics.googleapis.com/v1beta/a2a/projects/{sourceProjectId}/locations/global/dataAgents/{agentId}`

---

## 2. Dedicated 1:1 OAuth 2.0 Authorization Standard

Discovery Engine enforces a strict 1-to-1 relationship between an Agent and its Authorization resource (`projects/.../locations/global/authorizations/...`). Sharing an authorization resource across multiple agents causes:
`400 FAILED_PRECONDITION: Authorization resource is already used by another agent.`

### 2.1. Authorization Creation Payload
```bash
POST https://discoveryengine.googleapis.com/v1alpha/projects/{hostProjectId}/locations/global/authorizations?authorizationId={authId}
```

```json
{
  "name": "projects/{hostProjectId}/locations/global/authorizations/{authId}",
  "serverSideOauth2": {
    "clientId": "1234567890-abc.apps.googleusercontent.com",
    "clientSecret": "GOCSPX-YourClientSecretPlaceholder",
    "authorizationUri": "https://accounts.google.com/o/oauth2/v2/auth?client_id={clientId}&redirect_uri=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Foauth-redirect&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcloud-platform+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.email&include_granted_scopes=true&response_type=code&access_type=offline&prompt=consent",
    "tokenUri": "https://oauth2.googleapis.com/token"
  }
}
```

### 2.2. Critical Authorization Rules:
1. **Unique Auth ID**: `authId = "auth-" + agentId + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).substring(2, 4)`.
2. **Canonical Numeric Project Number**: Always use the numeric project number (e.g., `projects/123456789012/locations/global/authorizations/...`). Passing a text project ID string causes `400 INVALID_ARGUMENT: Invalid Authorization name`.
3. **Redirect URI Whitelist**: The OAuth 2.0 Client ID in Google Cloud Console must explicitly allow:
   - `https://vertexaisearch.cloud.google.com/oauth-redirect`
   - `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`

---

## 3. A2A Agent Card & Discovery Engine Registration

### 3.1. Agent Card JSON Payload (Spec v1.0.0)
```json
{
  "protocolVersion": "1.0",
  "name": "projects/my-project/locations/global/dataAgents/agent-inventory-01",
  "displayName": "O Boticário - Inventory Specialist",
  "description": "Conversational agent grounded on BigQuery Property Graph",
  "version": "1.0.0",
  "url": "https://geminidataanalytics.googleapis.com/v1beta/a2a/projects/my-project/locations/global/dataAgents/agent-inventory-01",
  "capabilities": {
    "streaming": false
  },
  "skills": [
    {
      "name": "query_property_graph",
      "description": "Queries BigQuery Property Graph using GQL and Semantic Measures (AGG)."
    }
  ],
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"]
}
```

### 3.2. Discovery Engine Assistant Registration Payload
```bash
POST https://discoveryengine.googleapis.com/v1alpha/projects/{hostProjectId}/locations/global/collections/default_collection/engines/{engineId}/assistants/default_assistant/agents?agentId={engineAgentId}
```

```json
{
  "name": "projects/{hostProjectId}/locations/global/collections/default_collection/engines/{engineId}/assistants/default_assistant/agents/{engineAgentId}",
  "displayName": "O Boticário - Inventory Specialist",
  "description": "Conversational agent grounded on BigQuery Property Graph",
  "state": "ENABLED",
  "sharingConfig": {
    "scope": "ALL_USERS"
  },
  "authorizationConfig": {
    "agentAuthorization": "projects/{projectNumber}/locations/global/authorizations/{authId}"
  },
  "a2aAgentDefinition": {
    "jsonAgentCard": "{\"protocolVersion\":\"1.0\",\"version\":\"1.0.0\", ... }"
  }
}
```

> **CRITICAL**: Without `"sharingConfig": { "scope": "ALL_USERS" }` and `"state": "ENABLED"`, the agent defaults to private (`null`) and will NOT be visible in the Gemini Enterprise Agent Gallery or Search Assistant UI.
