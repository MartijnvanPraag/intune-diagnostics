# Intune Data Warehouse MCP Server

Model Context Protocol (MCP) server for querying the Microsoft Intune Data Warehouse API.

## Overview

This MCP server provides programmatic access to the Intune Data Warehouse via OData queries. It exposes device inventory, user associations, application status, compliance policies, and other Intune telemetry data.

## Architecture

- **TypeScript MCP Server**: `backend/mcp_servers/datawarehouse/` (Node.js/NPM package)
- **Python Service Wrapper**: `backend/services/datawarehouse_mcp_service.py`
- **Authentication**: OAuth 2.0 via `auth_service.py` (scope: `https://api.manage.microsoft.com/.default`)

## Available Tools

### 1. `list_entities`
List all available Data Warehouse entities with descriptions.

**Arguments**: None

**Example**:
```python
result = await datawarehouse_mcp_service.list_entities()
```

### 2. `get_entity_schema`
Get schema information for a specific entity.

**Arguments**:
- `entity` (string): Entity name (e.g., "devices", "users", "mobileApps")

**Example**:
```python
result = await datawarehouse_mcp_service.get_entity_schema("devices")
```

### 3. `query_entity`
Query an entity with OData filters and options.

**Arguments**:
- `entity` (string): Entity name
- `select` (string, optional): Comma-separated fields to select
- `filter` (string, optional): OData filter expression (e.g., `"deviceId eq 'abc-123'"`)
- `orderby` (string, optional): OData orderby expression (e.g., `"lastContact desc"`)
- `top` (number, optional): Maximum number of results
- `skip` (number, optional): Number of results to skip (pagination)
- `expand` (string, optional): Comma-separated navigation properties to expand

**Example**:
```python
result = await datawarehouse_mcp_service.query_entity(
    entity="devices",
    select="deviceId,deviceName,operatingSystem,lastContact",
    filter="operatingSystem eq 'Windows'",
    top=100,
    orderby="lastContact desc"
)
```

### 4. `execute_odata_query`
Execute a raw OData query URL.

**Arguments**:
- `url` (string): Full OData query URL (relative to base URL)

**Example**:
```python
result = await datawarehouse_mcp_service.execute_odata_query(
    url="/devices?$filter=deviceId eq 'abc-123'&$select=deviceId,deviceName"
)
```

## Available Entities

### Device Entities
- `devices` - Device inventory and properties
- `devicePropertyHistories` - Device property change history
- `deviceEnrollmentTypes` - Enrollment type reference
- `managementAgentTypes` - Management agent type reference
- `managementStates` - Device management state reference
- `ownerTypes` - Device owner type reference (Corporate/Personal)

### User Entities
- `users` - User information
- `userDeviceAssociations` - User-to-device mappings

### Application Entities
- `mobileApps` - Mobile application catalog
- `mobileAppInstallStatuses` - App installation status per device/user
- `mobileAppDeviceUserInstallStatuses` - Detailed install status

### Policy & Configuration Entities
- `deviceConfigurationPolicies` - Configuration policies (v1)
- `deviceCompliancePolicies` - Compliance policies
- `deviceCompliancePolicySettingStateSummaries` - Compliance setting state
- `deviceCompliancePolicyDeviceStateSummaries` - Per-device compliance summary

### MAM Entities
- `mamApplications` - MAM-enabled applications
- `mamApplicationInstances` - MAM app instances
- `mamApplicationHealthStates` - MAM app health status

### Reference Tables
- `dates` - Date dimension for time-based queries
- `platforms` - Platform reference (iOS, Android, Windows)

## Data Freshness

- **Refresh Rate**: Daily snapshots at Midnight UTC (24-hour freshness)
- **Use Case**: Historical/snapshot queries, device inventory, compliance status
- **Real-time Events**: Use `intune.kusto.windows.net` (central cluster) for sub-minute telemetry

## OData Query Examples

### Find device by ID
```
filter: deviceId eq '790ed67d-8983-4603-90c0-725452a273ee'
select: deviceId,deviceName,serialNumber,operatingSystem,osVersion,lastContact
```

### Get Windows devices enrolled in last 7 days
```
filter: operatingSystem eq 'Windows' and enrolledDateTime gt 2025-10-22T00:00:00Z
orderby: enrolledDateTime desc
top: 100
```

### Get app install status for a device
```
entity: mobileAppInstallStatuses
filter: deviceId eq 'abc-123'
select: appName,installState,installStateDetail,lastModifiedDateTime
```

## Known Limitations

1. **No Real-time Events**: No equivalent to `IntuneEvent` table
2. **No EffectiveGroup Tables**: Group membership data not available
3. **No Policy Assignment Data**: Use Microsoft Graph API or central cluster
4. **24-Hour Freshness**: Daily snapshots only (not real-time)

## Configuration

### Environment Variables

- `INTUNE_DATAWAREHOUSE_URL`: OData endpoint URL (default: `https://fef.msud01.manage.microsoft.com/ReportingService/DataWarehouseFEService`)
- `INTUNE_DATAWAREHOUSE_API_VERSION`: API version (default: `v1.0`)
- `MCP_INIT_TIMEOUT`: Server initialization timeout in seconds (default: `60`)

### Required Permissions

Azure AD application registration needs:
- **Permission**: "Get data warehouse information from Microsoft Intune"
- **Scope**: `https://api.manage.microsoft.com/.default`

## Development

### Build TypeScript Server
```bash
cd backend/mcp_servers/datawarehouse
npm install
npm run build
```

### Run Tests
```bash
python test_datawarehouse_mcp.py
```

### Watch Mode (Development)
```bash
cd backend/mcp_servers/datawarehouse
npm run watch
```

## Testing

The test script `test_datawarehouse_mcp.py` validates:
1. Authentication token acquisition
2. MCP server initialization
3. Entity listing
4. Schema retrieval
5. OData query execution

Run with:
```bash
python test_datawarehouse_mcp.py
```

## Hybrid Architecture

For comprehensive Intune diagnostics, use both:

**Data Warehouse API** (this server):
- Device inventory (`devices`)
- User associations (`userDeviceAssociations`)
- App install status (`mobileAppInstallStatuses`)
- Compliance policies (`deviceCompliancePolicies`)

**Central Kusto Cluster** (`intune.kusto.windows.net`):
- Real-time events (`IntuneEvent`)
- Compliance status changes (`DeviceComplianceStatusChangesByDeviceId`)
- Application install attempts (`ApplicationInstallAttemptsByDeviceId`)
- Device check-ins (`HighLevelCheckin`)
- Policy assignments (`GetAllPolicyAssignmentsForTenant`)

## References

- [Intune Data Warehouse API Documentation](https://learn.microsoft.com/en-us/intune/intune-service/developer/reports-proc-data-rest)
- [Intune Data Warehouse Data Model](https://learn.microsoft.com/en-us/intune/intune-service/developer/reports-ref-data-model)
- [Model Context Protocol Specification](https://modelcontextprotocol.io)
