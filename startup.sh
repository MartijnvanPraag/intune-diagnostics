#!/bin/bash
# Azure App Service startup script for Oryx deployment

echo "Starting Intune Diagnostics Application..."

# Azure provides the PORT environment variable (default is 8000 but can vary)
PORT="${PORT:-8000}"
echo "Using port: $PORT"

# Oryx sets PYTHONPATH to include the app directory
# The virtual environment is already activated by Oryx's wrapper script
echo "Current directory: $(pwd)"
echo "PYTHONPATH: $PYTHONPATH"

# Change to backend directory so relative imports work
cd backend || { echo "Error: backend directory not found"; exit 1; }
echo "Changed to directory: $(pwd)"

# Run database migrations if needed
# python -m alembic upgrade head

# Start the FastAPI application on the port Azure expects
# Use main:app since we're now in the backend directory
echo "Starting Gunicorn on 0.0.0.0:$PORT"
exec gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:$PORT" \
    --timeout 600 \
    --access-logfile - \
    --error-logfile -
    --access-logfile - \
    --error-logfile -
