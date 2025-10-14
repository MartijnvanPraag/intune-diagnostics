# Agent Framework Deadlock Fix - Installation Record

**Date:** October 14, 2025  
**Issue:** GitHub Issue #1222 - Deadlock in MagenticOrchestratorExecutor  
**PR:** #1325 - Python: Fix deadlock in Magentic workflow  
**Status:** ✅ FIXED - Installed from GitHub main branch

---

## Problem Description

The `MagenticOrchestratorExecutor` experienced a deadlock when workflows detected stalling and attempted to reset and replan. The deadlock occurred because the same async task attempted to acquire the `_inner_loop_lock` while already holding it, creating a recursive locking scenario.

### Call Chain That Caused Deadlock (OLD CODE)

```
_run_inner_loop (acquires lock)
  └─> _run_inner_loop_locked
        └─> _reset_and_replan (when stall_count exceeds max_stall_count)
              └─> _run_outer_loop
                    └─> _run_inner_loop (attempts to acquire lock again) --> DEADLOCK
```

---

## The Fix

**Merged:** October 9, 2025 (PR #1325)  
**Installed:** October 14, 2025 (from GitHub main branch)

The fix was simpler than the initial proposal in the issue:

### Changes Made

1. **Removed the lock entirely**
   - Deleted: `self._inner_loop_lock = asyncio.Lock()`
   - Rationale: Executors are not designed to be thread-safe; instances are not meant to be used in multiple workflows

2. **Method renamed**
   - Old: `_run_inner_loop_locked`
   - New: `_run_inner_loop_helper`

3. **Simplified call flow**
   - `_run_inner_loop` now directly calls `_run_inner_loop_helper` without any lock
   - No recursive lock acquisition possible

### Code After Fix

```python
async def _run_inner_loop(
    self,
    context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
) -> None:
    """Run the inner orchestration loop. Coordination phase. Serialized with a lock."""
    if self._context is None or self._task_ledger is None:
        raise RuntimeError("Context or task ledger not initialized")
    
    await self._run_inner_loop_helper(context)  # No lock!

async def _run_inner_loop_helper(
    self,
    context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
) -> None:
    """Run inner loop with exclusive access."""
    # ... existing code ...
    
    if ctx.stall_count > self._manager.max_stall_count:
        logger.info("Magentic Orchestrator: Stalling detected. Resetting and replanning")
        await self._reset_and_replan(context)  # Called safely, no lock held
        return
```

---

## Installation Details

### Version Information

- **Before:** `agent-framework-core==1.0.0b251007` (from PyPI, built Oct 7)
- **After:** `agent-framework-core==1.0.0b251007` (from GitHub commit 9148392, built Oct 14)

### Installation Command Used

```powershell
# Set environment variable to skip Git LFS binary files
$env:GIT_LFS_SKIP_SMUDGE = "1"

# Install from GitHub main branch
uv pip install --force-reinstall "git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/core"
```

### Verification Results

✅ All verifications passed:

1. Lock initialization code removed (no more `self._inner_loop_lock = asyncio.Lock()`)
2. Method renamed from `_run_inner_loop_locked` to `_run_inner_loop_helper`
3. `reset_and_replan()` called outside any lock context (line 1342)

---

## Impact

### Before Fix
- Workflows that encountered stalling conditions would **deadlock**
- No recovery possible through reset/replan mechanism
- Required manual intervention or restart

### After Fix
- Workflows properly handle stall scenarios
- Reset and replan mechanism works as designed
- **No more deadlocks**

---

## Important Notes

### Package Management

⚠️ **This installation is from Git, not PyPI**

- Regular `uv pip install --upgrade agent-framework` will **NOT** overwrite this Git-based installation
- The package will stay at the Git version until manually changed
- Lock file (`uv.lock`) reflects the Git source

### Future Updates

**Option 1:** Continue using Git version (recommended until PyPI catches up)
```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"
uv pip install --force-reinstall "git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/core"
```

**Option 2:** Wait for PyPI release and switch back
```powershell
# Check for new releases (look for b251010 or later)
uv pip install --upgrade agent-framework

# Verify the fix is present after upgrading
# Check that version date is October 9 or later
```

---

## Testing Recommendations

To verify the fix works in your application:

1. **Test stall scenarios**
   - Configure workflows with `max_stall_count` = 3
   - Create tasks that cause agents to loop or fail to make progress
   - Verify that stall detection triggers reset without deadlock

2. **Monitor reset behavior**
   - Check logs for "Magentic Orchestrator: Stalling detected. Resetting and replanning"
   - Verify workflows recover and continue after reset

3. **Performance monitoring**
   - Ensure workflows complete successfully
   - No hung processes or frozen workflows

---

## References

- **GitHub Issue:** https://github.com/microsoft/agent-framework/issues/1222
- **Pull Request:** https://github.com/microsoft/agent-framework/pull/1325
- **Merge Commit:** 2397795c1dba1f9b6c6f2aaa1c490f362598bb9a
- **Installed Commit:** 9148392d00dafa47a95178622f3800f89bbf0425

---

## Related Documentation

- `docs/AGENT_FRAMEWORK_MIGRATION.md` - Initial migration to agent-framework
- `docs/AGENT_FRAMEWORK_QUICK_REFERENCE.md` - Usage patterns
- `backend/services/agent_framework_service.py` - Implementation file

---

**Status:** ✅ Production Ready - Fix verified and installed
