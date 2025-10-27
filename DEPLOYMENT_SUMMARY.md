# ✅ Azure App Service Deployment Setup - Complete!

## 🎯 What Was Done

Your application is now ready for Azure App Service deployment! All changes have been committed to the `azure-app-service-deployment` branch.

### Files Created/Modified

#### New Files:
1. **`.github/workflows/azure-deploy.yml`** - GitHub Actions CI/CD workflow
2. **`startup.sh`** - Azure App Service startup script
3. **`build.sh`** - Frontend build script
4. **`AZURE_DEPLOYMENT.md`** - Detailed Azure configuration guide
5. **`README_DEPLOYMENT.md`** - Complete deployment guide

#### Modified Files:
1. **`backend/main.py`**
   - Added static file serving for React frontend
   - Added SPA routing (all non-API routes serve React app)
   - Updated CORS to use environment variables
   - Changed root endpoint to `/api`

2. **`pyproject.toml`**
   - Added `gunicorn` for production server

3. **`package.json`**
   - Added `build:all` script for frontend build
   - Added `start:prod` script for production server

4. **`.env.example`**
   - Added Azure OpenAI configuration
   - Added CORS configuration
   - Added production environment variables

5. **`frontend/vite.config.ts`**
   - Configured for production builds
   - Disabled sourcemaps
   - Set correct base path

## 🚀 Next Steps

### 1. Test Locally (Optional but Recommended)

```powershell
# Build frontend
npm run build:all

# Start backend (will serve frontend)
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Visit: http://localhost:8000
```

### 2. Create Azure App Service

```powershell
# Option A: Using Azure Portal
# 1. Go to https://portal.azure.com
# 2. Create > Web App
# 3. Choose Python 3.11 runtime
# 4. Name it (e.g., "intunediagnostics")
# 5. Choose your subscription and resource group

# Option B: Using Azure CLI
az webapp create `
  --resource-group <your-rg> `
  --plan <your-plan> `
  --name intunediagnostics `
  --runtime "PYTHON:3.11"
```

### 3. Configure App Service

```powershell
# Set startup command
az webapp config set `
  --resource-group <your-rg> `
  --name intunediagnostics `
  --startup-file "startup.sh"

# Add environment variables
az webapp config appsettings set `
  --resource-group <your-rg> `
  --name intunediagnostics `
  --settings `
    ALLOWED_ORIGINS="https://intunediagnostics.azurewebsites.net" `
    AZURE_OPENAI_ENDPOINT="<your-endpoint>" `
    AZURE_OPENAI_API_KEY="<your-key>" `
    AZURE_OPENAI_DEPLOYMENT="gpt-4" `
    AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

### 4. Set Up GitHub Actions (Automated Deployment)

1. **Get publish profile:**
   ```powershell
   az webapp deployment list-publishing-profiles `
     --resource-group <your-rg> `
     --name intunediagnostics `
     --xml > publish-profile.xml
   ```

2. **Add to GitHub Secrets:**
   - Go to: https://github.com/MartijnvanPraag/intune-diagnostics/settings/secrets/actions
   - Click "New repository secret"
   - Name: `AZUREAPPSERVICE_PUBLISHPROFILE`
   - Value: Contents of `publish-profile.xml`

3. **Update workflow file:**
   - Edit `.github/workflows/azure-deploy.yml`
   - Line 99: Change `app-name: 'intunediagnostics'` to your app name

4. **Push to deploy:**
   ```powershell
   git push origin azure-app-service-deployment
   ```
   
   The workflow will automatically build and deploy!

### 5. Verify Deployment

Visit your app:
- **Homepage:** https://your-app.azurewebsites.net
- **API Health:** https://your-app.azurewebsites.net/api/health
- **API Docs:** https://your-app.azurewebsites.net/docs

## 📊 Architecture Overview

```
User Request
    ↓
Azure App Service (Linux)
    ↓
Gunicorn (4 workers)
    ↓
Uvicorn Workers (FastAPI)
    ↓
┌─────────────────────┬──────────────────┐
│   /api/*           │   /* (other)     │
│   FastAPI Routes   │   React SPA      │
│   JSON API         │   index.html     │
└─────────────────────┴──────────────────┘
```

## 🔄 How to Revert

If you need to go back to the original setup:

```powershell
# Switch back to main
git checkout main

# Optionally delete the deployment branch
git branch -D azure-app-service-deployment
git push origin --delete azure-app-service-deployment
```

Your main branch is completely unchanged!

## 📚 Documentation

- **Quick Start:** `README_DEPLOYMENT.md` (this file)
- **Detailed Guide:** `AZURE_DEPLOYMENT.md`
- **GitHub Actions:** `.github/workflows/azure-deploy.yml`

## 🎯 Key Features

✅ **Single App Service** - Both frontend and backend in one app
✅ **GitHub Actions CI/CD** - Automated deployment on push
✅ **SPA Routing** - React Router works correctly
✅ **Environment-based Config** - Easy to manage across environments
✅ **Production-ready** - Gunicorn + Uvicorn for performance
✅ **Easy Rollback** - Separate branch for safety

## 💡 Tips

1. **Start with B1 tier** ($13/month) - good for testing
2. **Enable "Always On"** in App Service settings
3. **Use Managed Identity** instead of API keys (more secure)
4. **Add Application Insights** for monitoring
5. **Consider Azure SQL** instead of SQLite for production

## ❓ Need Help?

- View deployment logs: `az webapp log tail --name intunediagnostics --resource-group <rg>`
- SSH into app: `az webapp ssh --name intunediagnostics --resource-group <rg>`
- Check GitHub Actions: https://github.com/MartijnvanPraag/intune-diagnostics/actions

---

**Branch:** `azure-app-service-deployment`  
**Commit:** 10f78b4  
**Status:** ✅ Ready to deploy
