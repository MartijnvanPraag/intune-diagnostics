# OAuth Setup Checklist

## ✅ Entra App Configuration Steps

### 1. Platform Configuration
- [ ] Go to Azure Portal → Entra ID → App Registrations
- [ ] Find app: `fbadc585-90b3-48ab-8052-c1fcc32ce3fe`
- [ ] Authentication → Add a platform → **Single-page application**
- [ ] Add Redirect URIs:
  - [ ] `https://intunediagnostics.azurewebsites.net` (production)
  - [ ] `http://localhost:5173` (development)
- [ ] Check ✅ **Access tokens**
- [ ] Check ✅ **ID tokens**
- [ ] Ensure **Allow public client flows** is ❌ **OFF** (PKCE is more secure)

### 2. API Permissions
- [ ] API permissions → Add a permission → Microsoft Graph → Delegated permissions
- [ ] Add `User.Read`
- [ ] Add `openid`
- [ ] Add `profile`
- [ ] Add `email`
- [ ] Click **Grant admin consent** (if admin)

### 3. Optional - Token Configuration
- [ ] Token configuration → Add optional claim → ID Token
  - [ ] Add `email`, `family_name`, `given_name`
- [ ] Token configuration → Add optional claim → Access Token
  - [ ] Add `email`, `family_name`, `given_name`

### 4. Optional - Expose an API
- [ ] Expose an API → Add a scope
- [ ] Application ID URI: `api://fbadc585-90b3-48ab-8052-c1fcc32ce3fe`
- [ ] Scope name: `access_as_user`
- [ ] Who can consent: Admins and users
- [ ] Save

---

## ✅ Code Changes Made

### Frontend Changes
- [x] Installed `@azure/msal-browser` and `@azure/msal-react`
- [x] Created `frontend/src/config/authConfig.ts` with MSAL configuration
- [x] Created `frontend/src/config/axiosConfig.ts` with token interceptor
- [x] Updated `frontend/src/main.tsx` to wrap app with `MsalProvider`
- [x] Updated `frontend/src/contexts/AuthContext.tsx` to use MSAL hooks
- [x] Updated `frontend/src/services/authService.ts` to send Bearer tokens

### Backend Changes
- [x] Added `PyJWT[crypto]>=2.8.0` to `pyproject.toml`
- [x] Updated `backend/routers/auth.py` with JWT validation
- [x] Removed `/login` endpoint (no longer needed)
- [x] Added `verify_token()` dependency for protected endpoints
- [x] Updated `/register` endpoint to validate tokens

---

## ✅ Testing Checklist

### Local Testing
- [ ] Install backend dependencies: `cd backend && uv sync`
- [ ] Start backend: `uv run uvicorn main:app --reload --port 8000`
- [ ] Install frontend dependencies: `cd frontend && npm install`
- [ ] Start frontend: `npm run dev`
- [ ] Navigate to `http://localhost:5173`
- [ ] Click "Sign in with Microsoft"
- [ ] Verify popup opens with Microsoft login
- [ ] Sign in with Microsoft account
- [ ] Verify redirect back to app
- [ ] Check browser console for errors
- [ ] Verify user is authenticated (see user name in UI)

### Production Testing
- [ ] Commit and push all changes
- [ ] Wait for GitHub Actions deployment to complete
- [ ] Navigate to `https://intunediagnostics.azurewebsites.net`
- [ ] Click "Sign in with Microsoft"
- [ ] Verify popup opens with Microsoft login
- [ ] Sign in with work/school account
- [ ] Verify redirect back to app
- [ ] Check browser DevTools console for errors
- [ ] Test API calls (should include Bearer token)
- [ ] Verify backend validates token correctly

---

## ✅ Verification Steps

### 1. Check MSAL Token in Browser
Open browser DevTools → Console:
```javascript
// Check if MSAL tokens are stored
Object.keys(localStorage).filter(k => k.includes('msal'))
```

### 2. Check Bearer Token in Network Tab
1. Open DevTools → Network tab
2. Make any API call
3. Click the request
4. Check **Request Headers**
5. Verify `Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...` is present

### 3. Check Backend Logs
Look for these log messages:
- ✅ `Token validated for user: user@example.com`
- ✅ `Created new user: user@example.com` (first login)
- ✅ `Updated user: user@example.com` (subsequent logins)

### 4. Check Token Claims
Backend should extract these claims:
- `oid` or `sub` → Azure AD user ID (unique identifier)
- `preferred_username` → Email address
- `name` → Display name
- `aud` → Should match your CLIENT_ID
- `iss` → Should be `https://login.microsoftonline.com/{tenant}/v2.0`

---

## 🚨 Troubleshooting

### Issue: "AADSTS50011: Redirect URI mismatch"
**Fix**: Add exact redirect URI to Entra App → Authentication → Redirect URIs

### Issue: "Token validation failed"
**Check**:
1. Token not expired (expires in 1 hour)
2. Audience matches CLIENT_ID
3. Issuer is Azure AD
4. Backend has correct CLIENT_ID in auth.py

### Issue: "401 Unauthorized on API calls"
**Check**:
1. Bearer token included in request headers
2. Token not expired
3. axios interceptor registered (imported in main.tsx)
4. Backend verify_token() working correctly

### Issue: "Popup blocked by browser"
**Fix**: Allow popups for your site, or switch to redirect flow:
```typescript
// In AuthContext.tsx, change:
await instance.loginPopup(loginRequest)
// To:
await instance.loginRedirect(loginRequest)
```

### Issue: "Can't sign in with personal Microsoft account"
**Fix**: Ensure authority is `common` not your specific tenant ID:
```typescript
authority: "https://login.microsoftonline.com/common"
```

---

## 📚 Documentation

- Full guide: [`docs/OAUTH_SETUP_GUIDE.md`](./OAUTH_SETUP_GUIDE.md)
- MSAL.js docs: https://github.com/AzureAD/microsoft-authentication-library-for-js
- Azure AD docs: https://learn.microsoft.com/en-us/entra/identity-platform/

---

## 🎉 Success Criteria

You'll know it's working when:
- ✅ No secrets stored in code
- ✅ Popup opens for Microsoft login
- ✅ User can sign in successfully
- ✅ User redirected back to app
- ✅ API calls include Bearer token
- ✅ Backend validates token successfully
- ✅ User data saved to database
- ✅ User stays logged in across page refreshes
- ✅ Tokens refresh automatically (no re-login for 90 days)

**Your app now uses enterprise-grade OAuth 2.0 authentication! 🚀**
