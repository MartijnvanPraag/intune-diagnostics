# Azure App Service Configuration

## Environment Variables

Set these in Azure App Service > Configuration > Application Settings:

### Required
- `ALLOWED_ORIGINS`: Your production domain (e.g., `https://intunediagnostics.azurewebsites.net`)
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key (or use Managed Identity)
- `AZURE_OPENAI_DEPLOYMENT`: Your model deployment name
- `AZURE_OPENAI_API_VERSION`: API version (e.g., `2024-02-15-preview`)

### Optional
- `DATABASE_URL`: Path to SQLite database or connection string for Azure SQL
- `LOG_LEVEL`: Logging level (default: INFO)

## App Service Configuration

### General Settings
- **Stack**: Python 3.11
- **Startup Command**: `bash startup.sh`
- **Always On**: Enabled (recommended)
- **ARR Affinity**: Disabled (for better load balancing)

### Path Mappings
If using persistent storage for SQLite:
- Virtual Path: `/home/data`
- Physical Path: `/home/site/data`
- Type: Azure Storage

## Deployment Steps

1. **Create Azure App Service**
   ```bash
   az webapp create \
     --resource-group <your-resource-group> \
     --plan <your-app-service-plan> \
     --name intunediagnostics \
     --runtime "PYTHON:3.11"
   ```

2. **Configure Application Settings**
   ```bash
   az webapp config appsettings set \
     --resource-group <your-resource-group> \
     --name intunediagnostics \
     --settings \
       ALLOWED_ORIGINS="https://intunediagnostics.azurewebsites.net" \
       AZURE_OPENAI_ENDPOINT="<your-endpoint>" \
       AZURE_OPENAI_DEPLOYMENT="<your-deployment>"
   ```

3. **Set Startup Command**
   ```bash
   az webapp config set \
     --resource-group <your-resource-group> \
     --name intunediagnostics \
     --startup-file "startup.sh"
   ```

4. **Enable Managed Identity (Optional)**
   ```bash
   az webapp identity assign \
     --resource-group <your-resource-group> \
     --name intunediagnostics
   ```

5. **Get Publish Profile for GitHub Actions**
   ```bash
   az webapp deployment list-publishing-profiles \
     --resource-group <your-resource-group> \
     --name intunediagnostics \
     --xml
   ```
   
   Add this to GitHub Secrets as `AZUREAPPSERVICE_PUBLISHPROFILE`

## Local Testing

Test the production build locally:

```bash
# Build frontend
npm run build:all

# Start backend serving frontend
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000

## Database Considerations

### SQLite (Current)
- Works for development and small deployments
- Requires persistent storage configuration in Azure
- Not recommended for high-traffic production

### Migration to Azure SQL (Recommended for Production)
1. Create Azure SQL Database
2. Update connection string
3. Run migrations with Alembic
4. Update `backend/dependencies.py` with new connection string

## Troubleshooting

### View Logs
```bash
az webapp log tail \
  --resource-group <your-resource-group> \
  --name intunediagnostics
```

### SSH into App Service
```bash
az webapp ssh \
  --resource-group <your-resource-group> \
  --name intunediagnostics
```

### Check Application Insights
Enable Application Insights for monitoring and diagnostics.
