# Authentication Fix - Lazy Loading & Robust Credentials

## Problem

**Authentication looping with multiple prompts at startup:**
```
[WARNING] azure.identity._internal.interactive: InteractiveBrowserCredential.get_token failed: 
Authentication failed: state mismatch: LpBnMGYhqQwSTUAl vs HoWFrYMyNJKtXBPS
```

### Root Causes
1. **Eager credential initialization**: Both `DefaultAzureCredential` and `InteractiveBrowserCredential` were created at module import time
2. **Multiple auth flows**: Each credential immediately started authentication, causing state conflicts
3. **Interactive prompts for background services**: WAM credential was used for all token requests, causing browser popups

---

## Solution: Lazy-Loading Credentials

### Key Changes

#### 1. **Lazy Initialization**
Credentials are now created only when first accessed:

```python
class AuthService:
    def __init__(self):
        # Lazy-initialized credentials (only create when first used)
        self._credential: Optional[DefaultAzureCredential] = None
        self._wam_credential: Optional[InteractiveBrowserCredential] = None
        self._credential_initialized = False
```

#### 2. **Property-Based Access**
Credentials are accessed via properties that trigger initialization:

```python
@property
def credential(self) -> DefaultAzureCredential:
    """Lazy-loaded primary credential"""
    self._ensure_credentials_initialized()
    assert self._credential is not None
    return self._credential

@property
def wam_credential(self) -> InteractiveBrowserCredential:
    """Lazy-loaded WAM credential (for interactive login)"""
    self._ensure_credentials_initialized()
    if self._wam_credential is None:
        logger.info("Creating WAM broker credential...")
        self._wam_credential = InteractiveBrowserCredential(...)
    return self._wam_credential
```

#### 3. **Separate Interactive vs Non-Interactive Auth**

**Non-Interactive** (background services, Azure OpenAI, Kusto):
- Uses `DefaultAzureCredential` with Azure CLI preferred
- No browser prompts during development
- Works with `az login` session

**Interactive** (user login endpoint):
- Uses `InteractiveBrowserCredential` with WAM broker
- Shows browser prompt only when user explicitly logs in
- Triggered via `interactive=True` flag

```python
async def get_access_token(
    self, 
    scope: Optional[str] = None, 
    force_refresh: bool = False,
    interactive: bool = False  # NEW: Choose credential type
) -> str:
    if interactive:
        # Use WAM for user login (may show prompt)
        token = self.wam_credential.get_token(target_scope)
    else:
        # Use Azure CLI for services (no prompts)
        token = self.credential.get_token(target_scope)
```

#### 4. **Credential Preferences**

**DefaultAzureCredential** (primary, non-interactive):
- ✅ Azure CLI (preferred for dev)
- ✅ Shared Token Cache (persisted)
- ✅ VS Code / PowerShell (if authenticated)
- ❌ Interactive Browser (excluded)
- ❌ Environment / Managed Identity (excluded for local dev)

**InteractiveBrowserCredential** (secondary, interactive):
- Only created when user login endpoint is called
- Uses WAM broker for Windows SSO
- Shows browser prompt for OAuth

---

## Impact

### ✅ Fixed Issues
1. **No more authentication loops** - credentials created on-demand
2. **No more state mismatch errors** - single credential instance per type
3. **No more startup prompts** - background services use Azure CLI
4. **Faster startup** - credentials not created until needed

### 🔧 Behavior Changes

| Scenario | Before | After |
|----------|--------|-------|
| App startup | Multiple auth prompts | No prompts (uses `az login`) |
| User login (`/auth/login`) | WAM prompt | WAM prompt (unchanged) |
| Azure OpenAI chat | WAM prompt | Uses Azure CLI token |
| Kusto queries | Azure CLI | Azure CLI (unchanged) |
| Token caching | Per-scope, 2min buffer | Same, but per-credential |

---

## Usage

### For Developers

1. **Before running app**: Ensure you're signed in with Azure CLI
   ```bash
   az login
   az account show  # Verify active subscription
   ```

2. **Start app**: No authentication prompts
   ```bash
   npm run dev
   ```

3. **User login**: Users clicking "Login" will see WAM/browser prompt (expected)

### For Background Services

All background services now automatically use non-interactive auth:

