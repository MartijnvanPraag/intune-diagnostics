# Intune Diagnostics Web App

A modern web application that uses Agentic AI to interface with Kusto MCP server for retrieving Intune diagnostics information. Built with FastAPI backend, React frontend, and Windows 11 styling.

## Features

- 🤖 **Agentic AI**: Powered by Autogen with Magentic One orchestrator
- 🔍 **Kusto Integration**: Direct access to Intune diagnostics data via MCP server
- 🔐 **Azure Authentication**: Interactive authentication using DefaultAzureCredential
- 📊 **Table Display**: Rich table display for diagnostic data
- ⚙️ **Configurable Models**: User-configurable Azure AI model settings
- 🏢 **Database-Backed**: All settings stored in database (no local config files)
- 🎨 **Modern UI**: Windows 11-inspired design with Fluent styling

## Architecture

```
├── backend/          # Python FastAPI backend with UV package management
│   ├── models/       # SQLAlchemy database models and Pydantic schemas
│   ├── routers/      # API route handlers
│   └── services/     # Business logic (auth, agents, MCP)
├── frontend/         # React frontend with TypeScript
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   ├── pages/       # Page components
│   │   ├── services/    # API service layers
│   │   └── contexts/    # React contexts
└── instructions.md   # Kusto queries and diagnostic procedures
```

## Prerequisites

- **Python 3.11+** with [UV package manager](https://astral.sh/uv/)
- **Node.js 18+** with npm
- **PostgreSQL** database
- **Azure CLI** (for authentication)

## Quick Start

1. **Clone and setup:**
   ```bash
   cd intune-diagnostics
   python setup.py
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your database connection details
   ```

3. **Start development servers:**
   ```bash
   npm run dev
   ```

   This starts both:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000

## Configuration

### Database Setup

Create a PostgreSQL database and update your `.env` file:

```env
DATABASE_URL=postgresql+asyncpg://username:password@localhost/intune_diagnostics
```

### Azure Authentication

The app uses `DefaultAzureCredential` for authentication. Ensure you're logged in via:

```bash
az login
```

### Kusto (Azure Data Explorer) Integration via MCP

The backend now auto-spawns the official Kusto MCP server (`npx -y @mcp-apps/kusto-mcp-server`) on first diagnostic query that needs Kusto data. No cluster / database credentials are stored in environment variables. Authentication and resource selection are handled interactively by the MCP server (browser/device sign-in flow) managed by the GitHub Copilot tooling.

Workflow:
1. First relevant query triggers process start (Node + npx required locally).
2. MCP server prompts (browser/device auth) – follow instructions once.
3. Tools exposed (executeQuery, getTableInfo, findTables, analyzeData) are invoked by the backend through JSON-RPC over stdio.

Security & Read-Only Guard:
The backend blocks KQL commands starting with: `.drop`, `.alter`, `.ingest`, `.delete`, `.set`, `.create`, `.append` before they reach MCP.

Requirements:
- Node.js 18+ in PATH
- Network access to your Azure Data Explorer cluster(s)

No additional .env entries are required for Kusto.

### Model Configuration

After authentication, configure your Azure AI models in the Settings page:

- **Azure Endpoint**: Your Azure OpenAI service endpoint
- **Deployment Name**: Name of your model deployment
- **Model Name**: The model identifier (e.g., gpt-4, gpt-3.5-turbo)
- **API Version**: Azure OpenAI API version (default: 2024-06-01)

## Usage

### For Support Engineers

1. **Authenticate** with your Microsoft account
2. **Configure Models** in Settings page with your Azure AI credentials
3. **Run Diagnostics** by providing device IDs and selecting query types
4. **View Results** in structured tables with AI-powered analysis

### Available Diagnostic Queries

- **Device Details**: Comprehensive device information
- **Compliance Status**: Device compliance changes (last 10 days)
- **Policy Status**: Policy and setting status
- **User Lookup**: Associated user IDs
- **Tenant Information**: Tenant details and flighting tags
- **Effective Groups**: Group memberships and assignments
- **Applications**: App deployment status
- **MAM Policy**: Mobile Application Management policies

## Development

### Backend Development

```bash
# Install dependencies
uv sync

# Run backend only
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run database migrations (when implemented)
# uv run alembic upgrade head
```

### Frontend Development

```bash
# Install dependencies
cd frontend && npm install

# Run frontend only
npm run dev

# Build for production
npm run build
```

## Technical Stack

### Backend
- **FastAPI**: Modern Python web framework
- **SQLAlchemy**: ORM with async support
- **PostgreSQL**: Database
- **Azure Identity**: Authentication
- **Autogen**: Agentic AI framework
- **MCP**: Model Context Protocol for Kusto integration

### Frontend
- **React 18**: UI framework
- **TypeScript**: Type safety
- **Tailwind CSS**: Styling with Windows 11 theme
- **React Router**: Navigation
- **Axios**: HTTP client
- **React Table**: Table components

## Security

- **No Local Secrets**: All authentication uses Azure's interactive flow
- **Database-Backed Settings**: No local configuration files
- **Secure Token Handling**: JWT tokens managed securely
- **CORS Protection**: Configured for development and production

## Troubleshooting

### Common Issues

1. **Authentication Fails**: Ensure you're logged in with `az login`
2. **Database Connection**: Verify PostgreSQL is running and connection string is correct
3. **MCP Connection**: Check Kusto MCP server configuration and permissions
4. **Port Conflicts**: Ensure ports 3000 and 8000 are available

### Logs

- Backend logs: Check uvicorn console output
- Frontend logs: Check browser developer console
- Agent logs: Check FastAPI application logs

## License

Internal Microsoft tool for Intune support engineering.