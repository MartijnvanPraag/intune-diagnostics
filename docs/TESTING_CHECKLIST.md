# Testing Checklist - Agent Framework Migration

## Prerequisites

- [ ] Close all PowerShell windows
- [ ] Open fresh PowerShell in `c:\dev\intune-diagnostics`
- [ ] Run: `az login` (if not already authenticated)
- [ ] Verify: `az account show` displays your subscription

---

## Test 1: Startup (No Auth Prompts)

**Expected**: Backend starts cleanly with no authentication prompts

```bash
npm run dev
```

**Success Criteria**:
- ✅ Backend starts without browser/WAM prompts
- ✅ Logs show: `[INFO] services.auth_service: AuthService initialized - credentials will be created on first use`
- ✅ Frontend loads at http://localhost:5173
- ✅ Backend running at http://localhost:8000

**If Failed**:
- Check `az account show` is valid
- Check logs for authentication errors
- Review `AUTHENTICATION_ROBUST_FIX.md`

---

## Test 2: Logging Consistency

**Expected**: Logs appear consistently on every startup

**Test Steps**:
1. Start app: `npm run dev`
2. Check backend logs for `[INFO]` messages
3. Stop app: CTRL+C
4. Start again: `npm run dev`
5. Check backend logs again

**Success Criteria**:
- ✅ Logs appear on first startup
- ✅ Logs appear on second startup
- ✅ Logs appear on third startup
- ✅ Log format is consistent: `[LEVEL] module.name: message`

**Example Expected Logs**:
```
[INFO] services.auth_service: AuthService initialized
[INFO] services.autogen_service: AgentService initialized
[INFO] services.kusto_mcp_service: Kusto MCP service initialized
```

**If Failed**:
- Check `backend/main.py` has `logging.basicConfig(force=True)`
- Check service files don't have `logging.basicConfig()` calls

---

## Test 3: Manual Restart Workflow

**Expected**: Backend restarts cleanly without hanging

**Test Steps**:
1. Start app: `npm run dev`
2. Make a small change to `backend/main.py` (add a comment)
3. Press CTRL+C (should stop immediately)
4. Run: `npm run dev` again

**Success Criteria**:
- ✅ CTRL+C stops backend within 2 seconds
- ✅ No "WatchFiles detected changes" message (reload disabled)
- ✅ Backend restarts successfully
- ✅ Logs appear after restart

**If Failed**:
- Check `package.json` line 7 has no `--reload` flag
- Kill PowerShell window if hung
- Open new PowerShell and try again

---

## Test 4: Autogen Framework (Baseline)

**Expected**: Tables render correctly with Autogen (control test)

**Test Steps**:
1. Open app: http://localhost:5173
2. Go to **Settings**
3. Ensure **Framework** is set to "Autogen Framework"
4. Go to **Advanced Scenarios**
5. Select scenario: "Device Details Lookup"
6. Enter device ID (or use default)
7. Click "Run Scenario"

**Success Criteria**:
- ✅ AI Insight Summary displays markdown table
- ✅ "Kusto Query Results" pane shows structured table with columns/rows
- ✅ Table has multiple columns (DeviceId, AccountId, OSVersion, etc.)
- ✅ Data is readable and formatted correctly

**If Failed**:
- This is a baseline test - Autogen should work
- Check Kusto MCP service is running
- Check authentication (az login)

---

## Test 5: Agent Framework Table Rendering (PRIMARY TEST)

**Expected**: Tables render correctly with Agent Framework (NEW FIX)

**Test Steps**:
1. Go to **Settings**
2. Change **Framework** to "Agent Framework"
3. Save settings
4. Go to **Advanced Scenarios**
5. Select scenario: "Device Details Lookup"
6. Enter device ID (or use default)
7. Click "Run Scenario"
8. **WAIT** for agent to complete (may take 10-30 seconds)

**Success Criteria**:
- ✅ AI Insight Summary displays markdown table
- ✅ **"Kusto Query Results" pane shows structured table** (THIS IS THE KEY FIX)
- ✅ Table has columns: DeviceId, AccountId, OSVersion, etc.
- ✅ Data is identical to Autogen test
- ✅ No "No table data available" message

**Backend Logs to Check**:
```
[INFO] services.agent_framework_service: Processing response with X messages
[INFO] services.agent_framework_service: Found function result from call_id: ...
[INFO] services.agent_framework_service: Extracted 1 objects from function results
[INFO] services.agent_framework_service: Found 1 unique tables
```

**If Failed**:
- Check backend logs for `[WARNING] No tables found`
- Check if Kusto tool was called
- Review `backend/services/agent_framework_service.py` lines 925-970
- Report logs to developer

---

## Test 6: User Login (Interactive Auth)

