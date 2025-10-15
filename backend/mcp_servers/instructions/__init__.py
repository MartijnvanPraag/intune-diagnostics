"""
Instructions MCP Server

Provides structured access to diagnostic scenarios and Kusto queries from instructions.md.
"""

from .models import (
    Scenario, QueryStep, Placeholder, ExtractedValue, OutputFormat,
    ScenarioSummary, ValidationResult, SubstitutionResult,
    PlaceholderType
)
from .parser import InstructionsParser, parse_instructions
from .store import ScenarioStore

__all__ = [
    "Scenario", "QueryStep", "Placeholder", "ExtractedValue", "OutputFormat",
    "ScenarioSummary", "ValidationResult", "SubstitutionResult",
    "PlaceholderType",
    "InstructionsParser", "parse_instructions",
    "ScenarioStore"
]
