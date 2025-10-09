import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

SCENARIO_HEADING_PATTERN = re.compile(r"^#+\s+(.*)")
CODE_BLOCK_FENCE = re.compile(r"^```(kusto|sql|kql|bash|text)?\s*$", re.IGNORECASE)

class InstructionScenario:
    def __init__(self, title: str):
        self.title = title.strip()
        self.description_lines: List[str] = []
        self.queries: List[str] = []

    def add_description(self, line: str):
        self.description_lines.append(line.rstrip())

    def add_query(self, code: str):
        cleaned = code.strip()
        if cleaned:
            self.queries.append(cleaned)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": "\n".join(l for l in self.description_lines if l).strip(),
            "queries": self.queries,
        }

def parse_instructions(markdown_text: str) -> List[Dict[str, Any]]:
    """Parse instructions.md and extract scenarios with queries.

    Heuristics:
    - Any heading (## or ### etc.) starts a new scenario except top-level title.
    - Code fences are captured; if inside a scenario and code looks like Kusto (contains '|', 'cluster(' or project/take/where) treat as query.
    - Otherwise stored as description.
    """
    scenarios: List[InstructionScenario] = []
    current: Optional[InstructionScenario] = None
    in_code = False
    code_lang = None
    code_lines: List[str] = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip('\n')

        fence_match = CODE_BLOCK_FENCE.match(line)
        if fence_match:
            if not in_code:
                in_code = True
                code_lang = fence_match.group(1) or ""
                code_lines = []
            else:
                # closing fence
                in_code = False
                block = "\n".join(code_lines)
                if current and _is_probable_kusto(block):
                    current.add_query(block)
                elif current and block.strip():
                    current.add_description(block)
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        heading_match = SCENARIO_HEADING_PATTERN.match(line)
        if heading_match:
            title = heading_match.group(1).strip()
            
            # Clean up markdown formatting from titles
            title = title.replace('**', '').replace('*', '').strip()
            
            # Skip first overall title if no scenario yet and probably H1
            if current is None and line.startswith('# '):
                # Don't create a scenario for the main document title
                continue
            # Start new scenario
            current = InstructionScenario(title)
            scenarios.append(current)
            continue

        if current:
            if line.strip():
                current.add_description(line)

    # Deduplicate titles
    seen = {}
    unique: List[Dict[str, Any]] = []
    for sc in scenarios:
        key = sc.title.lower()
        if key not in seen:
            seen[key] = True
            unique.append(sc.to_dict())
        else:
            # merge queries/description into first occurrence
            for u in unique:
                if u['title'].lower() == key:
                    if sc.queries:
                        u['queries'].extend(q for q in sc.queries if q not in u['queries'])
                    if sc.description_lines:
                        desc = u['description'] + "\n" + "\n".join(sc.description_lines)
                        u['description'] = desc.strip()
                    break

    # Fallback pass: for scenarios with zero queries, search description for inline cluster().database().Function(...) lines
    inline_func_pattern = re.compile(r"cluster\(.*?\)\.database\(.*?\)\.[A-Za-z0-9_]+\(.*\)")
    rescued = 0
    for u in unique:
        if not u['queries']:
            lines = u['description'].splitlines()
            for ln in lines:
                stripped = ln.strip()
                # Ignore fenced indicators or comments
                if not stripped or stripped.startswith('```') or stripped.startswith('//'):
                    continue
                if inline_func_pattern.search(stripped):
                    u['queries'].append(stripped)
            if u['queries']:
                rescued += 1
    if rescued:
        logger.info(f"[instructions_parser] Fallback rescued queries for {rescued} scenario(s)")

    # Debug summary
    try:
        summary = [(u['title'], len(u['queries'])) for u in unique]
        logger.debug("[instructions_parser] Scenario query counts: %s", summary)
    except Exception:  # noqa: BLE001
        pass

    return [u for u in unique if u['queries']]

def _is_probable_kusto(block: str) -> bool:
    """Heuristic to decide if a fenced code block is Kusto.

    Improvements:
    - Recognize single-line cluster().database().Function(...) invocations even if they lack multiple pipe operators.
    - Accept common Intune function style names (DeviceComplianceStatusChangesByDeviceId, GetEspFailuresForTenant, etc.).
    - Lower threshold for keyword score when strong function pattern present.
    - Allow one-keyword queries if they reference DeviceId / AccountId placeholders and cluster/database pattern.
    """
    text = block.strip()
    if not text:
        return False

    lowered = text.lower()
    strong_indicators = ["cluster(", "database("]
    if any(ind in lowered for ind in strong_indicators):
        # If it has the canonical cluster().database() invocation AND an opening parenthesis for a function call after that
        # treat it as Kusto even without pipe tokens.
        if re.search(r"cluster\(.*?\)\.database\(.*?\)\.[A-Za-z0-9_]+\(", text):
            return True

    kusto_keywords = ["|", " project ", " where ", " take ", " summarize ", " extend ", " datatable ", " let ", " union ", " join "]
    function_patterns = [
        "GetTenantInformation", "GetDeviceDetails", "StatusChanges", "Investigation", "DeviceComplianceStatusChangesByDeviceId",
        "ApplicationInstallAttemptsByDeviceId", "GetEspFailuresForTenant", "HighLevelCheckin", "GetAllPolicyAssignmentsForTenant"
    ]

    score = 0
    if any(k.strip() and k.strip() in lowered for k in kusto_keywords):
        # Count occurrences of pipe separately as it's very indicative
        score += lowered.count('|') * 2
        score += sum(1 for k in kusto_keywords if k.strip() in lowered)
    score += sum(2 for p in function_patterns if p.lower() in lowered)

    # Single-line strong function with cluster prefix
    if score == 0 and any(ind in lowered for ind in strong_indicators):
        # If it references typical placeholder markers, still treat as Kusto
        if any(ph in lowered for ph in ['<deviceid>', '<accountid', '<contextid', 'ago(']):
            return True

    return score >= 2
