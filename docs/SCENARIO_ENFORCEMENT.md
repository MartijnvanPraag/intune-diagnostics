# Scenario & Kusto Query Enforcement Simplification

## Overview
The agent now enforces a two-tier acceptance model for executing Kusto queries:

1. Scenario Lock (when a scenario has been confidently selected) – only the canonical queries for that scenario are allowed.
2. Global Fenced Allow-List – ANY query that appears in a fenced ```kusto code block in `instructions.md` is always allowed (placeholder tolerant) even if the current scenario lock patterns do not match, preventing false negatives when the model formats a canonical query without its regional cluster prefix, etc.

If a scenario lock rejects a query, the system automatically attempts the global allow-list before returning an error.

## Rationale
- Eliminates brittle dependence on complex parsing heuristics.
- Ensures every explicitly authored canonical Kusto block is executable.
- Still blocks model hallucinations that are not present in `instructions.md`.

## How It Works
1. On first scenario lookup (or earlier), the system extracts every fenced ` ```kusto ` block:
   - Builds a regex pattern per block with placeholder wildcards (`<DeviceId>`, `<TenantId>`, etc.).
   - Computes a normalized SHA-256 hash for each canonical form.
2. Scenario lock adds stricter patterns + hashes for the selected scenario.
3. During `execute_query`:
   - If scenario lock active: check scenario patterns/hashes.
   - If that fails: check global patterns/hashes.
   - If both fail: reject with guidance.

## Placeholder Normalization
Placeholders enclosed in angle brackets are replaced by a non-greedy wildcard pattern. Whitespace (multiple spaces, line ending differences) is tolerated.

## Adding or Updating Queries
- Just add or modify a fenced ` ```kusto ` block in `instructions.md`.
- Restart / trigger a scenario lookup; the global allow-list rebuilds automatically.

## Debug Logging Markers
- `[GlobalKustoAllow] Extracted N fenced kusto block(s)` – initial build.
- `[GlobalKustoAllow] Accepted query outside scenario lock via global fenced allow-list` – fallback success.
- `[ScenarioLock] Rejected query (no pattern/hash/global match)` – final denial.

## When a Query Is Rejected
Check:
1. Is the exact canonical query (including function name & parameter order) present in a fenced `kusto` block?
2. Are you using placeholders correctly (e.g., `<DeviceId>` replaced by a GUID)?
3. Did you accidentally add quotes or remove the cluster/database prefix if it is required? (Function-only variants may be accepted if authored that way; otherwise keep the full canonical form.)

## Migrating Simpler Scenarios
For a new simple scenario (one query):
- Add a heading and a fenced `kusto` block.
- No additional parser changes are required; it becomes globally executable.

## Future Improvements (Optional)
- Cache invalidation on file watch instead of first lookup.
- Per-scenario metadata summary regenerated for UI.
- Telemetry metrics on allow-list vs scenario-lock hits.

---
Generated automatically to reflect the simplified enforcement model.
