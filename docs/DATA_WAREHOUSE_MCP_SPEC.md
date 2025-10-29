# Intune Data Warehouse MCP Server Specification

**Document Version:** 1.0  
**Date:** October 29, 2025  
**Author:** System Architecture  
**Status:** Draft for Review

---

## 1. Executive Summary

### 1.1 Problem Statement
The current Intune diagnostics pipeline relies on direct Kusto cluster access to snapshot databases:
- `qrybkradxeu01pe.northeurope.kusto.windows.net` (EU region)
- `qrybkradxus01pe.westus2.kusto.windows.net` (US region)

These clusters have been moved to a more secure environment and are no longer accessible via corporate accounts. There is no workaround available.

### 1.2 Proposed Solution
Implement a new MCP (Model Context Protocol) server that wraps the **Intune Data Warehouse API** to provide equivalent data access through Microsoft's official REST OData endpoints.

### 1.3 Key Objectives
1. **Replace** snapshot cluster queries with Data Warehouse API calls
2. **Maintain** existing agent capabilities and query patterns
3. **Preserve** authentication flow using existing Azure credentials
4. **Enable** OData query capabilities for the AI agent
5. **Provide** schema discovery and entity exploration

---

## 2. Architecture Overview

### 2.1 Component Structure
```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Framework                           │
│              (agent_framework_service.py)                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ Uses tools
                        ▼
┌─────────────────────────────────────────────────────────────┐
│          Data Warehouse MCP Service (NEW)                   │
│        (datawarehouse_mcp_service.py)                       │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  MCP Client Session (Python SDK)                   │    │
│  │  - Manages lifecycle of MCP server process          │    │
│  │  - Handles stdio communication                      │    │
│  │  - Provides tool call interface                     │    │
│  └────────────────────────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ Spawns & communicates via stdio
                        ▼
┌─────────────────────────────────────────────────────────────┐
│       Data Warehouse MCP Server (NEW)                       │
│    (@mcp-apps/intune-datawarehouse-server or custom)       │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Tools:                                             │    │
│  │  - query_entity                                     │    │
│  │  - list_entities                                    │    │
│  │  - get_entity_schema                                │    │
│  │  - execute_odata_query                              │    │
│  └────────────────────────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ HTTPS REST API calls
                        ▼
┌─────────────────────────────────────────────────────────────┐
│          Intune Data Warehouse REST API                     │
│   https://fef.msud01.manage.microsoft.com/                  │
│   ReportingService/DataWarehouseFEService?api-version=v1.0  │
│                                                              │
│  Authentication: OAuth 2.0 Bearer Token                     │
│  Resource: https://api.manage.microsoft.com/               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Authentication Flow
```
┌──────────────┐
│ Agent calls  │
│ DW tool      │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ datawarehouse_mcp_service.py             │
│                                          │
│ 1. Check if session initialized          │
│ 2. If not, spawn MCP server process      │
│ 3. Acquire token from AuthService        │
│ 4. Pass token to MCP server via params   │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ auth_service.py                          │
│                                          │
│ 1. Use DefaultAzureCredential            │
│ 2. Get token for scope:                  │
│    "https://api.manage.microsoft.com/    │
│    .default"                             │
│ 3. Cache token with expiry               │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ MCP Server receives:                     │
│ - accessToken (Bearer token)             │
│ - warehouseUrl                           │
│ - entity name / OData query              │
│                                          │
│ Makes HTTPS call with:                   │
│ Authorization: Bearer <token>            │
└──────────────────────────────────────────┘
```

---

## 3. Data Warehouse API Details

### 3.1 Base Configuration
- **OData URL:** `https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService?api-version=v1.0`
- **API Version:** `v1.0`
- **Protocol:** OData v4
- **Authentication:** OAuth 2.0
- **Required Scope:** `https://api.manage.microsoft.com/.default`
- **Required Permission:** `Get data warehouse information from Microsoft Intune` (Delegated)

### 3.2 Available Entities

