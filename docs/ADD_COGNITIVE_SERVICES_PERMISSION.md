# Add Azure Cognitive Services Permission to Entra App

## Problem
User signs in with Microsoft.com account, but Azure resources are in a different tenant, causing:
```
Error code: 400 - {'error': {'code': 'Tenant provided in token does not match resource token'}}
```

## Solution
Add Azure Cognitive Services as a delegated permission to your Entra App, so the user's MSAL token can access Azure OpenAI.

## Steps

### 1. Expose API Scope (REQUIRED - Do This First!)

Your app needs to expose a `user_impersonation` scope:

1. Navigate to: https://portal.azure.com
2. Search for "App registrations" → Click on **intune-diagnostics**
3. In the left menu, click **Expose an API**
4. If you don't have an Application ID URI set:
   - Click **Set** next to "Application ID URI"
   - Accept the default: `api://fbadc585-90b3-48ab-8052-c1fcc32ce3fe`
   - Click **Save**
5. Click **+ Add a scope**
6. Fill in the scope details:
   - **Scope name**: `user_impersonation`
   - **Who can consent**: Admins and users
   - **Admin consent display name**: Access intune-diagnostics
   - **Admin consent description**: Allow the application to access intune-diagnostics on your behalf
   - **User consent display name**: Access intune-diagnostics
   - **User consent description**: Allow the application to access intune-diagnostics on your behalf
   - **State**: Enabled
7. Click **Add scope**

### 2. Open Azure Portal
Navigate to: https://portal.azure.com

### 2. Go to App Registrations (Skip if you just did Step 1)
- Search for "App registrations" in the top search bar
- Click on your app: **intune-diagnostics** (Client ID: `fbadc585-90b3-48ab-8052-c1fcc32ce3fe`)

### 3. Add API Permission
1. In the left menu, click **API permissions**
2. Click **+ Add a permission**
3. In the "Request API permissions" panel:
   - Click **APIs my organization uses**
   - Search for: **Azure Cognitive Services** or **Cognitive Services**
   - Click on **Azure Cognitive Services** in the results
4. Select **Delegated permissions** (NOT Application permissions)
5. Check the box for: **user_impersonation**
6. Click **Add permissions** at the bottom

### 4. Grant Admin Consent (Required for org accounts)
After adding the permission:
1. You'll see a new row: **Azure Cognitive Services** → **user_impersonation**
2. Status will show "Not granted"
3. Click **Grant admin consent for [Your Tenant]** button (top of permissions list)
4. Confirm by clicking **Yes**
5. Status should change to "Granted for [Your Tenant]" with a green checkmark

### 5. Verify Permissions
Your app should now have these API permissions:
- ✅ **Microsoft Graph** → User.Read (for user profile)
- ✅ **Azure Cognitive Services** → user_impersonation (for Azure OpenAI)

## Testing

After adding the permission:

1. **Clear your browser cache** (or use incognito mode)
2. Navigate to: https://intunediagnostics.azurewebsites.net
3. Sign in with your Microsoft.com account
4. You should see a **new consent prompt** asking:
   > "intune-diagnostics wants to access Azure Cognitive Services on your behalf"
5. Click **Accept**
6. Now your token will include the Cognitive Services scope
7. Backend will use this token to call Azure OpenAI (no tenant mismatch!)

## How It Works

### Before (Broken)
```
User Token (Microsoft tenant) → Try to access Azure OpenAI (Personal tenant)
❌ Tenant mismatch error
```

### After (Fixed)
```
User signs in → Consents to Cognitive Services access
→ Token includes both app access AND Cognitive Services scope
→ Backend uses this token for Azure OpenAI
✅ Same tenant, same token, no mismatch!
```

## No Secrets Required!
This solution maintains your requirement: **NO secrets stored anywhere**
- User authenticates interactively (MSAL browser popup)
- User consents to Cognitive Services access
- Backend uses the user's token (passed from frontend)
- Fully transparent, fully interactive, no client secrets needed

## Alternative: Managed Identity (For Production)
For a production-ready solution without user consent:
1. Enable **System-assigned Managed Identity** on your App Service
2. Grant the Managed Identity **Cognitive Services OpenAI User** role
3. Backend automatically detects Azure App Service and uses Managed Identity
4. No user interaction needed, no secrets, production-grade security

See `docs/MANAGED_IDENTITY_SETUP.md` for details.
