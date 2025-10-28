# 🚀 Docker Deployment Checklist

## ✅ What's Been Done

- [x] Created `Dockerfile` with Python 3.11 + Node.js 22 LTS
- [x] Created `.dockerignore` for optimized builds
- [x] Created `docker-compose.yml` for local testing
- [x] Created GitHub Actions workflow (`azure-deploy-docker.yml`)
- [x] Created comprehensive documentation
- [x] Committed all changes to git

## 📋 What You Need to Do

### Step 1: Test Locally (Recommended)

```bash
# Navigate to project directory
cd c:\dev\intune-diagnostics

# Build and run the container
docker-compose up -d

# Check logs (should show no Node.js errors!)
docker-compose logs -f

# Open browser to http://localhost:8000
# Sign in with your Microsoft account
# Try running a diagnostic scenario

# Verify Node.js is available
docker-compose exec app node --version
# Should output: v22.x.x

# Stop the container when done testing
docker-compose down
```

### Step 2: Configure Azure for Container Deployment

**Option A: Using Azure Portal**

1. Go to: https://portal.azure.com
2. Navigate to: App Services → intunediagnostics
3. Left menu → Deployment Center
4. Source: GitHub
5. Container type: Single Container
6. Registry: GitHub Container Registry (ghcr.io)
7. Image: martijnvanpraag/intune-diagnostics:latest
8. Save

**Option B: Using Azure CLI**

```bash
# Get your resource group name
$resourceGroup = az webapp show --name intunediagnostics --query resourceGroup -o tsv

# Configure for container deployment
az webapp config container set `
  --name intunediagnostics `
  --resource-group $resourceGroup `
  --docker-custom-image-name ghcr.io/martijnvanpraag/intune-diagnostics:latest `
  --docker-registry-server-url https://ghcr.io

# Set the port
az webapp config appsettings set `
  --name intunediagnostics `
  --resource-group $resourceGroup `
  --settings WEBSITES_PORT=8000
```

### Step 3: Set Up GitHub Actions Secrets

1. **Create Azure Service Principal:**

```bash
# Replace with your subscription ID and resource group
az ad sp create-for-rbac `
  --name "intune-diagnostics-deployment" `
  --role contributor `
  --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group} `
  --sdk-auth
```

Copy the entire JSON output.

2. **Add to GitHub Secrets:**

- Go to: https://github.com/MartijnvanPraag/intune-diagnostics/settings/secrets/actions
- Click: "New repository secret"
- Name: `AZURE_CREDENTIALS`
- Value: Paste the JSON from step 1
- Click: "Add secret"

### Step 4: Update Workflow File

Edit: `.github/workflows/azure-deploy-docker.yml`

Find line 87 and replace `<your-resource-group>`:

```yaml
# Before:
--resource-group <your-resource-group>

# After:
--resource-group YourActualResourceGroupName
```

Commit the change:
```bash
git add .github/workflows/azure-deploy-docker.yml
git commit -m "Configure resource group for Docker deployment"
```

### Step 5: Deploy to Azure

```bash
# Push to trigger GitHub Actions deployment
git push origin azure-app-service-deployment

# Monitor deployment at:
# https://github.com/MartijnvanPraag/intune-diagnostics/actions
```

### Step 6: Enable Managed Identity

```bash
# Enable system-assigned identity
az webapp identity assign `
  --name intunediagnostics `
  --resource-group $resourceGroup

# Copy the principalId from the output

# Grant Azure OpenAI access (replace placeholders)
az role assignment create `
  --assignee <principal-id-from-above> `
  --role "Cognitive Services OpenAI User" `
  --scope /subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.CognitiveServices/accounts/{openai-account-name}
```

### Step 7: Verify Deployment

```bash
# Check container logs
az webapp log tail --name intunediagnostics --resource-group $resourceGroup

# Test the application
curl https://intunediagnostics.azurewebsites.net/health

# SSH into container (if needed)
az webapp ssh --name intunediagnostics --resource-group $resourceGroup

# In SSH session, verify Node.js:
node --version  # Should show v22.x.x
npm --version   # Should show 10.x.x
```

### Step 8: Test MCP Server in Production

1. Sign in to: https://intunediagnostics.azurewebsites.net
2. Navigate to a diagnostic scenario
3. Run a query that uses the Kusto MCP server
4. Check logs - should show MCP initialization succeeding:
   ```
   [INFO] services.kusto_mcp_service: Kusto MCP service initialized
   ```

## 🔍 Troubleshooting

### Container won't start

```bash
# Check logs
az webapp log tail --name intunediagnostics --resource-group $resourceGroup

# Common fixes:
# - Ensure WEBSITES_PORT=8000 is set
# - Verify container image is accessible
# - Check environment variables are set
```

### Node.js still not found

```bash
# SSH into container
az webapp ssh --name intunediagnostics --resource-group $resourceGroup

# Verify Node.js
node --version
which node
which npm

# If missing, check Dockerfile build logs on GitHub Actions
```

### GitHub Actions fails

- Check: Repository secrets are set correctly
- Check: Workflow file has correct resource group name
- Check: Azure service principal has permissions
- View logs: https://github.com/MartijnvanPraag/intune-diagnostics/actions

## 📚 Documentation Reference

- **Quick Start:** `DOCKER_QUICK_REF.md`
- **Full Guide:** `docs/DOCKER_DEPLOYMENT.md`
- **Options Comparison:** `docs/DEPLOYMENT_OPTIONS.md`
- **Managed Identity:** `docs/MANAGED_IDENTITY_SETUP.md`

## ✅ Success Criteria

You'll know it's working when:

- [ ] Local Docker container runs without errors
- [ ] Node.js version shows v22.x.x in container
- [ ] Frontend loads at http://localhost:8000 (local)
- [ ] You can sign in with Microsoft account
- [ ] GitHub Actions deployment completes successfully
- [ ] Production app loads at https://intunediagnostics.azurewebsites.net
- [ ] Container logs show MCP service initializing
- [ ] Kusto queries work in diagnostic scenarios
- [ ] No "[Errno 2] No such file or directory" errors

## 🎉 After Successful Deployment

```bash
# Merge to main branch
git checkout main
git merge azure-app-service-deployment
git push origin main

# Celebrate! 🎊
```

## 📞 Need Help?

If you run into issues:

1. Check container logs: `az webapp log tail --name intunediagnostics --resource-group $resourceGroup`
2. Review GitHub Actions logs: https://github.com/MartijnvanPraag/intune-diagnostics/actions
3. Test locally first: `docker-compose up -d && docker-compose logs -f`
4. Verify Node.js in container: `docker-compose exec app node --version`

---

**Current Status:** ✅ All Docker files created and committed
**Next Step:** Test locally with `docker-compose up -d`
