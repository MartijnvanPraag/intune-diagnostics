# Docker Deployment Guide

This guide covers deploying the Intune Diagnostics application using Docker, which supports both Python (FastAPI) and Node.js (Kusto MCP server) in a single container.

## Overview

The application uses a multi-stage Dockerfile that:
- ✅ Builds the React frontend (Vite)
- ✅ Installs Python 3.11 for FastAPI backend
- ✅ Installs Node.js 22 LTS for Kusto MCP server
- ✅ Serves everything from a single container

## Prerequisites

- Docker installed locally (for testing)
- Azure CLI (for Azure deployment)
- GitHub account (for automated deployments)

## Local Development with Docker

### Build the Docker image

```bash
docker build -t intune-diagnostics:latest .
```

### Run locally with Docker

```bash
docker run -p 8000:8000 \
  -e AZURE_CLIENT_ID=fbadc585-90b3-48ab-8052-c1fcc32ce3fe \
  -e AZURE_TENANT_ID=72f988bf-86f1-41af-91ab-2d7cd011db47 \
  -e AZURE_OPENAI_ENDPOINT=your-openai-endpoint \
  -e AZURE_OPENAI_DEPLOYMENT=your-deployment \
  intune-diagnostics:latest
```

### Or use Docker Compose

```bash
# Create .env file with your Azure settings
cp .env.example .env

# Start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

Access the app at: http://localhost:8000

## Azure App Service Deployment (Container)

### Option 1: GitHub Actions (Recommended)

The workflow file `.github/workflows/azure-deploy-docker.yml` automatically:
1. Builds the Docker image
2. Pushes to GitHub Container Registry (ghcr.io)
3. Deploys to Azure App Service

**Setup Steps:**

1. **Create Azure Service Principal** (one-time setup):

```bash
az ad sp create-for-rbac \
  --name "intune-diagnostics-deployment" \
  --role contributor \
  --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group} \
  --sdk-auth
```

Copy the JSON output.

2. **Add GitHub Secrets**:

Go to: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

- `AZURE_CREDENTIALS`: Paste the JSON from step 1
- `AZUREAPPSERVICE_PUBLISHPROFILE`: (Optional, only if using publish profile method)

3. **Update workflow file**:

Edit `.github/workflows/azure-deploy-docker.yml`:

```yaml
# Line 87: Replace <your-resource-group> with your actual resource group name
--resource-group your-resource-group-name
```

4. **Enable container deployment in Azure**:

```bash
# Get your resource group name
az webapp show --name intunediagnostics --query resourceGroup -o tsv

# Configure the web app to use containers
az webapp config container set \
  --name intunediagnostics \
  --resource-group <your-resource-group> \
  --docker-custom-image-name ghcr.io/martijnvanpraag/intune-diagnostics:latest \
  --docker-registry-server-url https://ghcr.io
```

5. **Configure Azure App Settings**:

```bash
az webapp config appsettings set \
  --name intunediagnostics \
  --resource-group <your-resource-group> \
  --settings \
    AZURE_CLIENT_ID=fbadc585-90b3-48ab-8052-c1fcc32ce3fe \
    AZURE_TENANT_ID=72f988bf-86f1-41af-91ab-2d7cd011db47 \
    AZURE_OPENAI_ENDPOINT=<your-endpoint> \
    AZURE_OPENAI_DEPLOYMENT=<your-deployment> \
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<your-embedding-deployment> \
    WEBSITES_PORT=8000
```

6. **Push to trigger deployment**:

```bash
git add .
git commit -m "Enable Docker deployment"
git push origin azure-app-service-deployment
```

### Option 2: Manual Deployment

```bash
# Build the image
docker build -t intune-diagnostics:latest .

# Tag for Azure Container Registry (if using ACR)
docker tag intune-diagnostics:latest <your-acr>.azurecr.io/intune-diagnostics:latest

# Login to ACR
az acr login --name <your-acr>

# Push to ACR
docker push <your-acr>.azurecr.io/intune-diagnostics:latest

# Deploy to App Service
az webapp config container set \
  --name intunediagnostics \
  --resource-group <your-resource-group> \
  --docker-custom-image-name <your-acr>.azurecr.io/intune-diagnostics:latest

# Restart the app
az webapp restart --name intunediagnostics --resource-group <your-resource-group>
```

## Enable Managed Identity

After deploying with Docker, enable Managed Identity for AI services:

```bash
# Enable system-assigned Managed Identity
az webapp identity assign \
  --name intunediagnostics \
  --resource-group <your-resource-group>

# Copy the principalId from the output

# Grant Azure OpenAI access
az role assignment create \
  --assignee <principal-id> \
  --role "Cognitive Services OpenAI User" \
  --scope /subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.CognitiveServices/accounts/{openai-account}
```

## Verify Deployment

### Check container logs

```bash
az webapp log tail --name intunediagnostics --resource-group <your-resource-group>
```

### Test the application

```bash
# Health check
curl https://intunediagnostics.azurewebsites.net/health

# API status
curl https://intunediagnostics.azurewebsites.net/api/health
```

### Check Docker container status

```bash
az webapp show \
  --name intunediagnostics \
  --resource-group <your-resource-group> \
  --query state
```

## Troubleshooting

### Container won't start

Check the logs:
```bash
az webapp log tail --name intunediagnostics --resource-group <your-resource-group>
```

Common issues:
- ❌ **Port mismatch**: Ensure `WEBSITES_PORT=8000` is set in App Settings
- ❌ **Missing environment variables**: Check Azure App Settings
- ❌ **Image not found**: Verify container registry authentication

### Node.js not found

The Dockerfile installs Node.js 22 LTS. Verify with:
```bash
az webapp ssh --name intunediagnostics --resource-group <your-resource-group>
# Then in the SSH session:
node --version
npm --version
```

### MCP server fails

Check that `npx` can access the MCP package:
```bash
# In the SSH session
npx @mcp-apps/kusto-mcp-server --version
```

## Comparison: Docker vs. Oryx (Code Deploy)

| Feature | Docker (New) | Oryx (Current) |
|---------|-------------|----------------|
| Node.js Support | ✅ Yes (Node.js 22) | ❌ No (Python runtime only) |
| MCP Server | ✅ Works | ❌ Fails (no Node.js) |
| Build Time | Slower (builds image) | Faster (Oryx auto-build) |
| Portability | ✅ Runs anywhere | Azure-specific |
| Control | Full control | Limited |
| Debugging | Easier (run locally) | Harder |

## Recommendation

**Use Docker deployment** because:
1. ✅ Kusto MCP server works (Node.js available)
2. ✅ Same environment locally and in production
3. ✅ Full control over runtime
4. ✅ Easier debugging and testing

## Next Steps

After successful Docker deployment:
1. ✅ Enable Managed Identity (see above)
2. ✅ Test AI agent scenarios
3. ✅ Verify Kusto MCP queries work
4. ✅ Monitor container logs
5. ✅ Merge to main branch

## Resources

- [Azure App Service Container Deployment](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)
- [Docker Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