Based on [Microsoft documentation](https://learn.microsoft.com/en-us/intune/intune-service/developer/reports-ref-data-model), the Data Warehouse exposes entities in these categories:

#### Device Entities
- `devices` - Device inventory and properties
- `devicePropertyHistories` - Device property change history  
- `deviceEnrollmentTypes` - Enrollment type reference data
- `managementAgentTypes` - Management agent type reference
- `managementStates` - Device management state reference
- `ownerTypes` - Device owner type reference (Corporate/Personal)

#### User Entities
- `users` - User information
- `userDeviceAssociations` - User-to-device mappings

#### Application Entities
- `mobileApps` - Mobile application catalog
- `mobileAppInstallStatuses` - App installation status per device/user
- `mobileAppDeviceUserInstallStatuses` - Detailed install status

#### Policy & Configuration Entities
- `deviceConfigurationPolicies` - Configuration policies (limited to v1 policies)
- `deviceCompliancePolicies` - Compliance policies
- `deviceCompliancePolicySettingStateSummaries` - Compliance setting state
- `deviceCompliancePolicyDeviceStateSummaries` - Per-device compliance summary

#### MAM (Mobile Application Management) Entities
- `mamApplications` - MAM-enabled applications
- `mamApplicationInstances` - MAM app instances
- `mamApplicationHealthStates` - MAM app health status

#### Reference/Dimension Tables
- `dates` - Date dimension for time-based queries
- `platforms` - Platform reference (iOS, Android, Windows, etc.)

**Important Notes:**
- **NO EffectiveGroup entities** - Group membership data not available
- **NO IntuneEvent equivalent** - Real-time event telemetry must use central cluster
- **NO Policy assignment tables** - Use Microsoft Graph API for policy targeting
- **NO Snapshot-style tables** - Data model is different from Kusto snapshots

### 3.3 OData Query Capabilities
The API supports standard OData query options:
- `$select` - Select specific fields
- `$filter` - Filter results (e.g., `deviceId eq 'abc-123'`)
- `$orderby` - Sort results
- `$top` - Limit number of results
- `$skip` - Pagination
- `$expand` - Expand navigation properties
- `$count` - Get result count

**Example Query:**
```
GET https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService/devices
    ?api-version=v1.0
    &$filter=deviceId eq '790ed67d-8983-4603-90c0-725452a273ee'
    &$select=deviceId,deviceName,serialNumber,operatingSystem,osVersion,lastContact
```

---

## 4. MCP Server Specification

### 4.1 Server Implementation Options

#### TypeScript/JavaScript NPM Package (SELECTED)
**Rationale:** Reuse existing Node.js MCP patterns (like Kusto MCP), consistent with current architecture

**Package Name:** `@local/intune-datawarehouse-mcp-server`

**Location:** `backend/mcp_servers/datawarehouse/` (or separate npm workspace)

**Structure:**
```
backend/mcp_servers/datawarehouse/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts           # Main MCP server entry point
│   ├── server.ts          # MCP server implementation
│   ├── client.ts          # HTTP client for Data Warehouse API
│   ├── entities.ts        # Entity definitions & metadata
│   ├── schema.ts          # Entity schema cache
│   └── types.ts           # TypeScript types
├── dist/                  # Compiled JavaScript
└── README.md              # Server documentation
```

**Dependencies:**
```json
{
  "@modelcontextprotocol/sdk": "^0.5.0",
  "axios": "^1.6.0",
  "@azure/identity": "^4.0.0"
}
```

### 4.2 MCP Tools Interface

#### Tool 1: `list_entities`
**Purpose:** Discover available Data Warehouse entities

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "category": {
      "type": "string",
      "description": "Optional category filter: device, user, policy, application, reference",
      "enum": ["device", "user", "policy", "application", "reference", "all"]
    }
  }
}
```

**Output:**
```json
{
  "entities": [
    {
      "name": "devices",
      "category": "device",
      "description": "Device inventory and properties",
      "primaryKey": "deviceKey",
      "commonFilters": ["deviceId", "serialNumber", "lastContact"]
    },
    {
      "name": "users",
      "category": "user",
      "description": "User information",
      "primaryKey": "userKey",
      "commonFilters": ["userId", "userPrincipalName"]
    }
  ]
}
```

#### Tool 2: `get_entity_schema`
**Purpose:** Get detailed schema for a specific entity

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "entity": {
      "type": "string",
      "description": "Entity name (e.g., 'devices', 'users')"
    }
  },
  "required": ["entity"]
}
```

