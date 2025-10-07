# ChatMessage Rendering Fix - Final Solution

## Problem
The GUI was displaying `<agent_framework._types.ChatMessage object at 0x...>` instead of the actual text content from diagnostic queries.

## Root Cause
Based on the [Agent Framework source code](https://github.com/microsoft/agent-framework/tree/7ebe00ec3d9459a539ed73e2a8bfb9f33663ce0b/python/packages/core/agent_framework/_types.py#L2041-L2049), `ChatMessage` objects have a `.text` property that returns the concatenated text from all `TextContent` objects in the message's `contents` list.

Previous attempts to access `.content` or nested `.content.content` were incorrect because:
1. `ChatMessage` does NOT have a `.content` attribute
2. `ChatMessage` HAS a `.text` property that does the extraction automatically

## Correct Implementation

### From Agent Framework Source (Line 2041-2049):
```python
@property
def text(self) -> str:
    """Returns the text content of the message.

    Remarks:
        This property concatenates the text of all TextContent objects in Contents.
    """
    return " ".join(content.text for content in self.contents if isinstance(content, TextContent))
```

### Fixed Code in agent_service.py

**Line 806-813** (`query_diagnostics` method):
```python
last_message = team_result.messages[-1]
# Extract text from ChatMessage using the .text property
# ChatMessage.text concatenates all TextContent objects in the message
response_content = ""
if hasattr(last_message, 'text'):
    text_val = getattr(last_message, 'text', '')
    response_content = str(text_val) if text_val else ""
else:
    response_content = str(last_message) if last_message else ""
```

**Line 820** (mermaid extraction loop):
```python
txt = getattr(m, 'text', '') or ''
```

**Line 958-965** (`chat` method):
```python
last_message = team_result.messages[-1]
# Extract text from ChatMessage using the .text property
# ChatMessage.text concatenates all TextContent objects in the message
response_content = ""
if hasattr(last_message, 'text'):
    text_val = getattr(last_message, 'text', '')
    response_content = str(text_val) if text_val else ""
else:
    response_content = str(last_message) if last_message else ""
```

**Line 969** (JSON extraction loop):
```python
msg_text = getattr(m, 'text', '') or ''
```

## Changes Made
1. **agent_service.py** (4 locations):
   - Line 806-813: Extract text from final message in `query_diagnostics()`
   - Line 820: Extract text from messages in mermaid timeline search
   - Line 958-965: Extract text from final message in `chat()`
   - Line 969: Extract text from messages in JSON table extraction

## Why This Works
- `ChatMessage.text` is a **property** that automatically extracts and concatenates all text content
- Using `getattr(last_message, 'text', '')` safely accesses the property with fallback
- Type checker is satisfied because we check `hasattr()` first and use `getattr()` with default

## Testing
1. Restart backend server
2. Run any diagnostic query from Advanced Scenarios
3. Verify "AI Insight Summary" shows actual text instead of `<ChatMessage object at 0x...>`
4. Verify table data displays correctly

## References
- [Agent Framework ChatMessage Source](https://github.com/microsoft/agent-framework/tree/main/python/packages/core/agent_framework/_types.py#L2041-L2049)
- [ChatMessage Examples](https://github.com/microsoft/agent-framework/tree/main/python/packages/core/tests/core/test_types.py#L467-L481)
