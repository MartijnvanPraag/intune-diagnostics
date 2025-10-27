# 🚀 Azure App Service Deployment Guide

This branch (`azure-app-service-deployment`) contains all the necessary configuration to deploy your Intune Diagnostics application to Azure App Service.

## 📋 What Changed

### Backend Changes
- ✅ Added static file serving for React frontend
- ✅ Updated CORS to use environment variables
- ✅ Added SPA routing support (serves `index.html` for all routes)
- ✅ Changed health check to `/api/health`
- ✅ Added `gunicorn` for production server

### Deployment Files
- ✅ `startup.sh` - Azure App Service startup script
- ✅ `build.sh` - Build script for frontend
- ✅ `.github/workflows/azure-deploy.yml` - GitHub Actions CI/CD
- ✅ `AZURE_DEPLOYMENT.md` - Detailed deployment instructions

### Configuration
- ✅ Updated `.env.example` with Azure-specific variables
- ✅ Updated `package.json` with build commands
- ✅ Updated `pyproject.toml` with gunicorn dependency
- ✅ Updated `vite.config.ts` for production builds

## 🎯 Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Test Locally (Production Mode)

```bash
# Build frontend
npm run build:all

# Start backend (will serve frontend from /frontend/dist)
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000

### 3. Deploy to Azure

#### Option A: Using GitHub Actions (Recommended)

1. **Create Azure App Service**
   - Go to Azure Portal
   - Create a new App Service
   - Choose Python 3.11 runtime
   - Note the app name (e.g., `intunediagnostics`)

2. **Configure App Service**
   - Set startup command: `bash startup.sh`
   - Enable "Always On"
   - Disable "ARR Affinity"

3. **Get Publish Profile**
   - In App Service, go to "Deployment Center"
   - Click "Manage publish profile"
   - Download the publish profile XML

4. **Add GitHub Secret**
   - Go to your GitHub repository
   - Settings > Secrets and variables > Actions
   - Click "New repository secret"
   - Name: `AZUREAPPSERVICE_PUBLISHPROFILE`
   - Value: Paste the entire publish profile XML

5. **Update Workflow File**
   - Edit `.github/workflows/azure-deploy.yml`
   - Change `app-name: 'intunediagnostics'` to your app name

6. **Push to Trigger Deployment**
   ```bash
   git add .
   git commit -m "Configure Azure deployment"
   git push origin azure-app-service-deployment
   ```

#### Option B: Manual Deployment

```bash
# Build frontend
npm run build:all

# Deploy using Azure CLI
az webapp up \
  --name intunediagnostics \
  --resource-group <your-resource-group> \
  --runtime "PYTHON:3.11" \
  --sku B1
```

### 4. Configure Environment Variables

In Azure Portal > App Service > Configuration > Application Settings:

**Required:**
```
ALLOWED_ORIGINS=https://your-app.azurewebsites.net
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

**Optional:**
```
DATABASE_URL=sqlite+aiosqlite:///./intune_diagnostics.db
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## 🔍 Testing the Deployment

1. Visit your app: `https://your-app.azurewebsites.net`
2. Check API health: `https://your-app.azurewebsites.net/api/health`
3. View logs:
   ```bash
   az webapp log tail --name intunediagnostics --resource-group <your-rg>
   ```

## 🔄 Reverting Changes

If you need to go back to the original setup:

```bash
# Switch back to main branch
git checkout main

# Delete this branch (optional)
git branch -D azure-app-service-deployment
git push origin --delete azure-app-service-deployment
```

## 📊 Architecture

```
┌─────────────────────────────────────┐
│     Azure App Service (Linux)       │
│                                     │
│  ┌──────────────────────────────┐  │
│  │   Gunicorn + Uvicorn         │  │
│  │   (FastAPI Backend)          │  │
│  │   Port: 8000                 │  │
│  └──────────────────────────────┘  │
│              │                      │
│              ▼                      │
│  ┌──────────────────────────────┐  │
│  │   Static Files               │  │
│  │   (React Frontend - Built)   │  │
│  │   /frontend/dist/            │  │
│  └──────────────────────────────┘  │
│                                     │
└─────────────────────────────────────┘
```

**Request Flow:**
- `/` → Serves React app (`index.html`)
- `/api/*` → FastAPI routes
- `/assets/*` → Static assets (JS, CSS, images)
- All other routes → React app (SPA routing)

## 🛠️ Troubleshooting

### Frontend not loading
- Check that frontend was built: `ls -la frontend/dist`
- Rebuild: `npm run build:all`

### API errors
- Check environment variables in Azure Portal
- View logs: `az webapp log tail`

### Database issues
- SQLite works but needs persistent storage
- For production, consider migrating to Azure SQL Database

### CORS errors
- Ensure `ALLOWED_ORIGINS` includes your Azure URL
- Check that it doesn't have trailing slashes

## 📚 Additional Resources

- [Azure App Service Documentation](https://docs.microsoft.com/en-us/azure/app-service/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [GitHub Actions for Azure](https://github.com/Azure/actions)

## 🎉 Next Steps

After successful deployment:

1. **Set up custom domain** (optional)
2. **Enable Application Insights** for monitoring
3. **Configure auto-scaling** rules
4. **Set up staging slots** for zero-downtime deployments
5. **Consider migrating to Azure SQL** for better scalability
6. **Add Redis cache** for session management
7. **Enable Managed Identity** for secure Azure service access

---

**Need help?** See `AZURE_DEPLOYMENT.md` for detailed instructions.
