# F-String Error Fix (Round 2)

## Problem
After applying all the agent looping fixes, the app crashed on startup with:
```
[ERROR] Failed to setup Agent Framework: Invalid format specifier ' "abc-123", "StartTime": "2025-10-07", ...' for object of type 'str'
```

## Root Cause
In the agent instructions (which are defined as an f-string), there was example code showing a dictionary literal:

```python
system_instructions = f"""
    ...
    Step 3: For EACH step, substitute placeholders and execute
        substitute_and_get_query(
            query_id="device-timeline_step1",
            placeholder_values={"DeviceId": "abc-123", "StartTime": "2025-10-07", ...}
        )
    ...
"""
```

The problem: When Python parses an f-string, it looks for `{` and `}` as format placeholders. The dictionary literal `{"DeviceId": "abc-123", ...}` inside the f-string caused Python to interpret:
- `{` = start of format placeholder
- `"DeviceId": "abc-123", "StartTime": "2025-10-07", ...` = format specifier
- Python tried to use this as a format specification, which is invalid

## Solution
Changed the example code from Python literal syntax to plain text description:

**Before (causes f-string error)**:
```python
Step 3: For EACH step, substitute placeholders and execute
    substitute_and_get_query(
        query_id="device-timeline_step1",
        placeholder_values={"DeviceId": "abc-123", "StartTime": "2025-10-07", ...}
    )
```

**After (safe f-string)**:
```python
Step 3: For EACH step, substitute placeholders and execute
    Call substitute_and_get_query with:
    - query_id: The step's query identifier
    - placeholder_values: Dictionary with DeviceId, StartTime, EndTime, etc.
```

## Alternative Solutions Considered
1. **Escape braces**: Use `{{` and `}}` to escape the dictionary literal
   - Rejected: Still fragile, hard to maintain
   
2. **Use raw string**: Change from f-string to regular string
   - Rejected: Need f-string for `{self.scenario_service.get_scenario_summary()}`

3. **Plain text description** ✅ CHOSEN
   - Clearer for LLM to understand
   - No f-string parsing issues
   - More maintainable

## Files Changed
- `backend/services/agent_framework_service.py` (line ~723-741)

## Verification
```powershell
# Test import succeeds
uv run python -c "from services.agent_framework_service import AgentFrameworkService; service = AgentFrameworkService(); print('✅ Success')"
```

Expected output: `✅ F-string fix verified - service imports successfully`

## Related Issues
This is the **second time** we've encountered this f-string error:
1. **First occurrence**: Lines 720-744 (fixed in AGENT_FRAMEWORK_MIGRATION.md)
2. **Second occurrence**: Same section after updating workflow instructions

## Prevention
When editing agent instructions:
- ⚠️ **DO NOT** include dictionary literals like `{"key": "value"}` in example code
- ⚠️ **DO NOT** use `...` (ellipsis) inside braces in f-strings
- ✅ **DO** use plain text descriptions: "Dictionary with key, value, etc."
- ✅ **DO** test imports after every change: `uv run python -c "from services.agent_framework_service import ..."`

## Date
October 14, 2025
