# Parallel Query Execution Optimization

**Date**: October 14, 2025  
**Purpose**: Dramatically improve Device Timeline performance by executing independent queries in parallel

## Problem

The Device Timeline scenario was taking significantly longer than the previous Autogen setup because all 8 queries were executing **sequentially**. This meant each query had to wait for the previous one to complete, even if there were no dependencies between them.

**Original Sequential Execution Time**: ~60-90 seconds (8 queries × 7-11 seconds each)

## Solution

Implemented **parallel execution for independent queries** by organizing the Device Timeline workflow into dependency-based batches.

### Query Dependency Analysis

```
Step 1: Device Baseline (DeviceId, AccountId, TenantId)
    ├─→ Step 2: Compliance Status (needs DeviceId)
    ├─→ Step 3: Group Membership (needs DeviceId)
    │       └─→ Step 4: Group Definitions (needs EffectiveGroupId from Step 3)
    │               └─→ Step 5: Deployments (needs GroupId from Step 4)
    ├─→ Step 6: Application Installs (needs DeviceId)
    ├─→ Step 7: Check-in Activity (needs DeviceId)
    └─→ Step 8: Policy Assignments (optional, needs TenantId)
```

### Batch Execution Strategy

**BATCH 1** (must run first):
- Step 1: Device Baseline → Extract DeviceId, AccountId, TenantId

**BATCH 2** (run these 4 queries IN PARALLEL):
- Step 2: Compliance Status
- Step 3: Group Membership
- Step 6: Application Installs
- Step 7: Check-in Activity

**BATCH 3** (run after Batch 2 completes):
- Step 4: Group Definitions (needs EffectiveGroupId from Step 3)

**BATCH 4** (run after Batch 3 completes):
- Step 5: Deployments (needs GroupId from Step 4)

**BATCH 5** (optional, can run after Batch 1):
- Step 8: Policy Assignments (needs TenantId from Step 1)

### Performance Impact

**New Parallel Execution Time**: ~20-30 seconds

- **Batch 1**: 1 query × 8s = 8s
- **Batch 2**: 4 queries in parallel × 8s = 8s (not 32s!)
- **Batch 3**: 1 query × 8s = 8s
- **Batch 4**: 1 query × 8s = 8s
- **Total**: ~32s (vs 64s sequential)

**Performance Improvement**: ~50-65% faster

## Implementation Changes

### 1. Updated Device Timeline Instructions

**File**: `backend/services/agent_framework_service.py` (lines ~1089-1126)

The `device_timeline` query type now includes explicit batch execution instructions:

```python
timeline_instructions = (
    "Build a comprehensive chronological device event timeline for Intune diagnostics.\n\n"
    "WORKFLOW:\n"
    "1. Call search_scenarios with 'device timeline' to find the scenario\n"
    "2. Call get_scenario with 'device-timeline' to get all 8 query steps\n"
    "3. Execute queries in PARALLEL BATCHES to optimize performance:\n\n"
    "   **BATCH 1** (run first):\n"
    "   - Step 1: Device Baseline → Extract DeviceId, AccountId, TenantId\n\n"
    "   **BATCH 2** (run these 4 queries IN PARALLEL after Batch 1):\n"
    "   - Step 2: Compliance Status (needs DeviceId from Step 1)\n"
    "   - Step 3: Group Membership (needs DeviceId from Step 1)\n"
    "   - Step 6: Application Installs (needs DeviceId from Step 1)\n"
    "   - Step 7: Check-in Activity (needs DeviceId from Step 1)\n\n"
    "   **BATCH 3** (run after Batch 2 completes):\n"
    "   - Step 4: Group Definitions (needs EffectiveGroupId from Step 3)\n\n"
    "   **BATCH 4** (run after Batch 3 completes):\n"
    "   - Step 5: Deployments (needs GroupId from Step 4)\n\n"
    "   **BATCH 5** (optional, run after Batch 1):\n"
    "   - Step 8: Policy Assignments (needs TenantId from Step 1 and PolicyId from earlier results)\n\n"
    # ... rest of instructions
)
```

### 2. Updated General Agent Instructions

**File**: `backend/services/agent_framework_service.py` (lines ~670-693)

Added parallel execution guidance to the main agent workflow:

```python
"4. **PARALLEL EXECUTION OPTIMIZATION**:\n"
"   - If multiple queries depend ONLY on the same previous query results (no dependencies on each other),\n"
"     you can execute them IN PARALLEL to improve performance\n"
"   - Example: Device Timeline Steps 2,3,6,7 all only need DeviceId from Step 1 → run in parallel\n"
"   - Wait for all parallel queries to complete before proceeding to dependent queries\n"
```

### 3. Updated Task Completion Criteria

The completion criteria now references the batch structure to help the agent track progress:

```python
"TASK COMPLETION CRITERIA:\n"
"The Device Timeline task is COMPLETE when ALL of the following are satisfied:\n"
"1. All 8 Device Timeline queries have been executed successfully (or attempted if errors occur)\n"
"   - Batch 1: Step 1 completed\n"
"   - Batch 2: Steps 2, 3, 6, 7 completed (these ran in parallel)\n"
"   - Batch 3: Step 4 completed\n"
"   - Batch 4: Step 5 completed\n"
"   - Batch 5: Step 8 completed if applicable\n"
```

## How the Agent Executes Parallel Queries

The Azure Agent Framework (Magentic orchestration) supports parallel tool calls natively. When the agent receives instructions to execute multiple queries "in parallel", it will:

1. **Identify independent queries**: Steps 2, 3, 6, 7 all only need DeviceId
2. **Call tools concurrently**: The framework allows multiple `execute_query` calls simultaneously
3. **Wait for all to complete**: Before proceeding to Batch 3 (Step 4)
4. **Extract results**: Parse EffectiveGroupId from Step 3 for use in Step 4

## Testing

To verify parallel execution is working:

1. **Run Device Timeline**: Execute a device timeline query with a real DeviceId
2. **Check logs**: Look for multiple `[Magentic]` events with `execute_query` occurring close together in time
3. **Measure duration**: Compare total execution time (should be ~30s instead of ~60s)
4. **Verify results**: Ensure all 8 queries still execute and return correct data

## Future Optimizations

### Potential Additional Scenarios

Other multi-query scenarios could benefit from parallel execution:

1. **User Investigation**: User account queries + mailbox queries (independent)
2. **Tenant Overview**: Compliance counts + device counts + policy counts (independent)
3. **Policy Analysis**: Policy details + assignments + compliance (some parallel, some sequential)

### Dynamic Batch Detection

Could enhance the MCP server to automatically analyze dependencies and suggest batches:

```python
# Future enhancement in get_scenario tool
{
  "status": "success",
  "steps": [...],
  "execution_batches": [
    {"batch": 1, "steps": [1]},
    {"batch": 2, "steps": [2, 3, 6, 7], "parallel": true},
    {"batch": 3, "steps": [4]},
    {"batch": 4, "steps": [5]}
  ]
}
```

## Rollback Instructions

If parallel execution causes issues, revert to sequential by:

1. Remove "PARALLEL BATCHES" section from timeline_instructions
2. Change back to: "3. For each of the 8 steps in sequence:"
3. Update completion criteria to remove batch references

## Related Documents

- [Agent Framework Migration](./AGENT_FRAMEWORK_MIGRATION.md)
- [MCP Server Implementation](./README.md)
- [Performance Testing](./TESTING_CHECKLIST.md)
