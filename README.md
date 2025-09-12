# Intune Diagnostics Web App

A modern web application that uses Agentic AI to interface with Kusto MCP server for retrieving Intune diagnostics information. Built with FastAPI backend, React frontend, and Windows 11 styling.

## Features

- 🤖 **Agentic AI**: Powered by Autogen with Magentic One orchestrator
- 🔍 **Kusto Integration**: Direct access to Intune diagnostics data via MCP server
- 🔐 **Advanced Azure Authentication**: WAM broker-preferred authentication with sign-out/reauthentication support
- 📊 **Rich Data Display**: Interactive tables and chat interface for diagnostic data
- ⚙️ **Configurable Models**: User-configurable Azure AI model settings stored in database
- 🏢 **Database-Backed**: SQLite (development) / PostgreSQL (production) with comprehensive data models
- 🎨 **Modern UI**: Windows 11-inspired design with Fluent styling
- 💬 **Chat Interface**: Interactive chat sessions with conversation state management
- 🔄 **Force Reauthentication**: Support for clearing cached credentials and switching accounts

## Architecture

```
├── backend/          # Python FastAPI backend with UV package management
│   ├── models/       # SQLAlchemy database models and Pydantic schemas
│   │   ├── database.py      # User, ModelConfiguration, AgentConfiguration, ChatSession models
│   │   └── schemas.py       # Pydantic response/request schemas
│   ├── routers/      # API route handlers
│   │   ├── auth.py          # Authentication endpoints (login/logout)
│   │   ├── diagnostics.py   # Diagnostic query endpoints
│   │   └── settings.py      # Model configuration endpoints
│   └── services/     # Business logic
│       ├── auth_service.py      # WAM-preferred Azure authentication
│       ├── agent_service.py     # Autogen agent orchestration
│       └── kusto_mcp_service.py # MCP Kusto integration
├── frontend/         # React frontend with TypeScript
│   ├── src/
│   │   ├── components/  # Reusable UI components (DataTable, Navigation, etc.)
│   │   ├── pages/       # Page components (ChatPage, DiagnosticsPage, SettingsPage)
│   │   ├── services/    # API service layers
│   │   ├── contexts/    # React contexts (AuthContext)
│   │   └── types/       # TypeScript type definitions
└── instructions.md   # Kusto queries and diagnostic procedures
```

## Prerequisites

