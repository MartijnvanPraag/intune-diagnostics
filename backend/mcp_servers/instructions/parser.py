"""
Enhanced parser for instructions.md that extracts structured scenarios with steps.

This parser extends the basic instructions_parser to extract:
- Step-by-step queries with numbers
- Placeholders in each query
- Dependencies between steps
- Output format expectations
"""

import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from .models import (
    Scenario, QueryStep, Placeholder, ExtractedValue, OutputFormat,
    PlaceholderType
)


class InstructionsParser:
    """Parser for instructions.md with enhanced step extraction"""
    
    # Patterns
    SCENARIO_HEADING = re.compile(r"^###\s+(.*)")
    METADATA_START = re.compile(r"^<!--\s*$")
    METADATA_END = re.compile(r"^-->\s*$")
    METADATA_FIELD = re.compile(r"^-\s*(\w+):\s*(.*)$")
    CODE_BLOCK_START = re.compile(r"^```(kusto|sql|kql)?\s*$", re.IGNORECASE)
    CODE_BLOCK_END = re.compile(r"^```\s*$")
    STEP_HEADING = re.compile(r"^\*\*Step\s+(\d+):\s+(.*?)\*\*", re.IGNORECASE)
    PURPOSE_COMMENT = re.compile(r"^//\s*Purpose:\s*(.*)", re.IGNORECASE)
    PLACEHOLDER_PATTERN = re.compile(r"<([A-Za-z][A-Za-z0-9_]*)>")
    CRITICAL_SECTION = re.compile(r"^\*\*CRITICAL", re.IGNORECASE)
    EXECUTION_SECTION = re.compile(r"^\*\*EXECUTION\s+INSTRUCTIONS", re.IGNORECASE)
    OUTPUT_FORMAT_SECTION = re.compile(r"^\*\*Output\s+Format", re.IGNORECASE)
    
    def __init__(self):
        self.scenarios: List[Scenario] = []
    
    def parse_file(self, file_path: Path) -> List[Scenario]:
        """Parse instructions.md file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return self.parse_content(content)
    
    def parse_content(self, content: str) -> List[Scenario]:
        """Parse markdown content into structured scenarios"""
        self.scenarios = []
        lines = content.splitlines()
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for scenario headings
            if self.SCENARIO_HEADING.match(line):
                scenario, next_i = self._parse_scenario(lines, i)
                if scenario and scenario.steps:  # Only add if it has queries
                    self.scenarios.append(scenario)
                i = next_i
            else:
                i += 1
        
        return self.scenarios
    
    def _parse_scenario(self, lines: List[str], start_idx: int) -> Tuple[Optional[Scenario], int]:
        """Parse a single scenario starting at given index"""
        # Extract title
        title_match = self.SCENARIO_HEADING.match(lines[start_idx])
        if not title_match:
            return None, start_idx + 1
        
        title = title_match.group(1).strip()
        
        # Initialize scenario with defaults
        scenario_data = {
            "slug": self._generate_slug(title),
            "title": title,
            "domain": "",
            "keywords": [],
            "required_identifiers": [],
            "aliases": [],
            "description": "",
            "critical_requirements": [],
            "steps": [],
            "output_format": OutputFormat()
        }
        
        i = start_idx + 1
        in_metadata = False
        in_code_block = False
        in_critical = False
        in_execution = False
        in_output_format = False
        code_lines: List[str] = []
        current_step: Optional[Dict] = None
        current_step_number: Optional[int] = None
        description_lines: List[str] = []
        
        # Parse until next scenario or end
        while i < len(lines):
            line = lines[i]
            
            # Stop at next scenario
            if self.SCENARIO_HEADING.match(line):
                break
            
            # Metadata block
            if self.METADATA_START.match(line):
                in_metadata = True
                i += 1
                continue
            
            if self.METADATA_END.match(line) and in_metadata:
                in_metadata = False
                i += 1
                continue
            
            if in_metadata:
                meta_match = self.METADATA_FIELD.match(line.strip())
                if meta_match:
                    field = meta_match.group(1).lower()
                    value = meta_match.group(2).strip()
                    
                    if field == "slug":
                        scenario_data["slug"] = value
                    elif field == "domain":
                        scenario_data["domain"] = value
                    elif field == "keywords":
                        scenario_data["keywords"] = [k.strip() for k in value.split(",")]
                    elif field == "required_identifiers":
                        scenario_data["required_identifiers"] = [k.strip() for k in value.split(",")]
                    elif field == "aliases":
                        scenario_data["aliases"] = [k.strip() for k in value.split(",")]
                    elif field == "description":
                        scenario_data["description"] = value
                i += 1
                continue
            
            # Check for CRITICAL section
            if self.CRITICAL_SECTION.match(line):
                in_critical = True
                i += 1
                continue
            
            # Check for EXECUTION INSTRUCTIONS section
            if self.EXECUTION_SECTION.match(line):
                in_execution = True
                in_critical = False
                i += 1
                continue
            
            # Check for OUTPUT FORMAT section
            if self.OUTPUT_FORMAT_SECTION.match(line):
                in_output_format = True
                in_execution = False
                i += 1
                continue
            
            # Collect critical requirements
            if in_critical and line.strip().startswith(("-", "*", "•")):
                requirement = line.strip().lstrip("-*•").strip()
                if requirement:
                    scenario_data["critical_requirements"].append(requirement)
                i += 1
                continue
            
            # Check for step headings
            step_match = self.STEP_HEADING.match(line)
            if step_match:
                # Save previous step if it exists
                if current_step:
                    if current_step.get("query_text"):
                        current_step["placeholders"] = self._extract_placeholders(current_step["query_text"])
                    scenario_data["steps"].append(QueryStep(**current_step))
                
                # Start new step
                current_step_number = int(step_match.group(1))
                step_title = step_match.group(2).strip()
                
                current_step = {
                    "step_number": current_step_number,
                    "title": step_title,
                    "purpose": "",
                    "query_id": f"{scenario_data['slug']}_step{current_step_number}",
                    "query_text": "",
                    "placeholders": {},
                    "extracts": {},
                    "provides_for_steps": [],
                    "optional": "optional" in step_title.lower()
                }
                code_lines = []  # Reset for next code block
                i += 1
                continue
            
            # Code block handling - check END first if already in code block
            if in_code_block and self.CODE_BLOCK_END.match(line):
                in_code_block = False
                # Assign code block to current step immediately
                if current_step and code_lines:
                    current_step["query_text"] = "\n".join(code_lines).strip()
                code_lines = []
                i += 1
                continue
            
            if self.CODE_BLOCK_START.match(line) and not in_metadata and not in_code_block:
                in_code_block = True
                code_lines = []
                
                # If there's no current step, create an implicit one
                if not current_step:
                    implicit_step_number = len(scenario_data["steps"]) + 1
                    current_step = {
                        "step_number": implicit_step_number,
                        "title": title,  # Use scenario title
                        "purpose": "",
                        "query_id": f"{scenario_data['slug']}_step{implicit_step_number}",
                        "query_text": "",
                        "placeholders": {},
                        "extracts": {},
                        "provides_for_steps": [],
                        "optional": False
                    }
                
                i += 1
                continue
            
            if in_code_block:
                # Check for purpose comment
                purpose_match = self.PURPOSE_COMMENT.match(line)
                if purpose_match and current_step:
                    current_step["purpose"] = purpose_match.group(1).strip()
                else:
                    code_lines.append(line)
                i += 1
                continue
            
            # Collect description lines (before first step)
            if not current_step and line.strip() and not in_metadata:
                description_lines.append(line.strip())
            
            i += 1
        
        # Save last step
        if current_step:
            if current_step.get("query_text"):
                current_step["placeholders"] = self._extract_placeholders(current_step["query_text"])
            scenario_data["steps"].append(QueryStep(**current_step))
        
        # Set description if not in metadata
        if not scenario_data["description"] and description_lines:
            scenario_data["description"] = " ".join(description_lines)
        
        # Create scenario
        try:
            scenario = Scenario(**scenario_data)
            return scenario, i
        except Exception as e:
            print(f"Error creating scenario {title}: {e}")
            return None, i
    
    def _generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title"""
        slug = title.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug
    
    def _extract_placeholders(self, query_text: str) -> Dict[str, Placeholder]:
        """Extract placeholders from query text"""
        placeholders = {}
        
        for match in self.PLACEHOLDER_PATTERN.finditer(query_text):
            placeholder_name = match.group(1)
            
            if placeholder_name not in placeholders:
                # Infer type from name
                placeholder_type = self._infer_placeholder_type(placeholder_name)
                
                placeholders[placeholder_name] = Placeholder(
                    name=placeholder_name,
                    type=placeholder_type,
                    required=True,
                    description=f"{placeholder_name} value",
                    example=None,
                    format_hint=None
                )
        
        return placeholders
    
    def _infer_placeholder_type(self, name: str) -> PlaceholderType:
        """Infer placeholder type from its name"""
        name_lower = name.lower()
        
        if "id" in name_lower and "list" not in name_lower:
            return PlaceholderType.GUID
        elif "list" in name_lower:
            return PlaceholderType.GUID_LIST
        elif "time" in name_lower or "date" in name_lower:
            return PlaceholderType.DATETIME
        elif "count" in name_lower or "limit" in name_lower:
            return PlaceholderType.INTEGER
        else:
            return PlaceholderType.STRING


def parse_instructions(file_path: str) -> List[Scenario]:
    """Convenience function to parse instructions.md"""
    parser = InstructionsParser()
    return parser.parse_file(Path(file_path))
