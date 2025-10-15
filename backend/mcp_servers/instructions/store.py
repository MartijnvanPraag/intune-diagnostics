"""
Scenario store for managing parsed scenarios.

Provides in-memory storage with search capabilities.
"""

import re
from typing import List, Dict, Optional
from pathlib import Path

from .models import Scenario, ScenarioSummary, QueryStep
from .parser import parse_instructions


class ScenarioStore:
    """In-memory store for scenarios with search capabilities"""
    
    def __init__(self):
        self.scenarios: Dict[str, Scenario] = {}
        self._keyword_index: Dict[str, List[str]] = {}  # keyword -> [scenario_slugs]
    
    def load_from_file(self, file_path: str) -> int:
        """Load scenarios from instructions.md file"""
        scenarios = parse_instructions(file_path)
        
        for scenario in scenarios:
            self.add_scenario(scenario)
        
        return len(scenarios)
    
    def add_scenario(self, scenario: Scenario):
        """Add a scenario to the store"""
        self.scenarios[scenario.slug] = scenario
        
        # Index keywords for search
        all_keywords = scenario.keywords + [scenario.title.lower(), scenario.slug]
        if scenario.domain:
            all_keywords.append(scenario.domain.lower())
        
        # Also index aliases
        if hasattr(scenario, 'aliases') and scenario.aliases:
            all_keywords.extend([alias.lower() for alias in scenario.aliases])
        
        for keyword in all_keywords:
            keyword = keyword.strip().lower()
            if keyword not in self._keyword_index:
                self._keyword_index[keyword] = []
            if scenario.slug not in self._keyword_index[keyword]:
                self._keyword_index[keyword].append(scenario.slug)
    
    def search(self, query: str, domain: Optional[str] = None) -> List[ScenarioSummary]:
        """Search scenarios by keywords"""
        query_lower = query.lower().strip()
        query_words = re.findall(r'\w+', query_lower)
        
        # Normalize query for slug comparison (handle underscores, hyphens, spaces)
        normalized_query = query_lower.replace('_', '-').replace(' ', '-')
        
        # Score scenarios based on keyword matches
        scores: Dict[str, float] = {}
        
        for scenario_slug, scenario in self.scenarios.items():
            # Domain filter
            if domain and scenario.domain != domain:
                continue
            
            score = 0.0
            
            # PRIORITY 1: Exact slug match (highest priority)
            if query_lower == scenario.slug or normalized_query == scenario.slug:
                score += 100.0
            
            # PRIORITY 2: Exact alias match (very high priority)
            if hasattr(scenario, 'aliases') and scenario.aliases:
                for alias in scenario.aliases:
                    alias_lower = alias.lower().strip()
                    normalized_alias = alias_lower.replace('_', '-').replace(' ', '-')
                    if query_lower == alias_lower or normalized_query == normalized_alias:
                        score += 95.0  # Slightly less than exact slug match
                        break
            
            # PRIORITY 3: Slug contains query (high priority)
            if normalized_query in scenario.slug:
                score += 50.0
            
            # PRIORITY 4: Title contains query
            if query_lower in scenario.title.lower():
                score += 40.0
            
            # PRIORITY 5: Alias contains query
            if hasattr(scenario, 'aliases') and scenario.aliases:
                for alias in scenario.aliases:
                    if query_lower in alias.lower():
                        score += 35.0
                        break
            
            # PRIORITY 6: Keyword matches
            for keyword in scenario.keywords:
                if keyword.lower() in query_lower or query_lower in keyword.lower():
                    score += 20.0
            
            # PRIORITY 7: Description match
            if query_lower in scenario.description.lower():
                score += 10.0
            
            # PRIORITY 8: Word-by-word matching
            scenario_text = f"{scenario.title} {scenario.description} {' '.join(scenario.keywords)}".lower()
            for word in query_words:
                if word in scenario_text:
                    score += 5.0
            
            if score > 0:
                scores[scenario_slug] = score
        
        # Sort by score (descending)
        sorted_slugs = sorted(scores.keys(), key=lambda s: scores[s], reverse=True)
        
        # Return summaries
        return [self._make_summary(self.scenarios[slug]) for slug in sorted_slugs]
    
    def get_scenario(self, slug: str) -> Optional[Scenario]:
        """Get scenario by slug or alias"""
        # First try direct slug lookup
        if slug in self.scenarios:
            return self.scenarios[slug]
        
        # Try normalized slug (handle underscores, hyphens, spaces)
        normalized_slug = slug.lower().replace('_', '-').replace(' ', '-')
        for scenario_slug, scenario in self.scenarios.items():
            if normalized_slug == scenario_slug:
                return scenario
        
        # Try alias lookup
        slug_lower = slug.lower().strip()
        for scenario in self.scenarios.values():
            if hasattr(scenario, 'aliases') and scenario.aliases:
                for alias in scenario.aliases:
                    alias_lower = alias.lower().strip()
                    normalized_alias = alias_lower.replace('_', '-').replace(' ', '-')
                    if slug_lower == alias_lower or normalized_slug == normalized_alias:
                        return scenario
        
        return None
    
    def get_query_step(self, query_id: str) -> Optional[tuple[Scenario, QueryStep]]:
        """Get query step by ID (returns scenario and step)"""
        for scenario in self.scenarios.values():
            step = scenario.get_query_by_id(query_id)
            if step:
                return scenario, step
        return None
    
    def _make_summary(self, scenario: Scenario) -> ScenarioSummary:
        """Create scenario summary"""
        return ScenarioSummary(
            slug=scenario.slug,
            title=scenario.title,
            domain=scenario.domain,
            description=scenario.description[:200] + "..." if len(scenario.description) > 200 else scenario.description,
            required_identifiers=scenario.required_identifiers,
            num_queries=len(scenario.steps),
            keywords=scenario.keywords
        )
    
    def list_all_scenarios(self) -> List[ScenarioSummary]:
        """List all scenarios"""
        return [self._make_summary(s) for s in self.scenarios.values()]
