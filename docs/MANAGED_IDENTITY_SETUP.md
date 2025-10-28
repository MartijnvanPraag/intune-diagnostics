# Managed Identity Setup for Azure AI Services

## Overview

Your app now uses **Managed Identity** for Azure Cognitive Services authentication when running in Azure App Service. This eliminates the need for:
- Client secrets
- Connection strings
- Manual token management

## What Changed

### Backend Authentication Flow

**Azure App Service (Production)**:
1. User authenticates via MSAL in browser → gets access token for your app
2. Frontend sends token with API requests → backend validates it
3. **When calling Azure OpenAI/AI services**: Backend uses **Managed Identity** (not user token)
   - No secrets stored anywhere
   - Azure handles authentication automatically
   - More secure than storing credentials

**Local Development**:
1. User authenticates via MSAL → frontend sends token to backend
2. Backend stores user token in `auth_service`
3. Falls back to Azure CLI if user token not available
4. Works seamlessly with local Azure OpenAI development

### Code Changes

- `backend/services/auth_service.py`:
  - Detects Azure App Service via `WEBSITE_INSTANCE_ID` environment variable
  - Automatically uses `ManagedIdentityCredential` in production
  - Falls back to user token or Azure CLI in development

- `backend/routers/auth.py`:
  - Stores user's MSAL token when they authenticate
  - Updates token on profile checks
  - Token used for authorization but NOT for AI services in production

## Azure Setup Required

### Step 1: Enable Managed Identity in Azure App Service

```bash
# Enable system-assigned managed identity
az webapp identity assign \
  --name intunediagnostics \
  --resource-group <your-resource-group>

# This will output a principalId (save this for Step 2)
```

**Or via Azure Portal**:
1. Go to Azure Portal → App Services → `intunediagnostics`
2. Navigate to **Identity** (under Settings)
3. Switch **System assigned** tab to **On**
4. Click **Save**
5. Copy the **Object (principal) ID** (you'll need this)

### Step 2: Grant Managed Identity Access to Azure OpenAI

```bash
# Get your Azure OpenAI resource ID
OPENAI_RESOURCE_ID=$(az cognitiveservices account show \
  --name <your-openai-resource-name> \
  --resource-group <your-resource-group> \
  --query id -o tsv)

# Grant "Cognitive Services OpenAI User" role to Managed Identity
az role assignment create \
  --assignee <principalId-from-step-1> \
  --role "Cognitive Services OpenAI User" \
  --scope $OPENAI_RESOURCE_ID
```

**Or via Azure Portal**:
1. Go to Azure Portal → Cognitive Services → your Azure OpenAI resource
2. Navigate to **Access Control (IAM)**
3. Click **+ Add** → **Add role assignment**
4. Select role: **Cognitive Services OpenAI User**
5. Click **Next**
6. Select **Managed Identity**
7. Click **+ Select members**
8. Filter to **App Service** and select `intunediagnostics`
9. Click **Review + assign**

### Step 3: Update App Service Configuration (Optional)

These environment variables are already set in your code defaults, but you can override them if needed:

```bash
az webapp config appsettings set \
  --name intunediagnostics \
  --resource-group <your-resource-group> \
  --settings \
    AZURE_CLIENT_ID="fbadc585-90b3-48ab-8052-c1fcc32ce3fe" \
    AZURE_TENANT_ID="72f988bf-86f1-41af-91ab-2d7cd011db47"
```

### Step 4: Verify Managed Identity is Working

After deployment, check the App Service logs:

```bash
az webapp log tail --name intunediagnostics --resource-group <your-resource-group>
```

Look for:
- ✅ `AuthService initialized - running in Azure App Service, will use Managed Identity for AI services`
- ✅ `Creating Managed Identity credential for Azure App Service`
- ✅ Token acquisition succeeding without errors

If you see DefaultAzureCredential errors, it means Managed Identity isn't set up correctly.

## Benefits

### Security
- ✅ No secrets in code or configuration
- ✅ No connection strings to manage
- ✅ Automatic token rotation by Azure
- ✅ Least-privilege access (only what you grant)

### Simplicity
- ✅ No manual token refresh logic
- ✅ Works seamlessly in production
- ✅ Still supports local development
- ✅ No code changes needed for deployment

### Compliance
- ✅ Follows Azure security best practices
- ✅ Auditable via Azure Activity Logs
- ✅ Supports Azure Policy enforcement
- ✅ Works with Private Endpoints

## Troubleshooting

### Error: "ManagedIdentityCredential authentication unavailable"

**Cause**: Managed Identity not enabled on App Service

**Fix**: Complete Step 1 above

### Error: "Authorization failed"

**Cause**: Managed Identity doesn't have permission to Azure OpenAI

**Fix**: Complete Step 2 above

### Error: "DefaultAzureCredential failed to retrieve a token"

**Cause**: Running in App Service but environment variable detection failing

**Fix**: Check that `WEBSITE_INSTANCE_ID` environment variable exists (set automatically by Azure)

## Local Development

No changes needed! The code automatically:
1. Detects it's NOT in Azure App Service
2. Uses user's MSAL token from frontend
3. Falls back to Azure CLI if needed

To test locally, just ensure you're signed in with:
```bash
az login
```

## Next Steps

1. ✅ Enable Managed Identity (Step 1)
2. ✅ Grant Azure OpenAI access (Step 2)
3. ✅ Deploy updated code
4. ✅ Test authentication flow
5. ✅ Remove any old credentials from configuration

## References

- [Azure Managed Identity Overview](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview)
- [Azure OpenAI with Managed Identity](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/managed-identity)
- [App Service Managed Identity](https://learn.microsoft.com/en-us/azure/app-service/overview-managed-identity)
