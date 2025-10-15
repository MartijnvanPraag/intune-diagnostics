"""
Data models for structured instruction scenarios.

These models represent the structured format of scenarios, steps, and queries
parsed from instructions.md.
"""

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class PlaceholderType(str, Enum):
    """Types of placeholders in queries"""
    GUID = "guid"
    GUID_LIST = "guid_list"
    DATETIME = "datetime"
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"


class Placeholder(BaseModel):
    """Represents a placeholder in a query that needs substitution"""
    name: str = Field(..., description="Placeholder name (e.g., 'DeviceId')")
    type: PlaceholderType = Field(..., description="Type of the placeholder")
    required: bool = Field(True, description="Whether this placeholder is required")
    description: str = Field("", description="Human-readable description")
    example: Optional[str] = Field(None, description="Example value")
    format_hint: Optional[str] = Field(None, description="Format hint (e.g., 'comma_separated' for lists)")


class ExtractedValue(BaseModel):
    """Represents a value that should be extracted from query results"""
    name: str = Field(..., description="Name of the value to extract (e.g., 'DeviceId')")
    column: str = Field(..., description="Column name in results")
    description: str = Field("", description="What this value represents")
    extraction_method: str = Field("first", description="How to extract: 'first', 'all', 'unique'")


class QueryStep(BaseModel):
    """Represents a single step in a scenario with its query"""
    step_number: int = Field(..., description="Step number (1-based)")
    title: str = Field(..., description="Step title (e.g., 'Get Device Baseline Information')")
    purpose: str = Field("", description="Purpose/description of this step")
    query_id: str = Field(..., description="Unique query identifier")
    query_text: str = Field(..., description="Exact query text with placeholders")
    placeholders: Dict[str, Placeholder] = Field(default_factory=dict, description="Placeholders in this query")
    extracts: Dict[str, ExtractedValue] = Field(default_factory=dict, description="Values to extract from results")
    provides_for_steps: List[int] = Field(default_factory=list, description="Step numbers that use extracted values")
    rate_limit_rows: Optional[int] = Field(None, description="Row limit for rate limiting")
    optional: bool = Field(False, description="Whether this step is optional")


class OutputFormat(BaseModel):
    """Describes the expected output format for a scenario"""
    tables: List[str] = Field(default_factory=list, description="List of expected output tables")
    summary_includes: List[str] = Field(default_factory=list, description="What to include in summary")


class Scenario(BaseModel):
    """Represents a complete diagnostic scenario"""
    slug: str = Field(..., description="URL-friendly scenario identifier")
    title: str = Field(..., description="Scenario title")
    domain: str = Field("", description="Domain (device, user, application, etc.)")
    keywords: List[str] = Field(default_factory=list, description="Keywords for search")
    required_identifiers: List[str] = Field(default_factory=list, description="Required input identifiers")
    aliases: List[str] = Field(default_factory=list, description="Alternative names")
    description: str = Field("", description="Scenario description")
    execution_mode: Literal["sequential", "parallel", "conditional"] = Field("sequential", description="Execution mode")
    critical_requirements: List[str] = Field(default_factory=list, description="Critical requirements for execution")
    steps: List[QueryStep] = Field(default_factory=list, description="Steps to execute")
    output_format: OutputFormat = Field(default_factory=OutputFormat, description="Expected output format")
    
    def get_step(self, step_number: int) -> Optional[QueryStep]:
        """Get a step by number"""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None
    
    def get_query_by_id(self, query_id: str) -> Optional[QueryStep]:
        """Get a step by query ID"""
        for step in self.steps:
            if step.query_id == query_id:
                return step
        return None


class ScenarioSummary(BaseModel):
    """Lightweight summary of a scenario for search results"""
    slug: str
    title: str
    domain: str
    description: str
    required_identifiers: List[str]
    num_queries: int
    keywords: List[str]


class ValidationError(BaseModel):
    """Represents a validation error for a placeholder"""
    placeholder: str
    issue: str
    expected_format: Optional[str] = None


class ValidationResult(BaseModel):
    """Result of placeholder validation"""
    valid: bool
    errors: List[ValidationError] = Field(default_factory=list)


class SubstitutionResult(BaseModel):
    """Result of query substitution"""
    query_text: str
    placeholders_used: Dict[str, str]
    warnings: List[str] = Field(default_factory=list)
