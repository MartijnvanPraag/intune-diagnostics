#!/bin/bash
# Build script for Azure deployment

set -e

echo "🏗️  Building Intune Diagnostics Application..."

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm ci

# Build frontend
echo "🔨 Building frontend..."
npm run build

# Move back to root
cd ..

echo "✅ Build completed successfully!"
echo "📁 Frontend built to: frontend/dist"
