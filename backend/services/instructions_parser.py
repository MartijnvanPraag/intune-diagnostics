import re
from typing import List, Dict, Any, Optional

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

    return [u for u in unique if u['queries']]

def _is_probable_kusto(block: str) -> bool:
    text = block.strip()
    if not text:
        return False
    
    # Strong indicators that this is a Kusto query
    strong_indicators = ["cluster(", "database("]
    kusto_keywords = ["|", "project ", "where ", "take ", "summarize ", "extend ", "datatable ", "let ", "union ", "join "]
    function_patterns = ["GetTenantInformation", "GetDeviceDetails", "StatusChanges", "Investigation"]
    
    # If it starts with cluster() call, it's almost certainly Kusto
    if any(indicator in text for indicator in strong_indicators):
        return True
    
    # Or if it has multiple Kusto keywords/patterns
    score = sum(1 for i in kusto_keywords if i.lower() in text.lower())
    score += sum(1 for p in function_patterns if p in text)
    
    return score >= 2
