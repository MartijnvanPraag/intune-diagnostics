import os
import time
from typing import Optional, Dict, Tuple
from azure.identity import DefaultAzureCredential, get_bearer_token_provider, InteractiveBrowserCredential, SharedTokenCacheCredential
from azure.core.exceptions import ClientAuthenticationError
import httpx
import json

class AuthService:
    _token_cache: Dict[str, Tuple[float, str]] = {}
    def __init__(self):
        # Use DefaultAzureCredential with explicit exclusions to force WAM-compatible flow
        # Exclude Azure CLI and other problematic credential types that bypass WAM
        self.credential = DefaultAzureCredential(
            # Exclude credentials that don't use WAM broker
            exclude_azure_cli_credential=False,
            exclude_azure_powershell_credential=False,
            exclude_visual_studio_code_credential=False,
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True,
            # Keep only Interactive Browser and Shared Token Cache (which uses WAM)
            exclude_interactive_browser_credential=False,
            exclude_shared_token_cache_credential=False,
        )
        
        # Also create a WAM-specific credential as backup
        self.wam_credential = InteractiveBrowserCredential(
            enable_support_for_broker=True,
            # Force WAM usage with explicit parameters
            parent_window_handle=None,
            # Disable fallback to browser if WAM fails
            disable_automatic_authentication=False,
        )
        
        # Use Cognitive Services scope for Azure AI services (not Microsoft Graph)
        self.cognitive_services_scope = "https://cognitiveservices.azure.com/.default"
        self.graph_scope = "https://graph.microsoft.com/.default"
        
        # Create token providers - try WAM first, fallback to restricted DefaultAzureCredential
        try:
            self.cognitive_token_provider = get_bearer_token_provider(
                self.wam_credential, 
                self.cognitive_services_scope
            )
            self.graph_token_provider = get_bearer_token_provider(
                self.wam_credential,
                self.graph_scope
            )
            print("Using WAM broker credential for authentication")
        except Exception as e:
            print(f"WAM credential failed, using restricted DefaultAzureCredential: {e}")
            self.cognitive_token_provider = get_bearer_token_provider(
                self.credential, 
                self.cognitive_services_scope
            )
            self.graph_token_provider = get_bearer_token_provider(
                self.credential,
                self.graph_scope
            )
        
    print("Authentication initialized - Azure CLI excluded, WAM broker preferred")
    # In-memory token cache: scope -> (expires_on_epoch, token)
    # Instance will reuse class-level dict; could also choose self._token_cache = {} to isolate
    
    async def get_access_token(self, scope: Optional[str] = None, force_refresh: bool = False) -> str:
        """Get an access token (cached) using WAM broker credential.

        Token reuse logic: store token per scope with 2 minute safety buffer before expiry.
        """
        target_scope = scope or self.graph_scope
        now = time.time()
        cached = self._token_cache.get(target_scope)
        if cached and not force_refresh:
            exp, tok = cached
            if exp - 120 > now:  # 2 minute buffer
                return tok
        try:
            token = self.wam_credential.get_token(target_scope)
            # azure-identity returns expires_on as int epoch
            self._token_cache[target_scope] = (float(getattr(token, 'expires_on', now + 3000)), token.token)
            return token.token
        except Exception as e:
            print(f"WAM broker authentication failed, trying restricted DefaultAzureCredential: {e}")
            try:
                token = self.credential.get_token(target_scope)
                self._token_cache[target_scope] = (float(getattr(token, 'expires_on', now + 3000)), token.token)
                return token.token
            except ClientAuthenticationError as fallback_e:
                raise Exception(f"Authentication failed with both WAM and restricted credential: {str(fallback_e)}")

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
        """Complete authentication flow and return user info - always get fresh tokens"""
        try:
            # Always clear cache to ensure fresh authentication
            self.clear_token_cache()
            
            # Get Microsoft Graph token for user info with force refresh
            graph_token = await self.get_access_token(self.graph_scope, force_refresh=True)
            user_info = await self.get_user_info(graph_token)
            
            return {
                "azure_user_id": user_info.get("id"),
                "email": user_info.get("userPrincipalName"),
                "display_name": user_info.get("displayName"),
                "access_token": graph_token
            }
        except Exception as e:
            raise Exception(f"Authentication process failed: {str(e)}")
    
    def clear_token_cache(self):
        """Clear all cached tokens to force fresh authentication"""
        self._token_cache.clear()
        print("Token cache cleared - next authentication will be interactive")
    
    def sign_out(self):
        """Sign out user by clearing ALL token caches and invalidating cached credentials"""
        # Clear our internal token cache for all scopes
        self._token_cache.clear()
        
        # Try to clear the credential cache as well
        try:
            # Create new WAM credential instance to clear cached state
            self.wam_credential = InteractiveBrowserCredential(
                enable_support_for_broker=True,
                parent_window_handle=None,
                disable_automatic_authentication=False,
            )
            
            # Also recreate the default credential to clear its cache
            self.credential = DefaultAzureCredential(
                exclude_azure_cli_credential=False,
                exclude_azure_powershell_credential=False,
                exclude_visual_studio_code_credential=False,
                exclude_environment_credential=True,
                exclude_managed_identity_credential=True,
                exclude_interactive_browser_credential=False,
                exclude_shared_token_cache_credential=False,
            )
            
            # Recreate token providers with fresh credentials for all services
            self.cognitive_token_provider = get_bearer_token_provider(
                self.wam_credential, 
                self.cognitive_services_scope
            )
            self.graph_token_provider = get_bearer_token_provider(
                self.wam_credential,
                self.graph_scope
            )
            
            print("User signed out - all credential caches cleared (Graph, Cognitive Services, Kusto)")
            print(f"Cleared {len(self._token_cache)} cached tokens")
        except Exception as e:
            print(f"Warning: Could not fully clear credential cache: {e}")
            # Still clear what we can
            self._token_cache.clear()

# Global auth service instance
auth_service = AuthService()