**Expected**: User login shows WAM/browser prompt (expected behavior)

**Test Steps**:
1. Open app (if not logged in)
2. Click **"Login"** button
3. **EXPECT**: Browser or WAM authentication prompt
4. Complete authentication
5. User info should display

**Success Criteria**:
- ✅ WAM or browser prompt appears (this is correct)
- ✅ After login, user email/name displayed
- ✅ Dashboard accessible
- ✅ No state mismatch errors in logs

**Backend Logs to Check**:
```
[INFO] services.auth_service: Authenticating user interactively...
[INFO] services.auth_service: Creating WAM broker credential...
[INFO] services.auth_service: User authenticated: user@example.com
```

**If Failed**:
- Check for state mismatch errors in logs
- Review `AUTHENTICATION_ROBUST_FIX.md`
- Try `az account clear` + `az login` again

---

## Test 7: Background Service Auth (No Prompts)

**Expected**: Azure OpenAI and Kusto work without auth prompts

**Test Steps**:
1. With app running
2. Go to **Chat** page
3. Send message: "What devices are running Windows 11?"
4. **SHOULD NOT** see any auth prompts
5. Agent should query Kusto and respond

**Success Criteria**:
- ✅ No authentication prompts during chat
- ✅ Azure OpenAI responds
- ✅ Kusto queries execute
- ✅ Response includes data

**Backend Logs to Check**:
```
[DEBUG] services.auth_service: Getting token for https://cognitiveservices.azure.com/.default using default credential (non-interactive)
[INFO] services.kusto_mcp_service: Executing Kusto query...
```

**If Failed**:
- Check `az account show` is valid
- Check auth_service uses `interactive=False` for services
- Review `AUTHENTICATION_ROBUST_FIX.md`

---

## Test 8: Framework Switching

**Expected**: Can switch between frameworks without issues

**Test Steps**:
1. Run query with **Autogen** → note results
2. Go to **Settings**
3. Switch to **Agent Framework**
4. Run same query → compare results
5. Switch back to **Autogen**
6. Run query again → verify still works

**Success Criteria**:
- ✅ Both frameworks produce similar results
- ✅ Tables render in both frameworks
- ✅ No errors when switching
- ✅ Settings persist across switches

---

## Test 9: Error Handling

**Expected**: Graceful error handling for invalid queries

**Test Steps**:
1. Set framework to **Agent Framework**
2. Advanced Scenarios
3. Enter invalid device ID: `00000000-0000-0000-0000-000000000000`
4. Run scenario

**Success Criteria**:
- ✅ Agent responds with "No results found" or similar
- ✅ No crash or stack traces in UI
- ✅ Backend logs show query executed
- ✅ App remains functional

---

## Summary Checklist

| Test | Status | Notes |
|------|--------|-------|
| 1. Startup (no prompts) | ☐ Pass / ☐ Fail | |
| 2. Logging consistency | ☐ Pass / ☐ Fail | |
| 3. Manual restart | ☐ Pass / ☐ Fail | |
| 4. Autogen tables | ☐ Pass / ☐ Fail | |
| 5. **Agent Framework tables** | ☐ Pass / ☐ Fail | **CRITICAL** |
| 6. User login (WAM prompt) | ☐ Pass / ☐ Fail | |
| 7. Background auth (no prompts) | ☐ Pass / ☐ Fail | |
| 8. Framework switching | ☐ Pass / ☐ Fail | |
| 9. Error handling | ☐ Pass / ☐ Fail | |

---

## Success Criteria

**Migration is complete when**:
- ✅ All 9 tests pass
- ✅ Agent Framework tables render (Test 5)
- ✅ No authentication loops (Test 1, 7)
- ✅ Logging always works (Test 2)

---

## Reporting Issues

If any test fails, collect:
1. **Backend logs** (full terminal output)
2. **Browser console** (F12 → Console tab)
3. **Screenshots** of the issue
4. **Test number** that failed
5. **Steps to reproduce**

Reference documentation:
- `SESSION_SUMMARY.md` - Overview of all changes
- `AUTHENTICATION_ROBUST_FIX.md` - Auth troubleshooting
- `RELOAD_AND_LOGGING_FIX.md` - Reload/logging issues
- `TABLE_RENDERING_DEBUG.md` - Table rendering issues

---

## Quick Smoke Test (30 seconds)

For rapid verification:
```bash
# 1. Start app
npm run dev

# 2. Check no auth prompts (5 sec)
# 3. Check logs appear (5 sec)
# 4. Open browser → Settings → Agent Framework (10 sec)
# 5. Advanced Scenarios → Run any scenario (10 sec)
# 6. Verify tables in "Kusto Query Results" pane ✅
```

**If tables appear in Test 5, migration is successful!** 🎉
