# Instructions.md Reformatting Summary

## Date: October 14, 2025

## Changes Applied

### 1. Backup Created
- Created `instructions.md.backup` as a safety copy before making any changes
- Original file: 709 lines
- Can be restored with: `Copy-Item instructions.md.backup instructions.md -Force`

### 2. Heading Level Reorganization

**Non-scenario sections changed from ### to ####:**
The following sections are global rules/legends and have been changed to #### level to distinguish them from actual diagnostic scenarios:

1. **Output Rules (Mandatory)** - Line 27
   - Global output formatting requirements
   
2. **Scope Minimization Rule (Mandatory)** - Line 47
   - Query scope and dataset selection rules
   
3. **Application Enforcement Status Legend** - Line 92
   - Reference table for application status codes
   
4. **Enrollment Type Legend** - Line 119
   - Reference table for device enrollment types
   
5. **Multi-Value Column Expansion Pattern (Readable Tables)** - Line 538
   - Kusto query pattern for expanding multi-value columns

**Diagnostic scenarios remaining at ### level (12 total):**
1. Device Details
2. User ID Lookup
3. Tenant Information
4. Device Compliance Status (Last 10 Days)
5. Policy / Setting Status and Assignments
6. Effective Group Memberships and Troubleshooting
7. MAM Policy
8. Applications
9. Third Party Integration(JAMF)
10. Identify conflicting DCv1 and DCv2 policies
11. Autopilot Summary Investigation Workflow
12. Advanced Scenario: Device Timeline

### 3. Structured Metadata Added

Each of the 12 diagnostic scenarios now includes structured metadata in HTML comment format immediately after the heading:

**Metadata Schema:**
```html
<!-- 
Metadata:
- slug: [kebab-case-identifier]
- domain: [primary-domain-category]
- keywords: [comma-separated-search-terms]
- required_identifiers: [required-parameters]
- aliases: [alternative-names]
- description: [concise-summary]
-->
```

**Example (Device Details scenario):**
```markdown
### Device Details
<!-- 
Metadata:
- slug: device-details
- domain: device
- keywords: device, details, os version, serial number, enrolled by, primary user, aad device, last contact, device name
- required_identifiers: DeviceId
- aliases: device info, device information, basic device data
- description: Retrieves comprehensive device information including OS version, enrollment details, primary user, serial number, and Azure AD identifiers
-->
```

### 4. File Statistics

**Before:**
- Total lines: 709
- Level-3 headings (###): 17
- Scenarios with metadata: 0

**After:**
- Total lines: 817 (+108 lines)
- Level-3 headings (###): 12 (all scenarios)
- Level-4 headings (####): 5 (all non-scenarios)
- Scenarios with metadata: 12 (100%)
- Metadata lines added: ~108

### 5. Metadata Details by Scenario

| Scenario | Slug | Domain | Required Identifiers |
|----------|------|--------|---------------------|
| Device Details | device-details | device | DeviceId |
| User ID Lookup | user-id-lookup | user | DeviceId |
| Tenant Information | tenant-information | tenant | AccountId |
| Device Compliance Status | device-compliance-status | compliance | DeviceId |
| Policy / Setting Status | policy-setting-status | policy | DeviceId, ContextId |
| Effective Groups | effective-groups | group | DeviceId, AccountId |
| MAM Policy | mam-policy | mam | DeviceId, ContextId |
| Applications | applications | application | DeviceId, ContextId |
| Third Party Integration | third-party-integration | integration | AccountId |
| DCv1/DCv2 Conflicts | dcv1-dcv2-conflicts | policy | DeviceId |
| Autopilot Summary | autopilot-summary | autopilot | DeviceId |
| Device Timeline | device-timeline | device | DeviceId, StartTime, EndTime |

### 6. Domain Distribution

- **device**: 3 scenarios (Device Details, Device Timeline, and parts of others)
- **policy**: 3 scenarios (Policy/Setting Status, DCv1/DCv2 Conflicts, and related)
- **compliance**: 1 scenario
- **application**: 1 scenario
- **group**: 1 scenario
- **user**: 1 scenario
- **tenant**: 1 scenario
- **mam**: 1 scenario
- **integration**: 1 scenario
- **autopilot**: 1 scenario

## Benefits of These Changes

### For Scenario Lookup Service
1. **Structured metadata** enables:
   - Exact slug matching (highest confidence)
   - Domain-based filtering
   - Enhanced keyword scoring with explicit vs. derived keywords
   - Identifier validation (required parameters)
   - Alias matching for user query variations

2. **Clear scenario identification**:
   - Only ### headings are scenarios
   - Parser can reliably extract scenario sections
   - No confusion with reference tables or global rules

### For Future Improvements
1. **Parser Enhancement**: Can extract structured metadata fields instead of relying on free-text parsing
2. **Scoring Algorithm**: Can prioritize slug/alias exact matches before keyword overlap
3. **Validation**: Can verify required identifiers are available before executing queries
4. **Documentation**: Clear separation between instructions and diagnostic procedures

## Tool Used
- **Script**: `scripts/reformat_instructions.py`
- **Approach**: Programmatic transformation to ensure consistency
- **Verification**: Confirmed 12 scenarios with metadata, 5 non-scenarios at #### level

## Rollback Instructions
If changes need to be reverted:
```powershell
Copy-Item instructions.md.backup instructions.md -Force
```

## Next Steps (Recommended)
1. **Update instructions_parser.py** to extract metadata fields from HTML comments
2. **Enhance ScenarioLookupService** to use slug/domain/alias fields for improved matching
3. **Add metadata validation** to ensure all scenarios include required fields
4. **Create tests** for metadata parsing and scenario matching accuracy
5. **Document metadata schema** for future scenario additions

## Git Status Note
The `instructions.md` file is listed in `.gitignore` (line 72), so changes are not tracked by version control. The backup file provides the safety mechanism for rollback.
