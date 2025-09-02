from __future__ import annotations
from typing import Dict, Any, Optional, List

class ConversationState:
    """Holds extracted entities from prior diagnostic results to enable follow-up queries."""
    def __init__(self):
        self.device_id: Optional[str] = None
        self.account_id: Optional[str] = None
        self.context_id: Optional[str] = None
        self.effective_group_id: Optional[str] = None
        self.tenant_id: Optional[str] = None
        self.payload_id: Optional[str] = None
        # Raw history of actions
        self.history: List[Dict[str, Any]] = []

    def update_from_table(self, table: Dict[str, Any]):
        rows = table.get("rows") or []
        columns = table.get("columns") or []
        if not rows or not columns:
            return
        # Build index map for quick lookup
        col_index = {c.lower(): i for i, c in enumerate(columns)}
        # Inspect first handful of rows for identifiers
        for r in rows[:5]:
            def grab(key: str) -> Optional[str]:
                idx = col_index.get(key.lower())
                if idx is not None and idx < len(r):
                    val = r[idx]
                    if isinstance(val, str) and val and val.lower() not in {"null", "none", "undefined", ""}:
                        return val
                return None
            self.device_id = self.device_id or grab("DeviceId")
            self.account_id = self.account_id or grab("AccountId")
            self.context_id = self.context_id or grab("ContextId")
            self.effective_group_id = self.effective_group_id or grab("EffectiveGroupId")
            self.tenant_id = self.tenant_id or grab("TenantId") or self.account_id
            self.payload_id = self.payload_id or grab("PolicyId") or grab("PayloadId")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "account_id": self.account_id,
            "context_id": self.context_id,
            "effective_group_id": self.effective_group_id,
            "tenant_id": self.tenant_id,
            "payload_id": self.payload_id,
        }

    def record_action(self, action: str, params: Dict[str, Any]):
        self.history.append({"action": action, "params": params, "state": self.snapshot()})

    def load_from_snapshot(self, snap: Dict[str, Any]):
        self.device_id = snap.get("device_id") or self.device_id
        self.account_id = snap.get("account_id") or self.account_id
        self.context_id = snap.get("context_id") or self.context_id
        self.effective_group_id = snap.get("effective_group_id") or self.effective_group_id
        self.tenant_id = snap.get("tenant_id") or self.tenant_id
        self.payload_id = snap.get("payload_id") or self.payload_id

    def fill_defaults(self, params: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(params)
        if "device_id" not in out and self.device_id:
            out["device_id"] = self.device_id
        if "account_id" not in out and self.account_id:
            out["account_id"] = self.account_id
        if "context_id" not in out and self.context_id:
            out["context_id"] = self.context_id
        if "tenant_id" not in out and self.tenant_id:
            out["tenant_id"] = self.tenant_id
        if "payload_id" not in out and self.payload_id:
            out["payload_id"] = self.payload_id
        return out

# Simple rule-based intent mapping
INTENT_KEYWORDS = {
    "device details": "device_details",
    "device detail": "device_details",
    "details": "device_details",
    "detail": "device_details",
    "detailed": "device_details",
    "information": "device_details",
    "info": "device_details",
    "compliance": "compliance",
    "compliance status": "compliance",
    "policy status": "policy_status",
    "policy": "policy_status",
    "user": "user_lookup",
    "tenant": "tenant_info",
    "effective group": "effective_groups",
    "group": "effective_groups",
    "applications": "applications",
    "application": "applications",
    "apps": "applications",
    "app status": "applications",
    "mam": "mam_policy",
    "mam policy": "mam_policy",
}

def classify_intent(message: str) -> Optional[str]:
    m = message.lower()
    for kw, intent in INTENT_KEYWORDS.items():
        if kw in m:
            return intent
    return None
