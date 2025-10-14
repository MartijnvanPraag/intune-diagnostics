# Package Persistence Fix - Agent Framework Deadlock

## Problem: Git-Based Installation Was Lost

**Date:** October 14, 2025  
**Issue:** Deadlock returned after being "fixed" - app hung after "entering inner loop"

### Root Cause

The agent-framework deadlock fix from GitHub was **overwritten by PyPI version**:

1. **Initial fix (October 9)**: Manually installed `agent-framework-core` from GitHub main branch (commit 9148392)
   - Fix verified: Lock removed, method renamed
   - App tested successfully

2. **Problem occurred (October 14)**: Deadlock returned
   - Investigation showed: `agent-framework-core` version `1.0.0b251001` (October 1, from PyPI)
   - Expected: GitHub version with commit 9148392 (October 9+)

3. **Why it happened**: 
   - `pyproject.toml` specified: `"agent-framework>=0.1.0"`
   - This tells `uv` to install from PyPI, not GitHub
   - When `uv sync` or `uv lock` runs, it reinstalls from PyPI
   - Git-based `pip install` is **temporary** unless specified in `pyproject.toml`

### Evidence

**Before Fix:**
```bash
PS> uv pip list | Select-String "agent-framework"
agent-framework                          1.0.0b251007
agent-framework-core                     1.0.0b251001  # ❌ PyPI version (Oct 1)
```

**uv.lock showed:**
```toml
[[package]]
name = "agent-framework-core"
version = "1.0.0b251001"
source = { registry = "https://pypi.org/simple" }  # ❌ PyPI source
```

**Deadlock behavior:**
```
[INFO] agent_framework._workflows._magentic: Magentic Orchestrator: Resetting and replanning
[INFO] agent_framework._workflows._magentic: Magentic Orchestrator: Outer loop - entering inner loop
# ❌ Hangs here forever
```

## Solution: Permanent Git-Based Installation

### 1. Update pyproject.toml

**Changed from:**
```toml
dependencies = [
    "agent-framework>=0.1.0",
]
```

**Changed to:**
```toml
dependencies = [
    "agent-framework>=0.1.0",
    "agent-framework-core @ git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/core",
]
```

**Why this works:**
- `uv` respects `pyproject.toml` as source of truth
- Git source specified explicitly overrides PyPI
- `uv sync` will now use GitHub version
- Fix persists across lock file updates

### 2. Force Reinstall from GitHub

**Commands executed:**
```powershell
# Stop backend server first (required - uvicorn.exe is locked)

# Reinstall from GitHub with Git LFS skip
$env:GIT_LFS_SKIP_SMUDGE="1"
uv pip install --force-reinstall "git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/core"

# Update lock file to reflect Git source
uv lock
```

**Result:**
```bash
PS> uv pip list | Select-String "agent-framework"
agent-framework-core  1.0.0b251007 (from git+https://...)  # ✅ Git source
```

### 3. Verify Fix Present

**Commands:**
```powershell
# Should return NO matches (lock was removed)
Select-String -Path ".venv\Lib\site-packages\agent_framework\_workflows\_magentic.py" -Pattern "self._inner_loop_lock"

# Should return matches (method was renamed)
Select-String -Path ".venv\Lib\site-packages\agent_framework\_workflows\_magentic.py" -Pattern "_run_inner_loop_helper"
```

**Results:**
- ✅ `self._inner_loop_lock` NOT FOUND (lock removed)
- ✅ `_run_inner_loop_helper` FOUND (method renamed)

### 4. Verify uv.lock Updated

**After `uv lock`:**
```toml
[[package]]
name = "agent-framework-core"
version = "1.0.0b251007"
source = { git = "https://github.com/microsoft/agent-framework.git?subdirectory=python%2Fpackages%2Fcore&rev=main#9148392d00dafa47a95178622f3800f89bbf0425" }
```

✅ **Now references Git source with commit hash 9148392**

## Package Management Best Practices

### Why Git-Based pip Installs Are Temporary

1. **`pip install git+...`**: Temporary installation
   - Not recorded in `pyproject.toml`
   - Overwritten by `uv sync` or `uv lock`
   - Good for: Quick testing

2. **`pyproject.toml` with Git source**: Permanent installation
   - Recorded as project dependency
   - Persists across lock file updates
   - Good for: Production use, ongoing development

### UV Package Manager Behavior

- `uv` uses `pyproject.toml` as **source of truth**
- `uv.lock` is **generated** from `pyproject.toml`
- `uv sync`: Reinstalls all packages based on lock file
- `uv lock`: Regenerates lock file from `pyproject.toml`

**Key insight**: Manual `pip install` changes are **temporary** unless you update `pyproject.toml`

## Testing After Fix

### Start Backend
```powershell
uv run uvicorn backend.main:app --reload
```

### Test Device Timeline Scenario

**What to look for:**

1. **No deadlock after "entering inner loop"**
   ```
   [INFO] Magentic Orchestrator: Outer loop - entering inner loop
   [INFO] Magentic Orchestrator: Superstep 1  # ✅ Should progress
   ```

2. **All 9 queries execute** (from improved instructions)
   - Step 1: Device Baseline
   - Step 2: Compliance Timeline
   - Step 3: Device Snapshot (repeat)
   - Step 4: Group Membership
   - Step 5: Group Definitions
   - Step 6: Deployment Snapshots
   - Step 7: Application Installs
   - Step 8: Check-in Activity
   - Step 9: Policy Assignments (optional)

3. **No stalling after reset/replan**
   - If orchestrator detects stalling and resets
   - Should continue progressing through supersteps
   - Should NOT hang indefinitely

## Related Documentation

- `AGENT_FRAMEWORK_DEADLOCK_FIX.md` - Original deadlock fix and verification
- `AGENT_MESSAGE_LOGGING.md` - Message logging for debugging
- `CONVERSATION_STATE_FIX.md` - Context extraction fix
- `COMPLETE_FIX_SUMMARY.md` - Overview of all fixes

## Permanent Solution Summary

✅ **Problem:** Git-based installation was temporary and got overwritten  
✅ **Solution:** Added Git source to `pyproject.toml` for persistence  
✅ **Verification:** Lock file now shows Git source with commit hash  
✅ **Result:** Fix will persist across `uv sync` and `uv lock` commands  

**The deadlock fix is now permanently installed and will not be lost again!**
