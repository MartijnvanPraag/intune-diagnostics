import os
from typing import Optional
from azure.identity import DefaultAzureCredential, get_bearer_token_provider, InteractiveBrowserCredential, SharedTokenCacheCredential
from azure.core.exceptions import ClientAuthenticationError
import httpx
import json

class AuthService:
    def __init__(self):
        # Use DefaultAzureCredential with explicit exclusions to force WAM-compatible flow
        # Exclude Azure CLI and other problematic credential types that bypass WAM
        self.credential = DefaultAzureCredential(
            # Exclude credentials that don't use WAM broker
            exclude_azure_cli_credential=True,
            exclude_azure_powershell_credential=True,
            exclude_visual_studio_code_credential=True,
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
    
    async def get_access_token(self, scope: str = None) -> str:
        """Get an access token using WAM broker credential"""
        target_scope = scope or self.graph_scope
        
        try:
            # Try WAM broker credential first
            token = self.wam_credential.get_token(target_scope)
            print(f"Successfully obtained token using WAM broker for scope: {target_scope}")
            return token.token
        except Exception as e:
            print(f"WAM broker authentication failed, trying restricted DefaultAzureCredential: {e}")
            try:
                # Fallback to restricted DefaultAzureCredential (no CLI)
                token = self.credential.get_token(target_scope)
                return token.token
            except ClientAuthenticationError as fallback_e:
                raise Exception(f"Authentication failed with both WAM and restricted credential: {str(fallback_e)}")
    
    async def get_cognitive_services_token(self) -> str:
        """Get access token specifically for Azure Cognitive Services"""
        return await self.get_access_token(self.cognitive_services_scope)
    
    async def get_graph_token(self) -> str:
        """Get access token specifically for Microsoft Graph"""
        return await self.get_access_token(self.graph_scope)
    
    async def get_user_info(self, access_token: str = None) -> dict:
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
        """Complete authentication flow and return user info"""
        try:
            # Get Microsoft Graph token for user info
            graph_token = await self.get_graph_token()
            user_info = await self.get_user_info(graph_token)
            
            return {
                "azure_user_id": user_info.get("id"),
                "email": user_info.get("userPrincipalName"),
                "display_name": user_info.get("displayName"),
                "access_token": graph_token
            }
        except Exception as e:
            raise Exception(f"Authentication process failed: {str(e)}")

# Global auth service instance
auth_service = AuthService()