**Output:**
```json
{
  "entity": "devices",
  "fields": [
    {
      "name": "deviceKey",
      "type": "Edm.Int64",
      "nullable": false,
      "description": "Unique identifier (warehouse surrogate key)"
    },
    {
      "name": "deviceId",
      "type": "Edm.Guid",
      "nullable": false,
      "description": "Intune Device ID"
    },
    {
      "name": "deviceName",
      "type": "Edm.String",
      "nullable": true,
      "description": "Device name"
    },
    {
      "name": "serialNumber",
      "type": "Edm.String",
      "nullable": true,
      "description": "Device serial number"
    }
  ],
  "navigationProperties": [
    {
      "name": "deviceEnrollmentType",
      "targetEntity": "deviceEnrollmentTypes"
    }
  ]
}
```

#### Tool 3: `query_entity`
**Purpose:** Execute a query against a specific entity with filters

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "entity": {
      "type": "string",
      "description": "Entity name (e.g., 'devices')"
    },
    "filter": {
      "type": "string",
      "description": "OData $filter expression (e.g., \"deviceId eq '123-456'\")"
    },
    "select": {
      "type": "string",
      "description": "Comma-separated list of fields to return (optional)"
    },
    "orderby": {
      "type": "string",
      "description": "OData $orderby expression (optional)"
    },
    "top": {
      "type": "integer",
      "description": "Maximum number of results (default: 100, max: 1000)",
      "default": 100
    },
    "skip": {
      "type": "integer",
      "description": "Number of results to skip for pagination",
      "default": 0
    },
    "expand": {
      "type": "string",
      "description": "Navigation properties to expand (optional)"
    }
  },
  "required": ["entity"]
}
```

**Output:**
```json
{
  "success": true,
  "entity": "devices",
  "count": 1,
  "data": [
    {
      "deviceKey": 12345,
      "deviceId": "790ed67d-8983-4603-90c0-725452a273ee",
      "deviceName": "LAPTOP-ABC123",
      "serialNumber": "SN123456",
      "operatingSystem": "Windows",
      "osVersion": "10.0.22631",
      "lastContact": "2025-10-29T10:30:00Z"
    }
  ],
  "nextLink": null
}
```

#### Tool 4: `execute_odata_query`
**Purpose:** Execute a custom OData query with full control

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "odataPath": {
      "type": "string",
      "description": "Full OData path after base URL (e.g., 'devices?$filter=deviceId eq \"123\"&$select=deviceName,serialNumber')"
    }
  },
  "required": ["odataPath"]
}
```

**Output:**
```json
{
  "success": true,
  "data": { /* OData response */ },
  "metadata": {
    "odataContext": "...",
    "count": 1
  }
}
```

---

## 5. Service Implementation (`datawarehouse_mcp_service.py`)

### 5.1 Class Structure

```python
class DataWarehouseMCPService:
    """
    Intune Data Warehouse MCP service using the official MCP Python SDK.
    
    Wraps the Data Warehouse OData API to provide structured access to
    Intune telemetry data as a replacement for snapshot Kusto clusters.
    """
    
    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self.is_initialized = False
        self._init_lock = asyncio.Lock()
        self._tool_names: List[str] = []
        
        # Configuration
        self.warehouse_url = os.getenv(
            "INTUNE_WAREHOUSE_URL",
            "https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService"
        )
        self.api_version = "v1.0"
        
    async def initialize(self):
        """Initialize MCP server connection"""
        
    async def cleanup(self):
        """Cleanup MCP resources"""
        
    async def query_entity(
        self,
        entity: str,
        filter: Optional[str] = None,
        select: Optional[str] = None,
        orderby: Optional[str] = None,
        top: int = 100,
        skip: int = 0,
        expand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Query a Data Warehouse entity with OData parameters"""
        
    async def list_entities(self, category: str = "all") -> Dict[str, Any]:
        """List available Data Warehouse entities"""
        
    async def get_entity_schema(self, entity: str) -> Dict[str, Any]:
        """Get schema information for an entity"""
        
    async def execute_odata_query(self, odata_path: str) -> Dict[str, Any]:
        """Execute a raw OData query"""
```

### 5.2 Key Methods

#### `initialize()`
- Spawn MCP server process via `stdio_client`
- Enter async context for `ClientSession`
- Verify tool availability
- Cache entity metadata (optional optimization)

#### `query_entity()`
- Primary query method for agents
- Construct OData query from parameters
- Acquire access token from `auth_service`
- Call MCP tool with token + query
- Parse and normalize response

