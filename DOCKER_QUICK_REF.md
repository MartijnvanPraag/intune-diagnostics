# 🐳 Docker Quick Reference

## Build and Run Locally

```bash
# Build the image
docker build -t intune-diagnostics:latest .

# Run the container
docker run -p 8000:8000 \
  -e AZURE_CLIENT_ID=fbadc585-90b3-48ab-8052-c1fcc32ce3fe \
  -e AZURE_TENANT_ID=72f988bf-86f1-41af-91ab-2d7cd011db47 \
  intune-diagnostics:latest

# Or use docker-compose
docker-compose up -d
docker-compose logs -f
docker-compose down
```

## What's Inside the Container?

✅ **Python 3.11** - FastAPI backend  
✅ **Node.js 22 LTS** - Kusto MCP server  
✅ **React Frontend** - Pre-built and served by FastAPI  
✅ **Gunicorn** - Production WSGI server  
✅ **All dependencies** - No manual setup needed  

## Deploy to Azure (GitHub Actions)

1. **One-time setup:**
   ```bash
   # Create service principal
   az ad sp create-for-rbac --name "intune-diagnostics" --sdk-auth
   # Copy JSON output → GitHub Secrets → AZURE_CREDENTIALS
   ```

2. **Configure Azure for containers:**
   ```bash
   az webapp config container set \
     --name intunediagnostics \
     --resource-group <your-rg> \
     --docker-custom-image-name ghcr.io/martijnvanpraag/intune-diagnostics:latest
   ```

3. **Push to deploy:**
   ```bash
   git push origin azure-app-service-deployment
   ```

## Enable Managed Identity

```bash
# Enable identity
az webapp identity assign --name intunediagnostics --resource-group <your-rg>

# Grant Azure OpenAI access
az role assignment create \
  --assignee <principal-id> \
  --role "Cognitive Services OpenAI User" \
  --scope <openai-resource-scope>
```

## Verify Everything Works

```bash
# Health check
curl https://intunediagnostics.azurewebsites.net/health

# Container logs
az webapp log tail --name intunediagnostics --resource-group <your-rg>

# SSH into container
az webapp ssh --name intunediagnostics --resource-group <your-rg>

# Check Node.js (should show v22.x.x)
node --version
```

## Why Docker?

| Before (Code Deploy) | After (Docker) |
|---------------------|----------------|
| ❌ No Node.js | ✅ Node.js 22 LTS |
| ❌ MCP server fails | ✅ MCP server works |
| ❌ Complex setup | ✅ Simple container |
| ❌ Azure-specific | ✅ Portable |

## Troubleshooting

**Container won't start:**
- Check: `WEBSITES_PORT=8000` in App Settings
- Check: Container logs with `az webapp log tail`

**Node.js not found:**
- SSH into container and verify: `node --version`
- Should show: `v22.x.x`

**MCP server fails:**
- Check logs for `npx @mcp-apps/kusto-mcp-server`
- Verify Node.js installation

## Files Created

- ✅ `Dockerfile` - Multi-stage build (Python + Node.js)
- ✅ `.dockerignore` - Build optimization
- ✅ `docker-compose.yml` - Local development
- ✅ `.github/workflows/azure-deploy-docker.yml` - CI/CD
- ✅ `docs/DOCKER_DEPLOYMENT.md` - Full guide