- **Python 3.11+** with [UV package manager](https://astral.sh/uv/)
- **Node.js 18+** with npm
- **Database**: SQLite (default) or PostgreSQL (production)
- **Azure Identity**: Modern authentication via WAM broker or DefaultAzureCredential
- **No Azure CLI required**: App uses interactive authentication flows

## Quick Start

1. **Clone and setup:**
   ```bash
   cd intune-diagnostics
   python setup.py
   ```

2. **Configure environment (optional):**
   ```bash
   cp .env.example .env
   # Edit .env if you want to customize database or other settings
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

**Default (SQLite)**: Works out of the box with no configuration.

**Production (PostgreSQL)**: Update your `.env` file:

```env
DATABASE_URL=postgresql+asyncpg://username:password@localhost/intune_diagnostics
```

Current database models include:
- **Users**: Azure user authentication and profile data
- **ModelConfiguration**: User-specific Azure AI model settings
- **AgentConfiguration**: AI agent system messages and configurations
- **DiagnosticSession**: Query execution history and results
- **ChatSession/ChatMessage**: Interactive chat conversations with state management

### Azure Authentication

The app uses **advanced Azure authentication** with the following features:

#### Primary Authentication Methods:
1. **WAM Broker** (Windows Authentication Manager) - Preferred
2. **Interactive Browser Credential** - Fallback
3. **Shared Token Cache** - For cached sessions

#### Authentication Features:
- ✅ **No Azure CLI dependency**: Uses direct Azure Identity library
- ✅ **Token caching**: Intelligent 2-minute safety buffer for token reuse
- ✅ **Sign-out support**: Complete token cache clearing on logout
- ✅ **Force reauthentication**: Option to clear cache and force fresh login
- ✅ **Multiple scopes**: Separate tokens for Microsoft Graph, Azure Cognitive Services, and Kusto
- ✅ **Account switching**: Full support for switching between different Azure accounts

#### Setup:
```bash
# No pre-authentication required - app handles interactive auth
# Just ensure you have access to your Azure tenant
```

#### Troubleshooting Authentication:
If you experience authentication issues:
1. Click "Sign Out" in the app
2. Try "Force New Login" on the login page
3. This clears all cached credentials and forces interactive authentication

### Kusto (Azure Data Explorer) Integration via MCP

The backend auto-spawns the official Kusto MCP server (`npx -y @mcp-apps/kusto-mcp-server`) on first diagnostic query. Authentication and resource selection are handled interactively.

**Workflow:**
1. First Kusto query triggers MCP server start (Node.js required)
2. MCP server prompts for authentication (browser/device flow)
3. Backend communicates with MCP via JSON-RPC over stdio
4. Results returned through structured API responses

**Security Features:**
- Read-only KQL enforcement (blocks destructive operations)
- No cluster credentials stored in environment
- Interactive authentication per session

**Requirements:**
- Node.js 18+ in PATH
- Network access to Azure Data Explorer clusters

### Model Configuration

After authentication, configure your Azure AI models in the **Settings page**:
## Usage

### For Support Engineers

1. **Authenticate** with your Microsoft account (no pre-setup required)
2. **Configure Models** in Settings page with your Azure AI service details
3. **Choose Interface**:
   - **Diagnostics Page**: Structured queries with device IDs and query types
   - **Chat Page**: Interactive AI conversation for complex troubleshooting
4. **View Results** in structured tables with AI-powered analysis
5. **Manage Sessions**: Chat history and diagnostic sessions are saved per user

### Available Diagnostic Queries

- **Device Details**: Comprehensive device information and enrollment status
- **Compliance Status**: Device compliance changes and policy evaluation (last 10 days)
- **Policy Status**: Configuration policies and setting deployment status
- **User Lookup**: Associated user IDs and account information
- **Tenant Information**: Tenant details, flighting tags, and environment info
- **Effective Groups**: Group memberships, assignments, and inheritance
- **Applications**: App deployment status, installation results, and dependencies
- **MAM Policy**: Mobile Application Management policies and compliance

### Chat Interface Features

- **Conversational AI**: Natural language queries for complex diagnostics
- **Context Retention**: Chat sessions maintain device/user context across messages
- **State Management**: Automatic tracking of current diagnostic focus
- **Clarification Handling**: AI can ask follow-up questions when needed
- **Rich Results**: Tables, summaries, and actionable insights

## Development

### Backend Development

```bash
# Install dependencies
uv sync

# Run backend only
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Database operations
# Note: Database tables are created automatically on first run
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

### Development Scripts

```bash
# Run both frontend and backend concurrently
npm run dev

# Install all dependencies (backend + frontend)
npm run install

# Backend only
npm run backend:dev
npm run backend:install

# Frontend only  
npm run frontend:dev
npm run frontend:install
```

## Technical Stack

### Backend
- **FastAPI**: Modern Python web framework with async support
- **SQLAlchemy 2.0**: Async ORM with declarative models
- **Database**: SQLite (development) / PostgreSQL (production)
- **Azure Identity**: Advanced authentication with WAM broker support
- **Autogen**: Agentic AI framework with Magentic One orchestrator
- **MCP**: Model Context Protocol for Kusto data integration
- **UV**: Fast Python package management

### Frontend
- **React 18**: Modern UI framework with hooks
- **TypeScript**: Full type safety throughout the application
- **Tailwind CSS**: Utility-first styling with custom Windows 11 theme
- **React Router**: Client-side navigation and routing
- **Axios**: HTTP client with interceptors and error handling
- **Context API**: State management for authentication and global state

### Key Dependencies
- **azure-identity**: Advanced Azure authentication flows
- **autogen-magentic-one**: Latest AI agent orchestration
- **mcp**: Model Context Protocol integration
- **aiosqlite**: Async SQLite support
- **concurrently**: Development server orchestration

## Security

- **Advanced Token Management**: WAM broker authentication with secure token caching
- **Session Isolation**: User data and settings completely isolated per Azure account
- **No Local Secrets**: All authentication uses Azure's interactive flows
- **Database Security**: Prepared statements and ORM protection against injection
- **CORS Protection**: Configured for development and production environments
- **Read-Only Kusto**: Automatic blocking of destructive KQL operations
- **Force Reauthentication**: Complete credential cache clearing for account switching

## Troubleshooting

### Authentication Issues

1. **Cached Credentials**: Click "Sign Out" → "Force New Login"
2. **WAM Broker Errors**: App automatically falls back to browser authentication
3. **Account Switching**: Use "Force New Login" to switch between Azure accounts
4. **Token Refresh**: Automatic token refresh with 2-minute safety buffer

### Common Issues

1. **Database Connection**: Default SQLite works out of the box; check file permissions
2. **MCP Server**: Ensure Node.js 18+ is installed and in PATH
3. **Port Conflicts**: Ensure ports 3000 (frontend) and 8000 (backend) are available
4. **Dependencies**: Run `python setup.py` to check and install prerequisites

### Development Issues

1. **Backend Reload**: Some auth/MCP files excluded from auto-reload to prevent connection issues
2. **Frontend Hot Reload**: Vite handles automatic reloading for React components
3. **Database Schema**: Tables auto-created on first run; manual migration not required

### Logs and Debugging

- **Backend Logs**: uvicorn console output with detailed error messages
- **Frontend Logs**: Browser developer console
- **Authentication**: Detailed logging in auth_service.py
- **MCP Communication**: JSON-RPC logs for Kusto server interaction
- **Chat Sessions**: Conversation state and message history in database

## License

Internal Microsoft tool for Intune support engineering.