#### `_acquire_token()`
```python
async def _acquire_token(self) -> str:
    """Acquire Data Warehouse access token from auth service"""
    from backend.services.auth_service import auth_service
    
    # Use the Intune API scope
    scope = "https://api.manage.microsoft.com/.default"
    token = await auth_service.get_token_async(scope)
    
    if not token:
        raise RuntimeError("Failed to acquire Intune Data Warehouse token")
    
    return token
```

---

## 6. Query Translation Strategy

### 6.1 Current Snapshot Queries → Data Warehouse Mapping

#### Example 1: Device Details
**Current (Snapshot Kusto):**
```kusto
let DeviceID = '790ed67d-8983-4603-90c0-725452a273ee';
let base_query = (cluster: string, source: string) {
    cluster(cluster).database("qrybkradxglobaldb").Device_Snapshot()
        | where DeviceId == DeviceID
};
union
   base_query('qrybkradxeu01pe.northeurope.kusto.windows.net', 'europe'),  
   base_query('qrybkradxus01pe.westus2.kusto.windows.net', 'Non-EU')
```

**New (Data Warehouse OData):**
```python
await datawarehouse_service.query_entity(
    entity="devices",
    filter=f"deviceId eq '{device_id}'",
    select="deviceId,deviceName,serialNumber,operatingSystem,osVersion,lastContact,enrolledDateTime"
)
```

#### Example 2: User-Device Association
**Current (Snapshot Kusto):**
```kusto
cluster("intune.kusto.windows.net").database("intune").IntuneEvent
| where DeviceId == "<DeviceId>"
| project UserId
```

**New (Data Warehouse OData):**
```python
await datawarehouse_service.query_entity(
    entity="userDeviceAssociations",
    filter=f"deviceId eq '{device_id}'",
    select="userId,userPrincipalName,isPrimaryUser"
)
```

### 6.2 Translation Gaps & Limitations

#### Known Limitations
1. **24-Hour Data Freshness:** Data Warehouse is updated daily at Midnight UTC (same as snapshot clusters)
2. **No Real-time Events:** No equivalent to `IntuneEvent` table for sub-minute telemetry
3. **No EffectiveGroup Tables:** May not have `EffectiveGroupMembershipV2_Snapshot` equivalent
4. **No Policy Assignment Data:** Policy targeting information not available

#### Hybrid Architecture (CONFIRMED)
**Central Intune Cluster Remains Accessible:** `intune.kusto.windows.net` is **STILL OPERATIONAL** for real-time queries.

**Query Routing Strategy:**
- **Data Warehouse API** → Historical/snapshot data (devices, users, apps, compliance)
- **intune.kusto.windows.net** → Real-time events (IntuneEvent, DeviceComplianceStatusChangesByDeviceId, ApplicationInstallAttemptsByDeviceId, HighLevelCheckin, GetAllPolicyAssignmentsForTenant)

**Device Timeline Integration:**
- Steps 1, 3, 4, 5: Replace with Data Warehouse API
- Steps 2, 6, 7, 8: Continue using central cluster (NO CHANGES)

#### Mitigation Strategies
1. **Hybrid Approach:** Data Warehouse + central cluster (confirmed working)
2. **Supplemental Graph API:** Use Microsoft Graph for group memberships (fallback)
3. **Agent Query Routing:** Agent framework intelligently routes to Data Warehouse MCP vs Kusto MCP
4. **24-Hour Freshness Acceptable:** Matches previous snapshot cluster refresh rate

---

## 7. AuthService Integration

### 7.1 New Token Scope

Add to `auth_service.py`:

```python
class AuthService:
    def __init__(self):
        # ... existing code ...
        self.intune_api_scope = "https://api.manage.microsoft.com/.default"
        self._intune_token_cache: Optional[Tuple[float, str]] = None
    
    async def get_intune_datawarehouse_token(self) -> str:
        """
        Acquire access token for Intune Data Warehouse API.
        
        Returns:
            Bearer token string
        """
        # Check cache
        if self._intune_token_cache:
            expiry, token = self._intune_token_cache
            if time.time() < expiry - 300:  # 5 min buffer
                logger.debug("Using cached Intune Data Warehouse token")
                return token
        
        # Acquire new token
        try:
            self._ensure_credentials_initialized()
            logger.info("Acquiring Intune Data Warehouse token...")
            
            token_obj = self.credential.get_token(self.intune_api_scope)
            token = token_obj.token
            expiry = token_obj.expires_on
            
            # Cache
            self._intune_token_cache = (expiry, token)
            logger.info(f"Intune Data Warehouse token acquired (expires: {expiry})")
            
            return token
        except ClientAuthenticationError as e:
            logger.error(f"Failed to acquire Intune token: {e}")
            raise RuntimeError("Intune Data Warehouse authentication failed") from e
```

