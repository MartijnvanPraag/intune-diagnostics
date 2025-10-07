# Agent Framework Table Extraction Fix

## Issue
Tables were not being extracted in the Agent Framework service (`agent_framework_service.py`), even though the text response was rendering correctly. The GUI showed "No table data available" despite the agent executing Kusto queries successfully.

## Root Cause
The Agent Framework service was only extracting tables from `FunctionResultContent` objects in events, but was **not** comprehensively collecting all message content like the Autogen service does.

**Autogen approach** (working):
```python
# Iterate through ALL messages in team_result.messages
for m in team_result.messages:
    msg_text = getattr(m, 'content', '') or ''
    if not isinstance(msg_text, str):
        continue
    objs = self._extract_json_objects(msg_text)
    extracted_objs.extend(objs)
```

**Agent Framework approach** (broken):
```python
# Only extracted from FunctionResultContent, missed other message types
if isinstance(content, FunctionResultContent):
    # Only handled this specific content type
```

## Solution
Updated both `query_diagnostics()` and `chat()` methods to:
1. **Collect ALL event message content** during streaming
2. **Store message text** in a list for later extraction
3. **Extract JSON objects** from all collected messages
4. **Handle both** direct dict results AND string results that need parsing

### Changes Made

#### In `query_diagnostics()` method (Lines ~970-1025):

**Before:**
- Only looked at `FunctionResultContent` in event messages
- Fell back to extracting from final `response_content` if no results found
- Missed intermediate tool call results

**After:**
```python
all_event_messages: list[str] = []  # Collect all message content

async for event in self.magentic_workflow.run_stream(query_message):
    # ... existing event processing ...
    
    # Collect ALL message content for comprehensive table extraction
    if hasattr(event, 'message'):
        event_message = getattr(event, 'message', None)
        if event_message:
            # Collect message text content
            if hasattr(event_message, 'content') and event_message.content:
                msg_text = str(event_message.content)
                if msg_text and msg_text not in all_event_messages:
                    all_event_messages.append(msg_text)
            
            # Also check for FunctionResultContent (tool outputs)
            if hasattr(event_message, 'contents'):
                for content in event_message.contents:
                    if isinstance(content, FunctionResultContent):
                        if hasattr(content, 'result') and content.result:
                            result_data = content.result
                            if isinstance(result_data, str):
                                # Store the raw string result for extraction
                                if result_data not in all_event_messages:
                                    all_event_messages.append(result_data)
                            elif isinstance(result_data, dict):
                                # Direct dict result
                                extracted_objs.append(result_data)

# Extract JSON objects from all collected message content
for msg_text in all_event_messages:
    if isinstance(msg_text, str):
        objs = self._extract_json_objects(msg_text)
        if objs:
            extracted_objs.extend(objs)
```

#### In `chat()` method (Lines ~1163-1222):
Applied identical fix to ensure chat messages also extract tables properly.

## Key Improvements

1. **Comprehensive Collection**: Now collects ALL message content from events, not just specific content types
2. **Deduplication**: Prevents duplicate messages from being processed multiple times
3. **Dual Extraction**: Handles both:
   - Direct dict results (added immediately)
   - String results containing JSON (extracted via `_extract_json_objects()`)
4. **Better Logging**: Added detailed logging to track collection and extraction
5. **Parity with Autogen**: Now matches the approach used in `autogen_service.py`

## Testing Checklist

After restarting the backend:

✅ **Test Advanced Scenario Query**:
- Query: Device details for device ID `a50be5c2-d482-40ab-af57-18bace67b0ec`
- Expected: AI Insight Summary shows text + Kusto Query Results table with device data
- Should NOT see: "No table data available"

✅ **Verify Logs**:
- Look for: `[Magentic] query_diagnostics: Collected X message(s) from events`
- Look for: `[Magentic] query_diagnostics: Total extracted objects: X`
- Should see non-zero message count and extracted objects

✅ **Compare with Autogen**:
- Run same query with Autogen framework (default)
- Run same query with Agent Framework (settings toggle)
- Both should return identical table data

## Files Modified
- `backend/services/agent_framework_service.py` (2 methods: `query_diagnostics` and `chat`)

## Expected Behavior
All diagnostic queries using Agent Framework should now:
1. Display AI insights as readable text ✅ (already working)
2. Show Kusto query results in table format ✅ (NOW FIXED)
3. Extract multiple tables if query returns multiple datasets ✅ (NOW FIXED)
4. Match the behavior of the Autogen implementation ✅ (NOW FIXED)
