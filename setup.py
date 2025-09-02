#!/usr/bin/env python3
"""
Setup script for Intune Diagnostics Web App
This script helps initialize the project and install dependencies.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

def run_command(command: str, cwd: str = None, shell: bool = True):
    """Run a command and return the result"""
    try:
        result = subprocess.run(
            command, 
            shell=shell, 
            cwd=cwd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        print(f"SUCCESS: {command}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {command}")
        print(f"Error: {e.stderr}")
        return None

def check_prerequisites():
    """Check if required tools are installed"""
    print("Checking prerequisites...")
    
    # Check if UV is installed
    uv_result = run_command("uv --version")
    if not uv_result:
        print("ERROR: UV is not installed. Please install UV first:")
        print("   curl -LsSf https://astral.sh/uv/install.sh | sh")
        return False
    
    # Check if Node.js is installed
    node_result = run_command("node --version")
    if not node_result:
        print("ERROR: Node.js is not installed. Please install Node.js first:")
        print("   https://nodejs.org/")
        return False
    
    # Check if npm is installed
    npm_result = run_command("npm --version")
    if not npm_result:
        print("ERROR: npm is not installed. Please install npm first.")
        return False
    
    print("SUCCESS: All prerequisites are installed!")
    return True

def setup_backend():
    """Set up Python backend with UV"""
    print("\nSetting up Python backend...")
    
    backend_path = Path("backend")
    if not backend_path.exists():
        print("ERROR: Backend directory not found")
        return False
    
    # Install Python dependencies with UV
    result = run_command("uv sync", cwd=".")
    if not result:
        print("ERROR: Failed to install Python dependencies")
        return False
    
    print("SUCCESS: Python backend setup complete!")
    return True

def setup_frontend():
    """Set up Node.js frontend"""
    print("\nSetting up Node.js frontend...")
    
    frontend_path = Path("frontend")
    if not frontend_path.exists():
        print("ERROR: Frontend directory not found")
        return False
    
    # Install Node.js dependencies
    result = run_command("npm install", cwd="frontend")
    if not result:
        print("ERROR: Failed to install Node.js dependencies")
        return False
    
    print("SUCCESS: Frontend setup complete!")
    return True

def setup_database():
    """Set up database (create if needed)"""
    print("\nDatabase setup...")
    print("Please ensure you have PostgreSQL installed and running.")
    print("Create a database named 'intune_diagnostics' or update the DATABASE_URL in your .env file.")
    
    # Copy .env.example to .env if it doesn't exist
    env_file = Path(".env")
    if not env_file.exists():
        env_example = Path(".env.example")
        if env_example.exists():
            env_file.write_text(env_example.read_text())
            print("SUCCESS: Created .env file from .env.example")
        else:
            print("WARNING: Please create a .env file with your database configuration")
    
    return True

def main():
    """Main setup function"""
    print("Setting up Intune Diagnostics Web App")
    print("=" * 50)
    
    if not check_prerequisites():
        sys.exit(1)
    
    if not setup_backend():
        sys.exit(1)
    
    if not setup_frontend():
        sys.exit(1)
    
    if not setup_database():
        sys.exit(1)
    
    print("\nSetup complete!")
    print("\nNext steps:")
    print("1. Configure your .env file with database credentials")
    print("2. Start the development server:")
    print("   npm run dev")
    print("\nThe app will be available at:")
    print("   Frontend: http://localhost:3000")
    print("   Backend API: http://localhost:8000")

if __name__ == "__main__":
    main()