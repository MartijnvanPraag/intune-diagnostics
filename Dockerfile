# Multi-stage Dockerfile for Intune Diagnostics
# Includes Python 3.11 + Node.js 22 LTS for FastAPI backend + React frontend + Kusto MCP server

# ============================================
# Stage 1: Build Frontend (React + Vite)
# ============================================
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install frontend dependencies
RUN npm ci

# Copy frontend source code
COPY frontend/ ./

# Build frontend for production
RUN npm run build

# ============================================
# Stage 2: Python + Node.js Runtime
# ============================================
FROM python:3.11-slim

# Install Node.js 22 LTS in the Python container
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN python --version && node --version && npm --version

# Set working directory
WORKDIR /app

# Install uv for Python dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy Python dependency files
COPY pyproject.toml uv.lock* ./

# Create virtual environment and install Python dependencies
ENV UV_SYSTEM_PYTHON=1
RUN uv pip install --system -r pyproject.toml

# Copy backend source code
COPY backend/ ./backend/

# Copy frontend build from previous stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Install global Node.js packages needed for MCP server
# The Kusto MCP server will be installed on-demand via npx
RUN npm install -g npm@latest

# Create directory for MCP server cache (npx downloads packages here)
RUN mkdir -p /root/.npm

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8000

# Azure App Service expects the app to listen on $PORT
# Default to 8000 for local Docker runs
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Startup command
# Use gunicorn with uvicorn workers for production
CMD cd backend && \
    gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT}" \
    --timeout 600 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
