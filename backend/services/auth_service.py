import os
import time
from typing import Optional, Dict, Tuple
from azure.identity import DefaultAzureCredential, get_bearer_token_provider, InteractiveBrowserCredential, OnBehalfOfCredential, ManagedIdentityCredential
from azure.core.exceptions import ClientAuthenticationError
from azure.core.credentials import AccessToken
import httpx
import json
import logging

logger = logging.getLogger(__name__)

# Check if running in Azure App Service
IS_AZURE_APP_SERVICE = os.getenv("WEBSITE_INSTANCE_ID") is not None

class UserTokenCredential:
    """
    Custom credential that uses a user-provided access token.
    This allows us to use the MSAL token from the frontend for Azure SDK calls.
    """
    def __init__(self, access_token: str):
        self._access_token = access_token
        # Set expiry to 1 hour from now (typical token lifetime)
        self._expires_on = int(time.time()) + 3600
    
    def get_token(self, *scopes, **kwargs) -> AccessToken:
        """Return the user's access token as an AccessToken object"""
        return AccessToken(self._access_token, self._expires_on)

class AuthService:
    """
    Robust authentication service with support for user-provided MSAL tokens.
    
    For web app scenarios (Azure App Service):
    1. Frontend authenticates user via MSAL and obtains access token
    2. Frontend passes token to backend with each API call
    3. Backend uses token directly or exchanges it for service-specific tokens
    
    For local development:
    1. Falls back to DefaultAzureCredential (Azure CLI, VS Code, etc.)
    2. Supports interactive auth if needed
    """
    
    _token_cache: Dict[str, Tuple[float, str]] = {}
    
    def __init__(self):
        # Lazy-initialized credentials (only create when first used)
        self._credential: Optional[DefaultAzureCredential] = None
        self._wam_credential: Optional[InteractiveBrowserCredential] = None
        self._managed_identity_credential: Optional[ManagedIdentityCredential] = None
        self._credential_initialized = False
        
        # User-provided token for MSAL-based auth (from frontend)
        self._user_token: Optional[str] = None
        self._user_token_credential: Optional[UserTokenCredential] = None
        
        # Azure AD application credentials for OBO flow (if needed)
        self.client_id = os.getenv("AZURE_CLIENT_ID", "fbadc585-90b3-48ab-8052-c1fcc32ce3fe")
        self.tenant_id = os.getenv("AZURE_TENANT_ID", "72f988bf-86f1-41af-91ab-2d7cd011db47")
        self.client_secret = os.getenv("AZURE_CLIENT_SECRET")  # Only needed for OBO flow
        
        # Use Cognitive Services scope for Azure AI services (not Microsoft Graph)
        self.cognitive_services_scope = "https://cognitiveservices.azure.com/.default"
        self.graph_scope = "https://graph.microsoft.com/.default"
        
        # Token providers will be created lazily
        self._cognitive_token_provider = None
        self._graph_token_provider = None
        
        # Check if running in Azure App Service
        if IS_AZURE_APP_SERVICE:
            logger.info("AuthService initialized - running in Azure App Service, will use Managed Identity for AI services")
        else:
            logger.info("AuthService initialized - local development mode, supports MSAL token injection and credential fallback")
    
    def set_user_token(self, access_token: str):
        """
        Set the user's MSAL access token from the frontend.
        This allows the backend to use the user's authenticated session.
        
        Args:
            access_token: The access token from MSAL (from frontend)
        """
        self._user_token = access_token
        self._user_token_credential = UserTokenCredential(access_token)
        
        # Clear token providers to force recreation with new credential
        self._cognitive_token_provider = None
        self._graph_token_provider = None
        
        logger.info("User token set - will use MSAL token for authentication")
    
    def clear_user_token(self):
        """Clear the user's token and revert to default credentials"""
        self._user_token = None
        self._user_token_credential = None
        self._cognitive_token_provider = None
        self._graph_token_provider = None
        logger.info("User token cleared - will use default credentials")
    
    def _ensure_credentials_initialized(self):
        """Lazy initialization of credentials - only called when actually needed"""
        if self._credential_initialized:
            return
            
        logger.info("Initializing Azure credentials...")
        
        # Primary credential: Prefer Azure CLI for non-interactive scenarios
        # This avoids browser prompts during development when already signed in via 'az login'
        self._credential = DefaultAzureCredential(
            # Prefer Azure CLI (already authenticated, no prompts)
            exclude_azure_cli_credential=False,
            # Exclude interactive/browser flows unless needed
            exclude_interactive_browser_credential=True,
            # Exclude environment/managed identity for local dev
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True,
            # Allow shared token cache (persisted auth)
            exclude_shared_token_cache_credential=False,
            # Allow VS Code/PowerShell (already authenticated)
            exclude_visual_studio_code_credential=False,
            exclude_azure_powershell_credential=False,
        )
        
        # Backup credential: WAM broker for interactive scenarios (e.g., user login endpoint)
        # Only initialized when explicitly needed for interactive auth
        self._wam_credential = None  # Created on-demand in authenticate_user()
        
        self._credential_initialized = True
        logger.info("Azure credentials initialized - using Azure CLI (non-interactive)")
    
    @property
    def credential(self):
        """Return the appropriate credential based on context"""
        # If running in Azure App Service, use Managed Identity for AI services
        if IS_AZURE_APP_SERVICE:
            if self._managed_identity_credential is None:
                logger.info("Creating Managed Identity credential for Azure App Service")
                self._managed_identity_credential = ManagedIdentityCredential()
            return self._managed_identity_credential
        
        # If user token is available, use it (for web app scenarios in local dev)
        if self._user_token_credential is not None:
            logger.debug("Using user-provided MSAL token")
            return self._user_token_credential
        
        # Otherwise use default credential (for local development)
        self._ensure_credentials_initialized()
        assert self._credential is not None, "Credential should be initialized"
        return self._credential
    
    @property
    def wam_credential(self):
        """Return the appropriate credential for interactive scenarios"""
        # If running in Azure App Service, use Managed Identity
        if IS_AZURE_APP_SERVICE:
            if self._managed_identity_credential is None:
                logger.info("Creating Managed Identity credential for Azure App Service")
                self._managed_identity_credential = ManagedIdentityCredential()
            return self._managed_identity_credential
        
        # If user token is available, use it
        if self._user_token_credential is not None:
            logger.debug("Using user-provided MSAL token for WAM scenarios")
            return self._user_token_credential
        
        # Otherwise create WAM credential for local development
        self._ensure_credentials_initialized()
        
        # Create WAM credential on first access if not exists
        if self._wam_credential is None:
            logger.info("Creating WAM broker credential for Azure OpenAI...")
            self._wam_credential = InteractiveBrowserCredential(
                enable_support_for_broker=True,
                parent_window_handle=None,
                disable_automatic_authentication=False,
            )
            logger.info("WAM broker credential created")
        
        assert self._wam_credential is not None, "WAM credential should be initialized"
        return self._wam_credential
    
    @property
    def cognitive_token_provider(self):
        """Lazy-loaded cognitive services token provider"""
        if self._cognitive_token_provider is None:
            self._cognitive_token_provider = get_bearer_token_provider(
                self.wam_credential,  # This will auto-create WAM credential
                self.cognitive_services_scope
            )
        return self._cognitive_token_provider
    
    @property
    def graph_token_provider(self):
        """Lazy-loaded graph token provider"""
        if self._graph_token_provider is None:
            self._graph_token_provider = get_bearer_token_provider(
                self.wam_credential,  # This will auto-create WAM credential
                self.graph_scope
            )
        return self._graph_token_provider
    
    async def get_access_token(self, scope: Optional[str] = None, force_refresh: bool = False, interactive: bool = False) -> str:
        """Get an access token (cached) using appropriate credential.

        Token reuse logic: store token per scope with 2 minute safety buffer before expiry.
        
        Args:
            scope: The Azure scope to authenticate for
            force_refresh: Force getting a new token even if cached
            interactive: Use WAM/interactive credential (for user login). If False, uses Azure CLI.
        """
        target_scope = scope or self.graph_scope
        now = time.time()
        cached = self._token_cache.get(target_scope)
        if cached and not force_refresh:
            exp, tok = cached
            if exp - 120 > now:  # 2 minute buffer
                return tok
        
        # Choose credential based on whether interactive auth is needed
        if interactive:
            # For user login - use WAM credential (may show browser prompt)
            logger.info(f"Getting token for {target_scope} using WAM credential (interactive)")
            try:
                token = self.wam_credential.get_token(target_scope)
                self._token_cache[target_scope] = (float(getattr(token, 'expires_on', now + 3000)), token.token)
                return token.token
            except Exception as e:
                logger.warning(f"WAM credential failed: {e}, falling back to default credential")
                # Fall through to default credential
        
        # For background services - use Azure CLI (no prompts)
        logger.debug(f"Getting token for {target_scope} using default credential (non-interactive)")
        try:
            token = self.credential.get_token(target_scope)
            self._token_cache[target_scope] = (float(getattr(token, 'expires_on', now + 3000)), token.token)
            return token.token
        except ClientAuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            raise Exception(f"Authentication failed for scope {target_scope}: {str(e)}")

    async def get_kusto_token(self, cluster_url: str) -> str:
        """Return cached access token for a Kusto cluster resource scope.

        Kusto AAD scope pattern: https://{cluster_host}/.default
        Accept full https://... or just host; normalize host.
        """
        if not cluster_url:
            raise ValueError("cluster_url required for Kusto token")
        host = cluster_url
        if host.startswith('https://'):
            host = host[len('https://'):]
        if host.startswith('http://'):
            host = host[len('http://'):]
        host = host.rstrip('/')
        scope = f"https://{host}/.default"
        return await self.get_access_token(scope)
    
    async def get_cognitive_services_token(self) -> str:
        """Get access token specifically for Azure Cognitive Services"""
        return await self.get_access_token(self.cognitive_services_scope)
    
    async def get_graph_token(self) -> str:
        """Get access token specifically for Microsoft Graph"""
        return await self.get_access_token(self.graph_scope)
    
    async def get_user_info(self, access_token: Optional[str] = None) -> dict:
        """Get user information from Microsoft Graph"""
        if not access_token:
            access_token = await self.get_graph_token()
            
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get user info: {response.status_code}")
            
            return response.json()
    
    async def authenticate_user(self) -> dict:
        """Complete authentication flow and return user info - always get fresh tokens with interactive prompt"""
        try:
            # Always clear cache to ensure fresh authentication
            self.clear_token_cache()
            
            # Get Microsoft Graph token for user info with force refresh and interactive auth
            logger.info("Authenticating user interactively...")
            graph_token = await self.get_access_token(
                self.graph_scope, 
                force_refresh=True,
                interactive=True  # Use WAM credential for user login
            )
            user_info = await self.get_user_info(graph_token)
            
            logger.info(f"User authenticated: {user_info.get('userPrincipalName')}")
            return {
                "azure_user_id": user_info.get("id"),
                "email": user_info.get("userPrincipalName"),
                "display_name": user_info.get("displayName"),
                "access_token": graph_token
            }
        except Exception as e:
            logger.error(f"User authentication failed: {e}")
            raise Exception(f"Authentication process failed: {str(e)}")
    
    def clear_token_cache(self):
        """Clear all cached tokens to force fresh authentication"""
        count = len(self._token_cache)
        self._token_cache.clear()
        logger.info(f"Token cache cleared ({count} tokens) - next authentication will be fresh")
    
    def sign_out(self):
        """Sign out user by clearing ALL token caches and invalidating cached credentials"""
        # Clear our internal token cache for all scopes
        self._token_cache.clear()
        
        # Clear credential state - next use will re-initialize
        self._credential = None
        self._wam_credential = None
        self._credential_initialized = False
        
        # Clear token providers - will be recreated on next use
        self._cognitive_token_provider = None
        self._graph_token_provider = None
        
        logger.info("User signed out - all credentials and token caches cleared")
        logger.info("Next authentication will create fresh credentials")

# Global auth service instance
auth_service = AuthService()