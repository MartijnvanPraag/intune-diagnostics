# OAuth 2.0 Authentication Setup Guide

## Overview

This application uses **OAuth 2.0 Authorization Code Flow with PKCE** for authentication. This is the recommended approach for Single-Page Applications (SPAs) because it:

- ✅ Does NOT require storing client secrets
- ✅ All authentication happens in the browser (secure)
- ✅ Uses PKCE (Proof Key for Code Exchange) for enhanced security
- ✅ Tokens are automatically refreshed by MSAL.js
- ✅ Backend validates tokens (doesn't acquire them)

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Browser   │         │  Azure AD    │         │   Backend   │
│   (MSAL.js) │         │  (Entra App) │         │  (FastAPI)  │
└──────┬──────┘         └──────┬───────┘         └──────┬──────┘
       │                       │                        │
       │ 1. Login redirect     │                        │
       ├──────────────────────>│                        │
       │                       │                        │
       │ 2. User authenticates │                        │
       │    (Microsoft login)  │                        │
       │                       │                        │
       │ 3. Auth code + PKCE   │                        │
       │<──────────────────────┤                        │
       │                       │                        │
       │ 4. Exchange code      │                        │
       │    for tokens         │                        │
       ├──────────────────────>│                        │
       │                       │                        │
       │ 5. ID + Access tokens │                        │
       │<──────────────────────┤                        │
       │                       │                        │
       │ 6. API call with      │                        │
       │    Bearer token       │                        │
       ├───────────────────────────────────────────────>│
       │                       │                        │
       │                       │                        │ 7. Validate
       │                       │                        │    JWT token
       │                       │                        │
       │ 8. API response       │                        │
       │<───────────────────────────────────────────────┤
```

## Entra App Configuration

### Required Settings

**App ID**: `fbadc585-90b3-48ab-8052-c1fcc32ce3fe`

### 1. Authentication Platform Configuration

1. Navigate to **Azure Portal** → **Entra ID** → **App Registrations**
2. Find your app: `fbadc585-90b3-48ab-8052-c1fcc32ce3fe`
3. Go to **Authentication** → **Add a platform** → **Single-page application**
4. Add Redirect URIs:
   - Production: `https://intunediagnostics.azurewebsites.net`
   - Development: `http://localhost:5173`
5. Under **Implicit grant and hybrid flows**:
   - ✅ Check **Access tokens** (used for OAuth 2.0 implicit flow)
   - ✅ Check **ID tokens** (used for OpenID Connect)
6. **Allow public client flows**: ❌ NO (we use PKCE instead - more secure)

### 2. API Permissions

Add the following **Delegated Permissions** from **Microsoft Graph**:

| Permission | Type | Description | Admin Consent Required |
|------------|------|-------------|------------------------|
| `User.Read` | Delegated | Read user profile | No |
| `openid` | Delegated | OpenID Connect sign-in | No |
| `profile` | Delegated | View user's basic profile | No |
| `email` | Delegated | View user's email address | No |

**Grant Admin Consent**: Click **Grant admin consent for [Your Organization]** if you have admin rights.

### 3. Token Configuration (Optional but Recommended)

1. Go to **Token configuration** → **Add optional claim**
2. Select **ID Token**:
   - ✅ `email`
   - ✅ `family_name`
   - ✅ `given_name`
3. Select **Access Token**:
   - ✅ `email`
   - ✅ `family_name`
   - ✅ `given_name`

### 4. Expose an API (Optional - for custom API scope)

If you want to create a custom API scope for your backend:

1. Go to **Expose an API** → **Add a scope**
2. Application ID URI: `api://fbadc585-90b3-48ab-8052-c1fcc32ce3fe`
3. Scope name: `access_as_user`
4. Who can consent: **Admins and users**
5. Admin consent display name: "Access Intune Diagnostics as a user"
6. Admin consent description: "Allow the application to access Intune Diagnostics on behalf of the signed-in user"
7. State: **Enabled**

## Frontend Implementation

### MSAL.js Configuration

Location: `frontend/src/config/authConfig.ts`

```typescript
export const msalConfig: Configuration = {
  auth: {
    clientId: "fbadc585-90b3-48ab-8052-c1fcc32ce3fe",
    authority: "https://login.microsoftonline.com/common", // Multi-tenant
    redirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "localStorage", // Persist tokens across sessions
  },
};
```

### Authentication Flow

1. **User clicks "Sign in"** → `AuthContext.login()` called
2. **MSAL opens popup** → User signs in with Microsoft credentials
3. **MSAL receives tokens** → Stored securely in localStorage
4. **Frontend calls backend** → `/api/auth/register` with Bearer token
5. **Backend validates token** → Creates/updates user in database
6. **User is authenticated** → Can access protected resources

### Automatic Token Inclusion

All API requests automatically include the Bearer token via axios interceptor:

```typescript
// frontend/src/config/axiosConfig.ts
axios.interceptors.request.use(async (config) => {
  if (config.url?.startsWith('/api') && tokenProvider) {
    const token = await tokenProvider()
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})
```

## Backend Implementation

### JWT Token Validation

Location: `backend/routers/auth.py`

The backend **validates** tokens (does NOT acquire them):

```python
async def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    # Extract Bearer token
    token = authorization.split()[1]
    
    # Get Azure AD public keys for signature verification
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    
    # Decode and validate
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=CLIENT_ID,  # Validates token is for our app
        issuer=ISSUER,       # Validates token is from Azure AD
    )
    return payload
```

### Protected Endpoints

Any endpoint can require authentication by depending on `verify_token`:

```python
@router.get("/protected-resource")
async def get_protected_resource(token_payload: dict = Depends(verify_token)):
    user_id = token_payload.get("oid")  # Azure AD user ID
    # ... use user_id to fetch data
```

## Security Features

### PKCE (Proof Key for Code Exchange)

- Generated dynamically for each login
- Prevents authorization code interception attacks
- No client secret needed (secure for SPAs)

### Token Validation

Backend validates:
1. ✅ **Signature** - Using Azure AD's public keys (JWKS)
2. ✅ **Expiration** - Token must not be expired
3. ✅ **Audience** - Token must be for our app (CLIENT_ID)
4. ✅ **Issuer** - Token must be from Azure AD (ISSUER)

### Automatic Token Refresh

MSAL.js automatically refreshes tokens before they expire:
- Access tokens: Valid for 1 hour
- Refresh tokens: Valid for 90 days (default)
- Silent refresh happens in background

## Testing Locally

### 1. Start Backend

```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

### 2. Start Frontend

```bash
cd frontend
npm run dev
```

### 3. Test Login Flow

1. Navigate to `http://localhost:5173`
2. Click "Sign in with Microsoft"
3. Sign in with your Microsoft account
4. Verify you're redirected back and authenticated

### 4. Verify Token in Browser Console

```javascript
// Get MSAL instance from localStorage
const msalCache = JSON.parse(localStorage.getItem('msal.token.keys.fbadc585-90b3-48ab-8052-c1fcc32ce3fe'))
console.log('Tokens stored:', msalCache)
```

## Troubleshooting

### "AADSTS50011: The redirect URI specified in the request does not match..."

**Solution**: Add the exact redirect URI to Entra App configuration.

### "Token validation failed: Invalid audience"

**Solution**: Ensure `audience` in token matches your `CLIENT_ID`.

### "CORS error when calling backend"

**Solution**: Ensure backend allows frontend origin in CORS settings.

### "401 Unauthorized" on API calls

**Possible causes**:
1. Token expired → MSAL should refresh automatically
2. Token not included in request → Check axios interceptor
3. Backend validation failing → Check backend logs

### Users can't sign in with personal Microsoft accounts

**Solution**: Use `authority: "https://login.microsoftonline.com/common"` for multi-tenant support.

## Environment Variables

### Frontend

Create `frontend/.env.local`:

```bash
# No secrets needed! Client ID is public for SPAs
VITE_AZURE_CLIENT_ID=fbadc585-90b3-48ab-8052-c1fcc32ce3fe
VITE_AZURE_TENANT_ID=common  # or your specific tenant ID
```

### Backend

Create `backend/.env`:

```bash
# Azure AD Configuration (public values, no secrets)
AZURE_CLIENT_ID=fbadc585-90b3-48ab-8052-c1fcc32ce3fe
AZURE_TENANT_ID=common

# Database
DATABASE_URL=sqlite+aiosqlite:///./intune_diagnostics.db

# Azure OpenAI (for AI features)
AZURE_OPENAI_ENDPOINT=your-endpoint-here
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
```

## Production Deployment

### Azure App Service Configuration

1. **App Settings** → Add:
   - `AZURE_CLIENT_ID`: `fbadc585-90b3-48ab-8052-c1fcc32ce3fe`
   - `AZURE_TENANT_ID`: `common` (or your tenant ID)

2. **Startup Command**: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app`

3. **Authentication**: ❌ DO NOT enable "App Service Authentication" (we handle it ourselves)

### Verify Production Deployment

1. Navigate to `https://intunediagnostics.azurewebsites.net`
2. Click "Sign in with Microsoft"
3. Sign in with your work/school account
4. Verify redirect back to app
5. Check browser console for any errors
6. Test protected API endpoints

## Migration from Old Authentication

### What Changed

**Before** (Server-side interactive auth):
- ❌ Backend tried to open browser (`InteractiveBrowserCredential`)
- ❌ Failed in Azure App Service (no display)
- ❌ 401 errors on all login attempts

**After** (OAuth 2.0 with PKCE):
- ✅ Browser handles authentication (MSAL.js)
- ✅ Works perfectly in Azure App Service
- ✅ No secrets stored anywhere
- ✅ Automatic token refresh

### Removed Code

- ❌ `backend/services/auth_service.py` - `authenticate_user()` method
- ❌ `backend/routers/auth.py` - `/login` endpoint (no longer needed)
- ❌ `frontend/src/services/authService.ts` - `login()` method (replaced with MSAL)

### New Code

- ✅ `frontend/src/config/authConfig.ts` - MSAL configuration
- ✅ `frontend/src/config/axiosConfig.ts` - Token interceptor
- ✅ `frontend/src/main.tsx` - MsalProvider wrapper
- ✅ `backend/routers/auth.py` - JWT validation using `verify_token()`

## Summary

🎉 **No secrets required!**
🔒 **Secure OAuth 2.0 flow with PKCE**
🔄 **Automatic token refresh**
✅ **Works in production Azure App Service**
🚀 **Industry-standard authentication**

Your app now uses the same authentication pattern as Microsoft Teams, Office 365, and other Microsoft cloud apps!
