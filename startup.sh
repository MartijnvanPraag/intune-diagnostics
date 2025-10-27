#!/bin/bash
# Azure App Service startup script

echo "Starting Intune Diagnostics Application..."

# Azure provides the PORT environment variable (default is 8000 but can vary)
PORT="${PORT:-8000}"
echo "Using port: $PORT"

# Navigate to backend directory
cd /home/site/wwwroot/backend

# Activate virtual environment (created by Oryx during deployment)
if [ -d "/home/site/wwwroot/antenv" ]; then
    source /home/site/wwwroot/antenv/bin/activate
    echo "Virtual environment activated"
else
    echo "Warning: Virtual environment not found at /home/site/wwwroot/antenv"
fi

# Run database migrations if needed
# python -m alembic upgrade head

# Start the FastAPI application on the port Azure expects
echo "Starting Gunicorn on 0.0.0.0:$PORT"
gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:$PORT" \
    --timeout 600 \
    --access-logfile - \
    --error-logfile -