### 7.2 Permission Requirements

**App Registration (if using service principal):**
- API Permission: `Microsoft Intune API` → `Get data warehouse information from Microsoft Intune`
- Permission Type: Delegated
- Admin Consent: Required

**User Account (if using interactive):**
- Must have Intune permissions to read Data Warehouse
- Typically requires Intune Administrator or Global Reader role

---

## 8. Agent Integration

### 8.1 Tool Registration

In `agent_framework_service.py`, register Data Warehouse tools:

```python
# Add to tool definitions
datawarehouse_tools = [
    {
        "type": "function",
        "function": {
            "name": "query_datawarehouse_entity",
            "description": """
                Query Intune Data Warehouse entity with OData filters.
                Use this to retrieve device, user, policy, or application data
                when snapshot cluster queries are not available.
                
                Examples:
                - Get device details: entity='devices', filter="deviceId eq 'abc-123'"
                - Get user info: entity='users', filter="userId eq 'user-guid'"
                - Get app install status: entity='mobileAppInstallStatuses', filter="deviceId eq 'abc-123'"
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Entity name (devices, users, mobileApps, etc.)"
                    },
                    "filter": {
                        "type": "string",
                        "description": "OData $filter expression"
                    },
                    "select": {
                        "type": "string",
                        "description": "Comma-separated field list"
                    },
                    "top": {
                        "type": "integer",
                        "description": "Max results (default 100)"
                    }
                },
                "required": ["entity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_datawarehouse_entities",
            "description": "List available Data Warehouse entities to discover queryable data sources",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["device", "user", "policy", "application", "all"]
                    }
                }
            }
        }
    }
]
```

### 8.2 Tool Handlers

```python
async def handle_query_datawarehouse_entity(self, **kwargs):
    """Handle Data Warehouse entity query"""
    result = await self.datawarehouse_service.query_entity(**kwargs)
    
    if not result.get("success"):
        return {"error": result.get("error", "Unknown error")}
    
    # Format as markdown table for agent
    data = result.get("data", [])
    if not data:
        return {"message": "No data found", "count": 0}
    
    # Convert to markdown table
    table = self._format_as_table(data)
    return {
        "table": table,
        "count": len(data),
        "raw_data": data
    }
```

### 8.3 Instructions Update

Add to `instructions.md`:

```markdown
### Using Data Warehouse API

When snapshot clusters are unavailable, use the Data Warehouse API:

**Important Constraints:**
- Data is refreshed **daily** (not real-time)
- Historical data retention: typically 30 days
- OData query limits: max 1000 results per request

**Available Entities:**
- `devices` - Device inventory
- `users` - User information
- `userDeviceAssociations` - User-device relationships
- `mobileAppInstallStatuses` - App installation status
- `deviceCompliancePolicySettingStateSummaries` - Compliance state

**Query Pattern:**
1. Use `list_datawarehouse_entities` to discover entities
2. Use `query_datawarehouse_entity` with OData filters
3. Always specify `deviceId`, `userId`, or other key filters
4. Use `$select` to limit fields and improve performance

**Example:**
```
query_datawarehouse_entity(
    entity="devices",
    filter="deviceId eq '790ed67d-8983-4603-90c0-725452a273ee'",
    select="deviceName,serialNumber,osVersion,lastContact"
)
```
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

**File:** `tests/test_datawarehouse_mcp_service.py`

```python
import pytest
from backend.services.datawarehouse_mcp_service import DataWarehouseMCPService

@pytest.mark.asyncio
async def test_list_entities():
    service = DataWarehouseMCPService()
    await service.initialize()
    
    result = await service.list_entities()
    assert "entities" in result
    assert len(result["entities"]) > 0
    
    await service.cleanup()

@pytest.mark.asyncio
async def test_query_devices():
    service = DataWarehouseMCPService()
    await service.initialize()
    
    result = await service.query_entity(
        entity="devices",
        filter="deviceId eq 'test-device-id'",
        top=10
    )
    
    assert result["success"] == True
    assert "data" in result
    
    await service.cleanup()
