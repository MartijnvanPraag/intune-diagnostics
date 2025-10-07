"""
Conversation State Service

Manages conversation context by storing and retrieving key identifiers
(DeviceId, AccountId, ContextId, etc.) from query results across chat sessions.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ConversationContext:
    """Stores key identifiers extracted from query results"""
    device_id: Optional[str] = None
    account_id: Optional[str] = None
    context_id: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    scale_unit_name: Optional[str] = None
    serial_number: Optional[str] = None
    device_name: Optional[str] = None
    azure_ad_device_id: Optional[str] = None
    primary_user: Optional[str] = None
    enrolled_by_user: Optional[str] = None
    last_updated: Optional[str] = None
    
    def update_from_query_result(self, query_result: Dict[str, Any]) -> None:
        """Extract and update context from a query result"""
        self.last_updated = datetime.now(timezone.utc).isoformat()
        
        # Handle different query result formats
        if isinstance(query_result, dict):
            # If it has tables (typical MCP response format)
            if "tables" in query_result and isinstance(query_result["tables"], list):
                for table in query_result["tables"]:
                    if "rows" in table and isinstance(table["rows"], list):
                        self._extract_from_rows(table["rows"], table.get("columns", []))
            
            # Direct extraction from top-level keys
            self._extract_from_dict(query_result)
    
    def _extract_from_dict(self, data: Dict[str, Any]) -> None:
        """Extract identifiers from a dictionary"""
        key_mappings = {
            'DeviceId': 'device_id',
            'AccountId': 'account_id', 
            'ContextId': 'context_id',
            'TenantId': 'tenant_id',
            'UserId': 'user_id',
            'ScaleUnitName': 'scale_unit_name',
            'SerialNumber': 'serial_number',
            'DeviceName': 'device_name',
            'AzureAdDeviceId': 'azure_ad_device_id',
            'PrimaryUser': 'primary_user',
            'EnrolledByUser': 'enrolled_by_user'
        }
        
        for key, attr in key_mappings.items():
            if key in data and data[key]:
                setattr(self, attr, str(data[key]))
    
    def _extract_from_rows(self, rows: List[List[Any]], columns: List[str]) -> None:
        """Extract identifiers from table rows"""
        if not rows or not columns:
            return
            
        # Create column index mapping
        col_index = {col: i for i, col in enumerate(columns)}
        
        # Process first row (typically contains the main device info)
        if rows:
            first_row = rows[0]
            
            # Map common column names to context fields
            mappings = {
                'DeviceId': 'device_id',
                'AccountId': 'account_id',
                'ContextId': 'context_id', 
                'TenantId': 'tenant_id',
                'UserId': 'user_id',
                'ScaleUnitName': 'scale_unit_name',
                'SerialNumber': 'serial_number',
                'DeviceName': 'device_name',
                'AzureAdDeviceId': 'azure_ad_device_id',
                'PrimaryUser': 'primary_user',
                'EnrolledByUser': 'enrolled_by_user'
            }
            
            for col_name, field_name in mappings.items():
                if col_name in col_index:
                    idx = col_index[col_name]
                    if idx < len(first_row) and first_row[idx]:
                        setattr(self, field_name, str(first_row[idx]))

    def get_available_context(self) -> Dict[str, str]:
        """Get all non-null context values"""
        context = {}
        for field_name, value in asdict(self).items():
            if value is not None and field_name != 'last_updated':
                context[field_name] = value
        return context

    def get_value(self, key: str) -> Optional[str]:
        """Get a specific context value by key (case-insensitive)"""
        # Normalize key to field name format
        normalized_key = key.lower().replace(' ', '_')
        
        # Direct field access
        if hasattr(self, normalized_key):
            return getattr(self, normalized_key)
        
        # Handle common aliases
        aliases = {
            'deviceid': 'device_id',
            'accountid': 'account_id',
            'contextid': 'context_id',
            'tenantid': 'tenant_id',
            'userid': 'user_id',
            'scaleunitname': 'scale_unit_name',
            'serialnumber': 'serial_number',
            'devicename': 'device_name',
            'azureaddeviceid': 'azure_ad_device_id',
            'primaryuser': 'primary_user',
            'enrolledbyuser': 'enrolled_by_user'
        }
        
        if normalized_key in aliases:
            return getattr(self, aliases[normalized_key], None)
        
        return None

class ConversationStateService:
    """Service for managing conversation context across chat sessions"""
    
    def __init__(self):
        self.context = ConversationContext()
        # Resolve backend root directory robustly (this file: backend/services/conversation_state.py)
        backend_root = Path(__file__).resolve().parents[1]
        self._session_file = backend_root / "conversation_state.json"
        # Migration: if an older incorrectly nested path exists (backend/backend/conversation_state.json), move it
        try:
            old_nested = backend_root / "backend" / "conversation_state.json"
            if old_nested.exists() and not self._session_file.exists():
                self._session_file.parent.mkdir(parents=True, exist_ok=True)
                old_nested.replace(self._session_file)
                logger.info(f"Migrated conversation state from old path {old_nested} to {self._session_file}")
        except Exception as e:
            logger.warning(f"Failed migrating old conversation state file: {e}")
    
    def clear_context(self) -> None:
        """Clear all stored context"""
        self.context = ConversationContext()
        self._save_to_file()
    
    def update_from_query_result(self, query_result: Dict[str, Any]) -> None:
        """Update context from a query result"""
        try:
            self.context.update_from_query_result(query_result)
            self._save_to_file()
            logger.info(f"Updated conversation context: {list(self.context.get_available_context().keys())}")
        except Exception as e:
            logger.warning(f"Failed to update conversation context: {e}")
    
    def get_context_value(self, key: str) -> Optional[str]:
        """Get a specific context value"""
        return self.context.get_value(key)
    
    def get_all_context(self) -> Dict[str, str]:
        """Get all available context"""
        return self.context.get_available_context()
    
    def substitute_placeholders(self, query: str) -> str:
        """Replace placeholders in query with stored context values"""
        modified_query = query
        
        # Pattern to match placeholder instructions
        placeholder_patterns = [
            (r'<Fetch the accountId from Device Details and replace here>', 'account_id'),
            (r'<AccountId from Step 1>', 'account_id'),
            (r'<ContextId from Step 2>', 'context_id'),
            (r'<DeviceId>', 'device_id'),
            (r'<TenantId>', 'tenant_id'),
            (r'<UserId>', 'user_id'),
        ]
        
        for pattern, context_key in placeholder_patterns:
            if pattern in modified_query:
                value = self.get_context_value(context_key)
                if value:
                    modified_query = modified_query.replace(pattern, value)
                    logger.info(f"Replaced placeholder '{pattern}' with value from context: {value}")
                else:
                    logger.warning(f"No value found in context for placeholder '{pattern}' (key: {context_key})")
        
        return modified_query
    
    def _save_to_file(self) -> None:
        """Save context to file for persistence"""
        try:
            self._session_file.parent.mkdir(exist_ok=True)
            with open(self._session_file, 'w') as f:
                json.dump(asdict(self.context), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save conversation state: {e}")
    
    def _load_from_file(self) -> None:
        """Load context from file"""
        try:
            if self._session_file.exists():
                with open(self._session_file, 'r') as f:
                    data = json.load(f)
                    # Create new context with loaded data
                    self.context = ConversationContext(**{k: v for k, v in data.items() if k != 'last_updated'})
                    self.context.last_updated = data.get('last_updated')
                    logger.info("Loaded conversation context from file")
        except Exception as e:
            logger.warning(f"Failed to load conversation state: {e}")
            self.context = ConversationContext()

# Global service instance
_conversation_state_service: Optional[ConversationStateService] = None

def get_conversation_state_service() -> ConversationStateService:
    """Get the global conversation state service instance"""
    global _conversation_state_service
    if _conversation_state_service is None:
        _conversation_state_service = ConversationStateService()
        _conversation_state_service._load_from_file()
    return _conversation_state_service

def reset_conversation_state() -> None:
    """Reset the global conversation state"""
    global _conversation_state_service
    if _conversation_state_service:
        _conversation_state_service.clear_context()