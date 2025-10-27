#!/bin/bash
# Azure App Service startup script

echo "Starting Intune Diagnostics Application..."

# Navigate to backend directory
cd /home/site/wwwroot/backend

# Activate virtual environment (created by Oryx during deployment)
source /home/site/wwwroot/antenv/bin/activate

# Run database migrations if needed
# python -m alembic upgrade head

# Start the FastAPI application
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 600