```

### 9.2 Integration Tests

Test end-to-end flow:
1. Token acquisition via AuthService
2. MCP server spawn and initialization
3. Actual API call to Data Warehouse
4. Response parsing and formatting

### 9.3 Manual Testing Checklist

- [ ] Authenticate with corporate account
- [ ] List all entities successfully
- [ ] Query `devices` entity by deviceId
- [ ] Query `users` entity by userId
- [ ] Test OData filters (`$filter`, `$select`, `$top`)
- [ ] Test pagination (`$skip`, `$top`)
- [ ] Verify error handling (invalid entity, bad filter syntax)
- [ ] Test token expiry and refresh
- [ ] Load test (100+ queries)

---

## 10. Migration Plan

### 10.1 Phase 1: Foundation (Week 1)
- [ ] Create `datawarehouse_mcp_service.py` skeleton
- [ ] Implement basic MCP server (Python or TypeScript)
- [ ] Add token acquisition to `auth_service.py`
- [ ] Test authentication flow manually

### 10.2 Phase 2: Core Tools (Week 2)
- [ ] Implement `list_entities` tool
- [ ] Implement `query_entity` tool
- [ ] Add entity schema metadata
- [ ] Write unit tests

### 10.3 Phase 3: Agent Integration (Week 3)
- [ ] Register tools in agent framework
- [ ] Update `instructions.md` with Data Warehouse guidance
- [ ] Create query translation examples
- [ ] Test device details scenario end-to-end

### 10.4 Phase 4: Full Replacement (Week 4)
- [ ] Identify all snapshot cluster queries in `instructions.md`
- [ ] Create Data Warehouse equivalents where possible
- [ ] Document gaps and limitations
- [ ] Update agent instructions for hybrid approach
- [ ] Deploy to production

---

## 11. Known Gaps & Alternatives

### 11.1 Data Not Available in Data Warehouse

| Snapshot Query | Data Warehouse Equivalent | Fallback Option |
|----------------|---------------------------|-----------------|
| `IntuneEvent` (real-time events) | ❌ Not available | Use `intune.kusto.windows.net` if accessible, or Graph API activity logs |
| `EffectiveGroupMembershipV2_Snapshot` | ❌ Not available | Microsoft Graph `/groups` API |
| `PolicySettingMapV3_Snapshot` | ❌ Not available | Graph API `/deviceManagement/configurationPolicies` |
| `ApplicationInstallAttemptsByDeviceId` | ⚠️ Partial (`mobileAppInstallStatuses`) | Graph API `/deviceManagement/managedDevices/{id}/appInstalls` |

### 11.2 Recommended Hybrid Approach

1. **Data Warehouse (Primary):** Historical device/user/policy data
2. **Central Intune Cluster (Secondary):** Real-time event telemetry if accessible
3. **Microsoft Graph API (Tertiary):** Missing entities (groups, real-time status)

---

## 12. Success Criteria

### 12.1 Functional Requirements
- [ ] Agent can query device details by deviceId
- [ ] Agent can retrieve user information by userId
- [ ] Agent can access compliance policy status
- [ ] Agent can list application install status
- [ ] All queries return data in <5 seconds (95th percentile)

### 12.2 Non-Functional Requirements
- [ ] Token caching prevents excessive auth requests
- [ ] MCP server startup time <10 seconds
- [ ] Graceful error handling for missing entities
- [ ] Logging captures all API calls for debugging
- [ ] Documentation complete and accurate

---

## 13. Requirements Confirmed

All open questions have been answered:

1. **Entity Coverage:** ✅ **CONFIRMED** - Data model documented at https://learn.microsoft.com/en-us/intune/intune-service/developer/reports-ref-data-model
   - See Section 3.2 for complete entity list
   - Notable gaps: No EffectiveGroup tables, No Policy assignment data

2. **Real-time Events:** ✅ **CONFIRMED** - Central cluster `intune.kusto.windows.net` **REMAINS ACCESSIBLE**
   - Hybrid approach documented in Section 6.2
   - Device Timeline Steps 2, 6, 7, 8 continue using central cluster

3. **Data Freshness:** ✅ **CONFIRMED** - 24 hours (daily snapshots at Midnight UTC)
   - Same refresh rate as previous snapshot clusters
   - Acceptable for historical/diagnostic queries

4. **Rate Limits:** ✅ **CONFIRMED** - No rate limiting concerns
   - No special throttling handling required
   - Standard HTTP retry logic sufficient

5. **Schema Discovery:** ✅ **CONFIRMED** - Fetch on-demand
   - Entity schemas retrieved via OData $metadata endpoint
   - No pre-caching required
   - `get_entity_schema` tool fetches schema when needed

6. **MCP Server Tech:** ✅ **CONFIRMED** - TypeScript NPM package (Section 4.1)
   - Package name: `@local/intune-datawarehouse-mcp-server`
   - Location: `backend/mcp_servers/datawarehouse/`
   - Consistent with existing kusto_mcp_service pattern

7. **Autopilot Data & Prioritization:** ✅ **CONFIRMED** - Focus on `device_timeline` scenario only
   - ESP/Autopilot scenarios deferred to Phase 2
   - Priority: Replace Steps 1, 3, 4, 5 in device_timeline workflow
   - Steps requiring Data Warehouse replacement:
     - Step 1: Device_Snapshot → `devices` entity
     - Step 3: EffectiveGroupMembershipV2_Snapshot → Graph API fallback (not in Data Warehouse)
     - Step 4: EffectiveGroup_Snapshot → Graph API fallback (not in Data Warehouse)
     - Step 5: Deployment_Snapshot → TBD (investigate `mobileAppInstallStatuses` entity)

---

## 14. Next Steps

### Immediate Actions (Ready to Implement)

1. **TypeScript MCP Server Development**
   - Create `backend/mcp_servers/datawarehouse/` directory structure
   - Implement 4 MCP tools: `list_entities`, `get_entity_schema`, `query_entity`, `execute_odata_query`
   - HTTP client with OAuth token handling
   - OData query builder utilities

2. **Python Service Wrapper**
   - Implement `backend/services/datawarehouse_mcp_service.py`
   - Follow `kusto_mcp_service.py` pattern (AsyncExitStack, stdio_client, ClientSession)
   - Token acquisition via AuthService

3. **AuthService Extension**
   - Add `intune_api_scope = "https://api.manage.microsoft.com/.default"`
   - Implement `get_intune_datawarehouse_token()` with caching

4. **Agent Framework Integration**
   - Register Data Warehouse MCP server in agent tool registry
   - Implement query routing logic (Data Warehouse vs Kusto MCP)
   - Update device_timeline scenario in instructions.md

5. **Manual API Testing**
   - Validate entity availability via Postman/curl
   - Confirm OData query patterns work as expected
   - Document entity-to-Kusto table mappings for device_timeline

### Implementation Phases (Per Section 11)

- **Phase 1:** Foundation (MCP server, service wrapper, auth)
- **Phase 2:** Agent integration (tool registration, query routing)
- **Phase 3:** device_timeline migration (Steps 1, 3, 4, 5 replacement)
- **Phase 4:** Testing & documentation

**Specification Status:** ✅ **READY FOR IMPLEMENTATION** - All requirements confirmed

---

## Appendix A: Reference Links

- [Intune Data Warehouse API Documentation](https://learn.microsoft.com/en-us/intune/intune-service/developer/reports-proc-data-rest)
- [Intune Data Warehouse Data Model](https://learn.microsoft.com/en-us/intune/intune-service/developer/reports-ref-data-model)
- [OData v4 Query Options](https://www.odata.org/getting-started/basic-tutorial/#queryData)
- [MCP Python SDK Documentation](https://github.com/modelcontextprotocol/python-sdk)
- [Azure Identity DefaultAzureCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential)

---

## Appendix B: Sample API Responses

### Example: Query Devices Entity
**Request:**
```http
GET https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService/devices?api-version=v1.0&$filter=deviceId eq '790ed67d-8983-4603-90c0-725452a273ee'&$select=deviceName,serialNumber,osVersion
Authorization: Bearer <token>
```

**Response:**
```json
{
  "@odata.context": "https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService/$metadata#devices(deviceName,serialNumber,osVersion)",
  "value": [
    {
      "deviceName": "LAPTOP-ABC123",
      "serialNumber": "SN123456789",
      "osVersion": "10.0.22631"
    }
  ]
}
```

---

**End of Specification**