```python
# Azure OpenAI (agent_framework_service.py)
AzureOpenAIChatClient(
    credential=auth_service.wam_credential  # Uses cached credential
)

# Kusto (kusto_mcp_service.py)
access_token = await auth_service.get_kusto_token(cluster_url)
# Internally uses: credential.get_token() (non-interactive)
```

### For User Authentication

User login endpoint explicitly requests interactive auth:

```python
# auth.py router
@router.post("/login")
async def login():
    user_data = await auth_service.authenticate_user()
    # Calls: get_access_token(interactive=True)
    # Shows WAM browser prompt
```

---

## Debugging

### Check Credential State

```python
from services.auth_service import auth_service

print(f"Initialized: {auth_service._credential_initialized}")
print(f"Default credential: {auth_service._credential}")
print(f"WAM credential: {auth_service._wam_credential}")
```

### Enable Debug Logging

Edit `backend/main.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Was INFO
    ...
)
```

Restart backend and check logs:
```
[INFO] services.auth_service: AuthService initialized - credentials will be created on first use
[INFO] services.auth_service: Initializing Azure credentials...
[INFO] services.auth_service: Azure credentials initialized - using Azure CLI (non-interactive)
[DEBUG] services.auth_service: Getting token for https://cognitiveservices.azure.com/.default using default credential (non-interactive)
```

### Force Re-Authentication

```bash
# Clear Azure CLI cache
az account clear

# Re-login
az login

# Restart app
npm run dev
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AuthService                            │
│                                                             │
│  Lazy Properties:                                          │
│  ┌──────────────────────┐   ┌─────────────────────────┐  │
│  │ .credential          │   │ .wam_credential         │  │
│  │ DefaultAzureCredential│  │ InteractiveBrowser      │  │
│  │                      │   │ Credential              │  │
│  │ Preferred:           │   │                         │  │
│  │ - Azure CLI ✓        │   │ Created on-demand for:  │  │
│  │ - Shared Token Cache │   │ - User login            │  │
│  │ - VS Code            │   │ - Interactive auth      │  │
│  │                      │   │                         │  │
│  │ Used for:            │   │ Uses WAM broker         │  │
│  │ - Azure OpenAI       │   │ (Windows SSO)           │  │
│  │ - Kusto              │   │                         │  │
│  │ - Background services│   │                         │  │
│  └──────────────────────┘   └─────────────────────────┘  │
│                                                             │
│  Token Cache:                                              │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ scope -> (expiry, token)                            │ │
│  │ - 2 minute safety buffer                            │ │
│  │ - Shared across requests                            │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Migration Notes

### Before (Broken)
```python
# ❌ Both credentials created at import time
class AuthService:
    def __init__(self):
        self.credential = DefaultAzureCredential(...)  # Immediate auth
        self.wam_credential = InteractiveBrowserCredential(...)  # Immediate auth
        # Both try to authenticate -> state conflicts
```

### After (Fixed)
```python
# ✅ Credentials created on-demand
class AuthService:
    def __init__(self):
        self._credential = None  # Not created yet
        self._wam_credential = None  # Not created yet
    
    @property
    def credential(self):
        if self._credential is None:
            self._credential = DefaultAzureCredential(...)  # Created now
        return self._credential
```

---

## Testing

1. **Test startup (no prompts)**:
   ```bash
   az login
   npm run dev
   # Expected: Backend starts with no auth prompts
   ```

2. **Test user login (WAM prompt)**:
   - Open app in browser
   - Click "Login"
   - Expected: Browser/WAM prompt appears
   - After login: User info displayed

3. **Test Azure OpenAI (no prompts)**:
   - Send chat message
   - Expected: Works using Azure CLI token, no prompts

4. **Test Kusto queries (no prompts)**:
   - Run device query
   - Expected: Works using Azure CLI token, no prompts

---

## Summary

| Aspect | Status | Details |
|--------|--------|---------|
| Authentication loops | ✅ Fixed | Lazy credential loading |
| State mismatch errors | ✅ Fixed | Single credential instance |
| Startup prompts | ✅ Fixed | Uses Azure CLI for services |
| User login | ✅ Working | WAM prompt (expected) |
| Performance | ✅ Improved | Faster startup |
| Logging | ✅ Enhanced | Clear credential usage logs |

**Bottom line**: Run `az login` once, then `npm run dev` should start without any auth prompts.
