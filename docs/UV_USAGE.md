# Using UV with Intune Diagnostics

## Important: Always Use UV

This project uses **UV** as the package manager. All Python commands MUST be run with `uv run` to ensure the correct virtual environment is used.

## Why UV?

UV manages the virtual environment in `.venv/` and ensures all packages (including pre-release packages like `agent-framework`) are properly installed and accessible.

## Correct Usage

### ✅ DO (Correct)
```powershell
# Run the backend server
uv run uvicorn backend.main:app --reload

# Run Python scripts
uv run python backend/services/agent_framework_service.py

# Run tests
uv run pytest

# Install new packages
uv add package-name
uv sync
```

### ❌ DON'T (Incorrect)
```powershell
# This uses system Python, NOT the virtual environment!
python backend/main.py  # ❌ WRONG

# This won't find packages installed by UV
python -c "import agent_framework"  # ❌ WRONG
```

## Why System Python Doesn't Work

When you run `python` directly, it uses the system Python installation (e.g., `C:\Program Files\Python313`), which doesn't have access to the packages UV installed in `.venv/`.

When you run `uv run python`, UV activates the virtual environment first, making all packages available.

## Package Installation Status

The following Agent Framework packages are installed and working:
- ✅ `agent-framework` 1.0.0b251001
- ✅ `agent-framework-core` 1.0.0b251001
- ✅ `agent-framework-azure-ai` 1.0.0b251001
- ✅ `agent-framework-a2a` 1.0.0b251001
- Plus 10 more agent-framework packages

## Running the Application

### Backend Server
```powershell
cd C:\dev\intune-diagnostics
uv run uvicorn backend.main:app --reload --port 8000
```

### Frontend Development Server
```powershell
cd C:\dev\intune-diagnostics\frontend
npm run dev
```

## Testing Agent Framework Imports

```powershell
# This should work perfectly
uv run python -c "from agent_framework import ChatAgent; from agent_framework.azure import AzureOpenAIChatClient; print('SUCCESS!')"
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'agent_framework'"

This error means you're using system Python instead of UV. Always prefix with `uv run`.

### Reinstall Packages

If packages seem missing:
```powershell
uv sync --prerelease=allow
```

### Check Installed Packages

```powershell
uv pip list | Select-String "agent"
```

## VS Code Configuration

If running from VS Code's integrated terminal or debugger, ensure you're using the UV virtual environment:

1. Open Command Palette (Ctrl+Shift+P)
2. Search: "Python: Select Interpreter"
3. Choose: `.venv\Scripts\python.exe`

Or better yet, configure VS Code to always use UV:

**`.vscode/settings.json`:**
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
  "terminal.integrated.env.windows": {
    "VIRTUAL_ENV": "${workspaceFolder}/.venv"
  }
}
```

## Pre-release Packages

Agent Framework is a pre-release package (version 1.0.0b251001). The `pyproject.toml` is configured to allow pre-releases:

```toml
[tool.uv]
prerelease = "allow"
```

This ensures UV can install beta versions of Agent Framework.
