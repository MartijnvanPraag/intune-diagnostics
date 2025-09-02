import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple, Optional, Set

GUID_REGEX = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
WINDOW = 4

ROLE_KEYWORDS = {
    "device_id": ["device","machine","endpoint","computer"],
    "account_id": ["account","tenant","user","principal","aad"],
    "context_id": ["context","ctx"],
    "policy_id": ["policy","payload","config","configuration"],
}

@dataclass
class GuidCandidate:
    guid: str
    index: int  # token index of guid placeholder
    window_text: str
    role_scores: Dict[str, int]

    def to_public(self):
        return {
            "guid": self.guid,
            "window": self.window_text,
            "scores": self.role_scores,
        }


def tokenize(message: str) -> List[str]:
    # Simple whitespace + punctuation split
    return re.findall(r"[A-Za-z0-9_-]+", message)


def extract_guid_candidates(message: str) -> List[GuidCandidate]:
    tokens = tokenize(message)
    lower_tokens = [t.lower() for t in tokens]
    guid_candidates: List[GuidCandidate] = []
    # Map token indices to original token for quick lookup
    for i, tok in enumerate(tokens):
        if GUID_REGEX.fullmatch(tok):
            start = max(0, i - WINDOW)
            end = min(len(tokens), i + WINDOW + 1)
            context_slice = lower_tokens[start:end]
            role_scores: Dict[str, int] = {}
            for role, kws in ROLE_KEYWORDS.items():
                score = sum(1 for kw in kws if kw in context_slice)
                if score:
                    role_scores[role] = score
            guid_candidates.append(GuidCandidate(guid=tok, index=i, window_text=" ".join(tokens[start:end]), role_scores=role_scores))
    return guid_candidates


def resolve_entities(
    message: str,
    intent: str,
    needed_slots: List[str],
    state: Dict[str, Any]
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Return (resolved_params, meta) where meta contains candidates and ambiguity flags.
    Does not call LLM; pure heuristic.
    """
    candidates = extract_guid_candidates(message)
    resolved: Dict[str, str] = {}
    meta: Dict[str, Any] = {
        "candidates": [c.to_public() for c in candidates],
        "heuristic": True,
        "ambiguities": [],
    }

    if not candidates:
        return resolved, meta

    # If exactly one candidate and one needed slot, assign directly
    if len(candidates) == 1 and len(needed_slots) == 1:
        resolved[needed_slots[0]] = candidates[0].guid
        return resolved, meta

    # Score per (slot, candidate)
    # Basic approach: candidate role score for slot keyword list; tie-break by proximity to explicit slot name mention
    message_lower = message.lower()
    for slot in needed_slots:
        slot_scores: List[Tuple[str, int]] = []
        for c in candidates:
            base = c.role_scores.get(slot, 0)
            # Add small boost if preceding token is the slot root (e.g., 'device') near the candidate
            if slot.startswith('device') and re.search(r"device[^a-z0-9]*" + re.escape(c.guid), message_lower):
                base += 2
            if slot.startswith('account') and re.search(r"account[^a-z0-9]*" + re.escape(c.guid), message_lower):
                base += 2
            if slot.startswith('context') and re.search(r"context[^a-z0-9]*" + re.escape(c.guid), message_lower):
                base += 2
            if slot.startswith('policy') and re.search(r"policy[^a-z0-9]*" + re.escape(c.guid), message_lower):
                base += 2
            slot_scores.append((c.guid, base))
        # Choose best if clear
        slot_scores.sort(key=lambda x: x[1], reverse=True)
        if slot_scores:
            top_guid, top_score = slot_scores[0]
            second_score = slot_scores[1][1] if len(slot_scores) > 1 else -1
            if top_score > 0 and (top_score - second_score) >= 2:
                resolved[slot] = top_guid
            else:
                meta["ambiguities"].append({
                    "slot": slot,
                    "candidates": slot_scores
                })
    return resolved, meta


def needed_slots_for_intent(intent: str) -> List[str]:
    mapping = {
        "device_details": ["device_id"],
        "compliance": ["device_id"],
        "policy_status": ["device_id", "context_id"],
        "user_lookup": ["device_id"],
        "tenant_info": ["account_id"],
        "effective_groups": ["device_id", "account_id"],
        "applications": ["device_id"],
        "mam_policy": ["device_id", "context_id"],
    }
    return mapping.get(intent, [])
