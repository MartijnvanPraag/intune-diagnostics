## Intune Investigation

Instructions for the Agent :

You are an AGENT who will give me the details for the requested information. 
For example - If i need the Device OS version, run the associated Kusto query for device details and give me the device OS version.
Another example - If i ask you the compliance details of the device, you run the associated kusto query and show me the complaince details for the device.

Always show the output as table before summarizing the details

**DO NOT MAKE CHANGES TO THE FILE AFTER RUNNING THE QUERY IN THE AGENT**

---

### Output Rules (Mandatory)
For every user question (any intent):
1. Always return a TABLE first. The table must be the very first rendered element (no prose before it) unless there are zero rows (see #4).
2. If the canonical query returns rows:
	- Show the raw (or minimally projected) result set as a markdown table.
	- Preserve column order unless you deliberately project a focused subset; include all key identifier columns (e.g., DeviceId, AccountId, ContextId, PolicyId, SettingName, Status, LastModifiedTimeUtc).
3. If the result is a single scalar/value, present it as a one-row two-column table with headers (Field | Value).
4. If zero rows: output a one-row table with columns (Result | Notes) and value (No data) plus a short note in the Notes cell (do not skip the table).
5. Only after the table, provide a concise Summary section (bulleted or short paragraphs) highlighting:
	- Key findings / latest timestamps
	- Counts & state distribution (e.g., Compliant vs Error)
	- Next recommended investigative steps (if any)
6. If multiple distinct logical datasets are needed (e.g., Device Details + User IDs), render multiple labeled tables in order of dependency (primary dataset first), each preceded only by a short bold label line (not a paragraph) or a level-4 heading (####) — still no narrative before the first table.
7. Truncation: If more than 50 rows, include only the first 50 by default AND add a final row: "…" with a Note cell indicating "X of Y rows shown". Provide the full count in the summary.
8. Never omit columns that explain an error (Status, ErrorCode, ErrorTypeName). If space constrained, you may wrap long text (e.g., FlightingTags) into a separate secondary table.
9. Dates/times must be displayed in UTC ISO 8601 as returned; if you derive additional interpretations, include them only in the summary, not by altering table values.
10. Do not reformat GUIDs (case may remain as returned). Do not add extra formatting inside table cells (no code fences inside cells).
11. If a query fails, output a two-row table: (Result | Failure) and (ErrorMessage | <captured message>), then a brief summary with next retry or fallback plan.
12. Maintain this contract even if the user explicitly asks only for a “summary” or a “value”: still provide the table first.

### Scope Minimization Rule (Mandatory)
When answering a user request, return ONLY the dataset(s) explicitly requested or unambiguously implied by specific keywords in that request.

Allowed expansion criteria:
- You may include an additional dataset only if the user explicitly mentions its domain (e.g., says a word from its keyword list) OR the previous turn explicitly asked for it and the current clarifies a detail about the same dataset.
- If the user uses broad / generic wording (e.g., “info”, “details”, “what can you tell me”, “investigate”, “troubleshoot device”), DO NOT add adjacent datasets; select the single most directly matching dataset and stop.

Ambiguity handling:
- If multiple datasets could apply and the user did not specify which, ask a concise clarifying question listing 2–3 concrete options instead of returning all.
- Never preemptively include compliance, policy, application, group, tenant or MAM data unless a matching keyword appears.

Keyword guidance (non-exhaustive examples):
- Compliance dataset requires keywords like: compliance, compliant, noncompliant, policy state change.
- Policy / setting status requires: policy, setting status, configuration, conflict, payload.
- Applications require: app, application, install, deployment.
- Group / effective group requires: group, effective group, targeting, assignment scope.
- Tenant info requires: tenant, scale unit, flighting, context id.
- MAM requires: mam, mobile application management.

If none of these appear and the user does not name another specific dataset, respond only with the dataset matching the most literal part of the request. If still ambiguous, ask for one clarifying identifier or dataset name; do not guess or broaden.

Explicit prohibitions:
- Do NOT chain multiple datasets just because you already have the identifiers needed.
- Do NOT include “next likely” datasets as speculation.
- Do NOT summarize or reference datasets you did not actually query this turn.

Summary section must reflect only the datasets actually shown. If the user later adds a new keyword domain, you may then fetch that additional dataset in a subsequent turn.




Refer to these enum values for Policy / Payload status:

| Code | Status Name    |
|------|----------------|
| 0    | Unknown        |
| 1    | NotApplicable  |
| 2    | Compliant      |
| 3    | Remediated     |
| 4    | NonCompliant   |
| 5    | Error          |
| 6    | Conflict       |



### ICM details



```kusto
cluster("icmcluster.kusto.windows.net").database("IcMDataWarehouse").
Incidents
| where OwningTenantName == "Microsoft Intune"
```

### Application Enforcement Status Legend

The following legend augments application status outputs:

| EnforcementStatus | Meaning  |
|-------------------|----------|
| 1                 | Installed |
| 2                 | Failed |
| 3                 | NotInstalled |



### Device Details

Capture the device details for the provided `<DeviceId>` and summarize key fields (DeviceId, AccountId, PrimaryUser/EnrolledByUser, OSVersion, LastContact, SerialNumber, DeviceName, AzureAdDeviceId). 


```kusto
// US region fallback
cluster("qrybkradxus01pe.westus2.kusto.windows.net").database("qrybkradxglobaldb").Device_Snapshot()
| where DeviceId == "<DeviceId>"
```

```kusto
// EU region fallback
cluster("qrybkradxeu01pe.northeurope.kusto.windows.net").database("qrybkradxglobaldb").Device_Snapshot()
| where DeviceId == "<DeviceId>"
```

### Enrollment Type Legend

| EnrollmentType | DeviceEnrollmentType | Meaning (Typical) | Notes |
|----------------|----------------------|-------------------|-------|
| 0 | 0 | Unknown / Default | Placeholder or not yet classified |
| 1 | 1 | MDM (User) | Standard user-driven MDM enrollment (Android/iOS) |
| 3 | 3 | MDM (macOS) | macOS direct MDM (low volume in sample) |
| 4 | 5 | Windows AAD MDM | Windows user-based (mapped variant) |
| 10 | 9 | Windows Autopilot / AAD Join | Includes provisioning / pre-provisioning scenarios |
| 19 | 3 | macOS (Alt Path) | macOS with alternate enrollment code path |
| 21 | 16 | Android Enterprise (Work Profile / Fully Managed) | AE deployment types (work profile / fully managed) |
| 26 | 20 | iOS/iPadOS Automated Device Enrollment (ADE) | Formerly DEP / supervised |


### User ID Lookup
Extract the userId(s) associated with the device (may return primary plus all-zero GUID). Use the central Intune telemetry table:

```kusto
cluster("intune.kusto.windows.net").database("intune").IntuneEvent
| where DeviceId == "<DeviceId>"
| project UserId
```

If multiple values are returned, prefer the non-all-zero GUID as the primary user association.


### Tenant Information

Fetch the tenant info using the AccountId obtained in Step 1. Summarize the output as a table.

 ContextId, flighting tags, Tenant name and ScaleUnit
```kusto
cluster("intune.kusto.windows.net").database("intune").WindowsAutopilot_GetTenantInformationFromEitherAccountIdContextIdOrName("<Fetch the accountId from Device Details and replace here>")
```

### Compliance (Last 10 Days)

Check the compliance state changes for the device over the last 10 days and show the output as a table.


```kusto
cluster("intune.kusto.windows.net").database("intune").DeviceComplianceStatusChangesByDeviceId('<DeviceId>', ago(10d), now(), 1000)
```

### Policy / Setting Status and Assignments

Using the ContextId from Device Details, run the following queries and show the output (tables):

Policy setting status per device:


```kusto
// PolicySettingsStatus
GetAllPolicySettingsStatusForTenant(@'<ContextId from Step 2>')
| where DeviceId == "<DeviceId>"
```

// Overall policy status per device:


```kusto
GetAllPolicyStatusForTenant('<ContextId from Step 2>')
| where DeviceId == "<DeviceId>"
```

After checking the above 2 Kusto queries, check the below Kusto query to give more information about the PolicyId.

```kusto
IntuneEvent
| where DeviceId == "<DeviceId>"
| where * contains "<PolicyId or PayloadId>"
```

// Policy Assignments for Tenant (Settings Catalog, ASR, Device Configuration Policies) to Track Policy Deployment
GetAllPolicyAssignmentsForTenant('<TenantId>')

-------------------------------


### Effective Group Troubleshooting

**Effective Group Troubleshooting Table**

| Step | Action | Query/Details |
|------|--------|---------------|
| 1    | Find Effective Group Id (EGID) for the device | See query below; use `<DeviceId>` and `<AccountId from Step 1>` |
| 2    | List groups within the Effective Group | Use `<EffectiveGroupId>` from Step 1 |
| 3    | Identify policies assigned to the group | Use `<PayloadId>`, `<AccountId from Step 1>`, and `<GroupId>` |
| 4    | Review policy assignments for the tenant | Use `<TenantId>` and `<PolicyId or PayloadId>` |

**Queries:**

```kusto
// Step 1: Find the Effective Group Id (EGID) containing the device
union 
	cluster("qrybkradxus01pe.westus2.kusto.windows.net").database("qrybkradxglobaldb").EffectiveGroupMembershipV2_Snapshot(),
	cluster("qrybkradxeu01pe.northeurope.kusto.windows.net").database("qrybkradxglobaldb").EffectiveGroupMembershipV2_Snapshot()
| where AccountId == "<AccountId from Step 1>"
| where TargetId == "<DeviceId>" // or replace with a UserId to inspect user-scoped targeting
```

```kusto
// Step 2: Groups within a specific Effective Group (EU primary, US fallback)
// Primary (EU)
cluster('qrybkradxeu01pe.northeurope.kusto.windows.net').database('qrybkradxglobaldb').EffectiveGroup_Snapshot()
| where EffectiveGroupId == "<EffectiveGroupId>"
| project GroupsAsString

// Fallback (US) – run only if EU query errors or returns zero rows
cluster('qrybkradxus01pe.westus2.kusto.windows.net').database('qrybkradxglobaldb').EffectiveGroup_Snapshot()
| where EffectiveGroupId == "<EffectiveGroupId>"
| project GroupsAsString
```

```kusto
// Step 3: Policies assigned to a group (EU first, fallback to US)
// Primary (EU)
cluster('qrybkradxeu01pe.northeurope.kusto.windows.net').database('qrybkradxglobaldb').Deployment_Snapshot()
| where PayloadId == "<PayloadId>"
| where AccountId == "<AccountId from Step 1>"
| where GroupId in ("<GroupId>")
| distinct GroupId

// Fallback (US) – run only if EU query errors or returns zero rows
cluster('qrybkradxus01pe.westus2.kusto.windows.net').database('qrybkradxglobaldb').Deployment_Snapshot()
| where PayloadId == "<PayloadId>"
| where AccountId == "<AccountId from Step 1>"
| where GroupId in ("<GroupId>")
| distinct GroupId
```

```kusto
// Step 4: Policy assignments for the tenant
GetAllPolicyAssignmentsForTenant('<TenantId>')
| where PolicyId == "<PolicyId or PayloadId>"
```

### EffectiveGroup Memberships

Use these optional queries to trace effective group membership and related policy assignments. Replace placeholders before running.


```kusto
// Find the Effective Group Id (EGID) containing the device
union 
	cluster("qrybkradxus01pe.westus2.kusto.windows.net").database("qrybkradxglobaldb").EffectiveGroupMembershipV2_Snapshot(),
	cluster("qrybkradxeu01pe.northeurope.kusto.windows.net").database("qrybkradxglobaldb").EffectiveGroupMembershipV2_Snapshot()
| where AccountId == "<AccountId from Step 1>"
| where TargetId == "<DeviceId>"

// Groups within a specific Effective Group (EU primary, US fallback)
// Primary (EU)
cluster('qrybkradxeu01pe.northeurope.kusto.windows.net').database('qrybkradxglobaldb').EffectiveGroup_Snapshot()
| where EffectiveGroupId == "<EffectiveGroupId>"
| project GroupsAsString

// Fallback (US) – run only if EU query errors or returns zero rows
cluster('qrybkradxus01pe.westus2.kusto.windows.net').database('qrybkradxglobaldb').EffectiveGroup_Snapshot()
| where EffectiveGroupId == "<EffectiveGroupId>"
| project GroupsAsString

// Policies assigned to a group (supply relevant IDs) – EU first, fallback to US
// Primary (EU)
cluster('qrybkradxeu01pe.northeurope.kusto.windows.net').database('qrybkradxglobaldb').Deployment_Snapshot()
| where PayloadId == "<PayloadId>"
| where AccountId == "<AccountId from Step 1>"
| where GroupId in ("<GroupId>")
| distinct GroupId

// Fallback (US) – run only if EU query errors or returns zero rows
cluster('qrybkradxus01pe.westus2.kusto.windows.net').database('qrybkradxglobaldb').Deployment_Snapshot()
| where PayloadId == "<PayloadId>"
| where AccountId == "<AccountId from Step 1>"
| where GroupId in ("<GroupId>")
| distinct GroupId

// Policy assignments for the tenant
GetAllPolicyAssignmentsForTenant('<TenantId>')
| where PolicyId == "<PolicyId or PayloadId>"
```

---

Placeholders:
- `<DeviceId>` = Provided DeviceId for investigation
- `<AccountId from Step 1>` = AccountId returned in Step 1
- `<ContextId from Step 2>` = ContextId returned in Step 2
- `<EffectiveGroupId>` = Effective group identifier discovered above
- `<PayloadId>` = Policy / payload identifier of interest
- `<GroupId>` = Azure AD / Intune group Id
- `<TenantId>` = Tenant Id (often same as AccountId but confirm)
- `<PolicyId or PayloadId>` = Specific policy/payload to filter

### Multi-Value Column Expansion Pattern (Readable Tables)


Kusto pattern to expand `GroupsAsString`:

```kusto
// Raw (primary) table — use as-is for the first output table
let RawEG = EffectiveGroup_Snapshot()
	| where EffectiveGroupId == '<EffectiveGroupId>'
	| project EffectiveGroupId, GroupsAsString;
RawEG;

// Expanded (secondary) table — one row per GroupId
RawEG
| extend GroupArray = split(GroupsAsString, ',')
| mv-expand GroupArray
| project EffectiveGroupId, GroupId = trim(' ', GroupArray)
```

If multiple multi-value columns exist, repeat the expansion for each (producing additional labeled tables) rather than overloading a single wide table.


### MAM Policy 

// To check all the MAM Policy deployed to the device.
```Kusto
cluster("intune.kusto.windows.net").database("intune").
GetAllMAMPolicyStatusForTenant("ContextId")
| where DeviceId == "DeviceId"
```

### Applications

//Get all the application status for the tenant
```kusto
GetAllAppStatusForTenant('ce6f9430-1d64-4a97-a32d-e92a05a11971')
| where DeviceId == "DeviceId"
```

// Get all the application details for the tenant
```kusto
GetAllApplicationsForTenant(@'b749cbc5-432b-40f6-a389-ed007659d2d0')
```

// Application install attemps by device Id
```kusto
ApplicationInstallAttemptsByDeviceId("790ed67d-8983-4603-90c0-725452a273ee", datetime(2025-08-05 05:42:00),datetime(2025-08-13 05:42:00),1000)
```


// More application deployment details with message.
```Kusto
DeviceManagementProvider
|where env_time >= ago(30d)
|where ActivityId == "deviceId" 
```


### Third Party Integration(JAMF)

cluster("https://qrybkradxus01pe.westus2.kusto.windows.net").database("qrybkradxglobaldb").MTPartnerTenantService_Snapshot
|where AccountId == "<Intune Account Id>"

### Identify conflicting DCv1 and DCv2 policies

Use this query to identify conflicting DCv1 and DCv2 policies. Replace the placeholder with the deviceId the user is interested in.

```Kusto
let DeviceID = '<deviceId>';
let base_query = (cluster: string, source: string) {
    let Device_Snapshot = cluster(cluster).database('qrybkradxglobaldb').Device_Snapshot;
    let AccountID = toscalar(Device_Snapshot | where DeviceId == DeviceID | project AccountId);
    let ASU = toscalar(Device_Snapshot | where DeviceId == DeviceID | project ScaleUnitName);
    let PolicySettingMap = materialize(cluster(cluster).database('qrybkradxglobaldb').PolicySettingMapV3_Snapshot | where AccountId == AccountID);
    let SettingsLevelData = 
        cluster(cluster).database('qrybkradxglobaldb').IntentSettingStatusPerDevicePerUserV2_Snapshot
        | where ScaleUnitName == ASU and AccountId == AccountID and DeviceId == DeviceID
        | extend Source="IntentSettingStatus", LastModifiedTimeUtc=IntentSettingStatusPerDevicePerUserLastUpdateTimeUTC
        | union (
            cluster(cluster).database('qrybkradxglobaldb').SettingStatusPerDevicePerUserV1_Snapshot
            | where ScaleUnitName == ASU and AccountId == AccountID and DeviceId == DeviceID
            | join kind=leftouter PolicySettingMap on $left.SettingId == $right.SettingId
            | extend Source="SettingStatusV1", LastModifiedTimeUtc=SspdpuLastModifiedTimeUtc)
        | union (
            cluster(cluster).database('qrybkradxglobaldb').SettingStatusPerDevicePerUserV3_Snapshot
            | where ScaleUnitName == ASU and AccountId == AccountID and DeviceId == DeviceID
            | extend Source="SettingStatusV3", LastModifiedTimeUtc=SspdpuLastModifiedTimeUtc)
        | union (
            cluster(cluster).database('qrybkradxglobaldb').AdmxPolicySettingStatusPerDevicePerUserV1_Snapshot
            | where ScaleUnitName == ASU and AccountId == AccountID and DeviceId == DeviceID
            | extend Source="AdmxSettingStatus", LastModifiedTimeUtc=LastModifiedTimeUtc)
        | project DeviceId, UserId, PolicyId, SettingName, SettingInstancePath,
                 Status = case(SettingStatus == 0, "Unknown", SettingStatus == 1, "NotApplicable", SettingStatus == 2, "Compliant", SettingStatus == 3, "Remediated", SettingStatus == 4, "NotCompliant", SettingStatus == 5, "Error", SettingStatus == 6, "Conflict", ""),
                 ErrorTypeName = case(ErrorType == 0, "None", ErrorType == 1, "DeviceCheckinDiscovery", ErrorType == 2, "DeviceCheckinRemediation", ErrorType == 3, "DeviceCheckinCompliance", ErrorType == 4, "DeviceCheckinProcessing", ErrorType == 5, "DeviceCheckinConflict", ErrorType == 6, "DeviceCheckinConflictResolution", ErrorType == 7, "PolicyReportProcessing", ErrorType == 32, "GroupPolicy", ErrorType == 64, "DFCI", "Other"),
                 ErrorCode, LastModifiedTimeUtc, PolicyVersion, SettingId, SettingInstanceId, Source
        | distinct DeviceId, UserId, PolicyId, SettingName, SettingInstancePath, Status, ErrorTypeName, ErrorCode, LastModifiedTimeUtc, PolicyVersion, SettingId, SettingInstanceId, Source;
    let PolicyMetadata = 
        cluster(cluster).database('qrybkradxglobaldb').CombinedPolicyMetadataWithScopeTags_Snapshot
        | where ScaleUnitName == ASU and AccountId == AccountID
        | extend Source="PolicyMetadata"
        | union (
            cluster(cluster).database('qrybkradxglobaldb').DeviceIntentMetadataV2_Snapshot
            | where ScaleUnitName == ASU and AccountId == AccountID
            | extend Source="IntentMetadata")
        | union (
            cluster(cluster).database('qrybkradxglobaldb').PolicyMetadataV1_Snapshot
            | where ScaleUnitName == ASU and AccountId == AccountID
            | extend Source="PolicyMetadataV1")
        | project PolicyId, PolicyName, PolicyBaseTypeName;
    let PayloadTypeMap = cluster(cluster).database('qrybkradxglobaldb').DeploymentStatus_Snapshot
        | where AccountId == AccountID
        | distinct PayloadId, PayloadType;    SettingsLevelData
    | join kind=leftouter PayloadTypeMap on $left.PolicyId == $right.PayloadId
    | join kind=leftouter PolicyMetadata on PolicyId
    | extend PayloadTypeDescription = case(PayloadType == 1, "DCv1", PayloadType == 29, "DCv2", strcat("PayloadType_", tostring(PayloadType))), HasSettingDetails = true
    | where PayloadType in (1, 29) and Status == "Conflict"
    | as ConflictData    | join kind=leftouter (
        ConflictData 
        | where PayloadTypeDescription == "DCv1"
        | extend 
            HasKeyPattern = SettingInstancePath contains "Key='",
            ExtractedPath = case(
                SettingInstancePath contains "Key='",
                tostring(split(SettingInstancePath, "Key='")[1]),
                SettingInstancePath
            )
        | extend 
            CleanPath = case(
                HasKeyPattern,
                tostring(split(ExtractedPath, "'")[0]),
                ExtractedPath
            )
        | extend DCv1_SettingName = tostring(split(CleanPath, "/")[-1])
        | project DeviceId, UserId, DCv1_PolicyId = PolicyId, DCv1_PolicyName = PolicyName, DCv1_SettingName, DCv1_SettingInstancePath = SettingInstancePath
    ) on DeviceId, UserId, $left.SettingName == $right.DCv1_SettingName
    | project AccountID, DeviceId, UserId, PolicyId, PolicyName, PolicyBaseTypeName, PayloadType, PayloadTypeDescription, SettingName,
             ConflictingDCv1_PolicyId = case(PayloadTypeDescription == "DCv2", DCv1_PolicyId, ""),
             ConflictingDCv1_PolicyName = case(PayloadTypeDescription == "DCv2", DCv1_PolicyName, ""),
             ConflictingDCv1_SettingPath = case(PayloadTypeDescription == "DCv2", DCv1_SettingInstancePath, ""),
             SettingInstancePath, Status, ErrorTypeName, ErrorCode, LastModifiedTimeUtc, PolicyVersion, SettingId, SettingInstanceId, Source, HasSettingDetails
    | where ConflictingDCv1_PolicyId != ""
    | distinct *
    | order by PolicyId, HasSettingDetails desc, SettingName
};
union
   base_query('qrybkradxeu01pe.northeurope', 'europe'),  
   base_query('qrybkradxus01pe.westus2', 'Non-EU')
```