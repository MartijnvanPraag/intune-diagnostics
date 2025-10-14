import re
from typing import List, Dict, Any, Optional

SCENARIO_HEADING_PATTERN = re.compile(r"^(#{2,3})\s+(.*)")  # Match ## or ###
CODE_BLOCK_FENCE = re.compile(r"^```(kusto|sql|kql|bash|text)?\s*$", re.IGNORECASE)
METADATA_START = re.compile(r"^<!--\s*$")
METADATA_END = re.compile(r"^-->\s*$")
METADATA_FIELD = re.compile(r"^-\s*(\w+):\s*(.*)$")

class InstructionScenario:
    def __init__(self, title: str, heading_level: int = 3):
        self.title = title.strip()
        self.heading_level = heading_level
        self.description_lines: List[str] = []
        self.queries: List[str] = []
        # Metadata fields
        self.slug: Optional[str] = None
        self.domain: Optional[str] = None
        self.keywords_meta: Optional[str] = None  # Raw keywords from metadata
        self.required_identifiers: Optional[str] = None
        self.aliases: Optional[str] = None
        self.description_meta: Optional[str] = None  # Description from metadata

    def add_description(self, line: str):
        self.description_lines.append(line.rstrip())

    def add_query(self, code: str):
        cleaned = code.strip()
        if cleaned:
            self.queries.append(cleaned)
    
    def set_metadata(self, field: str, value: str):
        """Set metadata field"""
        field_lower = field.lower().strip()
        value_clean = value.strip()
        
        if field_lower == 'slug':
            self.slug = value_clean
        elif field_lower == 'domain':
            self.domain = value_clean
        elif field_lower == 'keywords':
            self.keywords_meta = value_clean
        elif field_lower == 'required_identifiers':
            self.required_identifiers = value_clean
        elif field_lower == 'aliases':
            self.aliases = value_clean
        elif field_lower == 'description':
            self.description_meta = value_clean

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "title": self.title,
            "description": "\n".join(l for l in self.description_lines if l).strip(),
            "queries": self.queries,
        }
        
        # Add metadata fields if present
        if self.slug:
            result["slug"] = self.slug
        if self.domain:
            result["domain"] = self.domain
        if self.keywords_meta:
            result["keywords_meta"] = self.keywords_meta
        if self.required_identifiers:
            result["required_identifiers"] = self.required_identifiers
        if self.aliases:
            result["aliases"] = self.aliases
        if self.description_meta:
            result["description_meta"] = self.description_meta
            
        return result

def parse_instructions(markdown_text: str) -> List[Dict[str, Any]]:
    """Parse instructions.md and extract scenarios with queries and metadata.

    Heuristics:
    - ### headings are diagnostic scenarios (#### are non-scenarios like legends/rules)
    - HTML comments immediately after headings contain structured metadata
    - Code fences are captured; if inside a scenario and code looks like Kusto, treat as query.
    - Otherwise stored as description.
    """
    scenarios: List[InstructionScenario] = []
    current: Optional[InstructionScenario] = None
    in_code = False
    in_metadata = False
    code_lang = None
    code_lines: List[str] = []
    metadata_lines: List[str] = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip('\n')

        # Check for metadata block start
        if METADATA_START.match(line) and current and not in_code:
            in_metadata = True
            metadata_lines = []
            continue
        
        # Check for metadata block end
        if METADATA_END.match(line) and in_metadata:
            in_metadata = False
            # Parse metadata fields
            if current:  # Type safety check
                for meta_line in metadata_lines:
                    field_match = METADATA_FIELD.match(meta_line.strip())
                    if field_match:
                        field_name = field_match.group(1)
                        field_value = field_match.group(2)
                        current.set_metadata(field_name, field_value)
            metadata_lines = []
            continue
        
        # Collect metadata lines
        if in_metadata:
            metadata_lines.append(line)
            continue

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
            heading_level = len(heading_match.group(1))  # Count the # symbols
            title = heading_match.group(2).strip()
            
            # Clean up markdown formatting from titles
            title = title.replace('**', '').replace('*', '').strip()
            
            # Skip if this is not a level-3 heading (scenarios are ### only)
            # Level-4 headings (####) are non-scenarios like legends/rules
            if heading_level != 3:
                continue
            
            # Skip first overall title if no scenario yet and probably H1/H2
            if current is None and heading_level <= 2:
                # Don't create a scenario for the main document title
                continue
            
            # Start new scenario
            current = InstructionScenario(title, heading_level)
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
