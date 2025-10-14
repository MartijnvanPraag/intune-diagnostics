# Using the Fixed Deadlock Code - Quick Start Guide

**Date:** October 14, 2025  
**Status:** ✅ Fix Installed and Verified  
**Action Required:** Restart backend to use the fix

---

## Current Status

✅ **agent-framework-core** installed from GitHub main branch  
✅ **Deadlock fix verified** - lock removal confirmed  
✅ **Backend not running** - will use fixed code on next start

---

## What Was Fixed

The Git installation **initially didn't take effect** because:
1. First installation left old PyPI version in place
2. Package needed to be uninstalled and reinstalled with `--no-cache`
3. Now properly using Git version: `1.0.0b251007 (from git+...)`

**Verification completed:**
- ✅ Lock initialization removed (`self._inner_loop_lock = asyncio.Lock()` gone)
- ✅ Method renamed (`_run_inner_loop_locked` → `_run_inner_loop_helper`)
- ✅ No recursive lock acquisition possible

---

## How to Start the Backend with the Fix

### Option 1: Direct Run (Recommended)

```powershell
cd C:\dev\intune-diagnostics
uv run uvicorn backend.main:app --reload --log-level info
```

**Advantages:**
- `--reload` auto-restarts on code changes
- `--log-level info` shows detailed agent messages
- Uses the fixed agent-framework from .venv

### Option 2: VS Code Debugger

1. Open VS Code
2. Go to Run and Debug (Ctrl+Shift+D)
3. Select "Python: FastAPI" configuration
4. Press F5 to start with debugging

**Advantages:**
- Breakpoint support
- Variable inspection
- Automatic use of .venv interpreter

### Option 3: Production Mode

```powershell
cd C:\dev\intune-diagnostics
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## Verifying the Fix is Active

### Method 1: Check Logs on Startup

When the backend starts, you should see:

```
[INFO] Building Magentic workflow with 1 participants
```

**NO MORE:** Deadlock warnings or errors during workflow execution

### Method 2: Run a Test Query

After starting the backend:

```powershell
# Test the device timeline scenario
# Watch for the new agent message logs we just enabled
```

**Expected behavior:**
- Workflow should complete or hit max_rounds (20)
- If it stalls, it should successfully reset and replan WITHOUT deadlock
- You'll see detailed agent messages showing what's happening

### Method 3: Python Quick Check

```powershell
# Verify Python will use the fixed package
uv run python -c "import agent_framework._workflows._magentic as m; import inspect; print('Lock in code:', 'self._inner_loop_lock' in inspect.getsource(m.MagenticOrchestratorExecutor.__init__))"
```

**Expected output:** `Lock in code: False`

---

## Troubleshooting

### Issue: Backend still deadlocks

**Check:**
```powershell
# Verify the Git installation is active
uv pip show agent-framework-core
```

**Should show:**
```
Version: 1.0.0b251007 (from git+https://github.com/microsoft/agent-framework.git@...)
```

**If it shows just `1.0.0b251001` without the git URL:**
```powershell
# Reinstall with no cache
$env:GIT_LFS_SKIP_SMUDGE = "1"
uv pip uninstall agent-framework-core
uv pip install --no-cache "git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/core"
```

### Issue: Stalling still occurs but NOT deadlock

**This is different!** The fix prevents **deadlock**, but **stalling is a feature**:

- **Stalling** = Orchestrator detects no progress is being made
- **Deadlock** = Process freezes and never recovers
- **Stalling → Reset** = Normal workflow recovery mechanism

**What the fix does:**
- ✅ Prevents deadlock when reset is triggered
- ✅ Allows reset to actually work
- ❌ Does NOT prevent stalling detection (that's intentional)

If stalling persists after reset:
1. Check the new agent message logs (we just enabled these)
2. See what instructions the orchestrator is giving
3. Verify the agent is executing queries properly
4. Check if the agent is returning proper results

### Issue: "No running backend" but it IS running

**Check for processes in other terminals:**
```powershell
Get-Process python* | Where-Object { $_.Path -like "*intune-diagnostics*" }
```

**Kill all Python processes related to this project:**
```powershell
Get-Process python* | Where-Object { $_.Path -like "*intune-diagnostics*" } | Stop-Process -Force
```

---

## Expected Behavior After Fix

### ✅ Good (Fixed):
```
[INFO] Magentic Orchestrator: Stalling detected. Resetting and replanning
[INFO] Magentic Orchestrator: Resetting and replanning
[INFO] Magentic Orchestrator: Outer loop - entering inner loop
[INFO] Magentic Orchestrator: Inner loop - round 1
# <-- Workflow continues successfully (NO DEADLOCK)
```

### ❌ Bad (Deadlock - should not happen now):
```
[INFO] Magentic Orchestrator: Stalling detected. Resetting and replanning
[INFO] Magentic Orchestrator: Resetting and replanning
# <-- Process hangs here forever, no more logs
```

### ⚠️ Still Possible (Stalling - different issue):
```
[INFO] Magentic Orchestrator: Stalling detected. Resetting and replanning
[INFO] Magentic Orchestrator: Resetting and replanning
[INFO] Magentic Orchestrator: Outer loop - entering inner loop
[INFO] Magentic Orchestrator: Inner loop - round 1
[INFO] Magentic Orchestrator: Inner loop - round 2
[INFO] Magentic Orchestrator: Stalling detected. Resetting and replanning
# <-- Workflow resets AGAIN because agent still not making progress
```

**If you see repeated stalling**, the issue is NOT the deadlock fix but the agent behavior. Use the new message logging to diagnose.

---

## Complete Startup Checklist

Before running a test:

- [x] **Fix installed:** `uv pip show agent-framework-core` shows git source
- [x] **Fix verified:** Lock removal confirmed in installed package
- [x] **Backend stopped:** No existing Python/uvicorn processes running
- [x] **Message logging enabled:** Recent changes to agent_framework_service.py
- [ ] **Start backend:** `uv run uvicorn backend.main:app --reload --log-level info`
- [ ] **Watch logs:** Look for agent message details in the output
- [ ] **Run test:** Execute device timeline scenario
- [ ] **Analyze:** Review agent conversation logs to see why it stalls

---

## Quick Commands Reference

```powershell
# Verify fix installation
uv pip show agent-framework-core

# Check for running backend
Get-Process python* | Where-Object { $_.Path -like "*intune-diagnostics*" }

# Start backend with detailed logging
uv run uvicorn backend.main:app --reload --log-level info

# Watch logs in real-time (if logging to file)
Get-Content .\logs\backend.log -Wait -Tail 50

# Stop all backend processes
Get-Process python* | Where-Object { $_.Path -like "*intune-diagnostics*" } | Stop-Process -Force
```

---

## Related Documentation

- `docs/AGENT_FRAMEWORK_DEADLOCK_FIX.md` - Original deadlock fix documentation
- `docs/AGENT_MESSAGE_LOGGING.md` - Agent message logging for debugging
- `docs/TROUBLESHOOTING.md` - General troubleshooting guide

---

**Status:** ✅ Ready to start - Backend will use the fixed code on next launch
