"""
Scenario Lookup Service

This service provides efficient lookup of scenarios from instructions.md
without loading the entire file into the agent's system prompt.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from services.instructions_parser import parse_instructions

logger = logging.getLogger(__name__)

@dataclass
class ScenarioInfo:
    """Lightweight scenario information for lookup"""
    title: str
    keywords: Set[str]
    description_summary: str
    has_queries: bool

@dataclass
class DetailedScenario:
    """Full scenario information with queries"""
    title: str
    description: str
    queries: List[str]
    keywords: Set[str]

class ScenarioLookupService:
    """Service for looking up scenarios from instructions.md efficiently"""
    
    def __init__(self, instructions_path: Path):
        self.instructions_path = instructions_path
        self.scenarios_index: Dict[str, DetailedScenario] = {}
        self.scenario_lookup: Dict[str, ScenarioInfo] = {}
        self.keyword_index: Dict[str, Set[str]] = {}  # keyword -> set of scenario titles
        self._load_scenarios()
    
    def _load_scenarios(self) -> None:
        """Load and index scenarios from instructions.md"""
        try:
            with open(self.instructions_path, encoding='utf-8') as f:
                content = f.read()
            
            parsed_scenarios = parse_instructions(content)
            logger.info(f"Parsed {len(parsed_scenarios)} scenarios from instructions.md")
            
            for scenario_data in parsed_scenarios:
                title = scenario_data['title']
                description = scenario_data['description']
                queries = scenario_data['queries']
                
                # Extract keywords from title and description
                keywords = self._extract_keywords(title, description)
                
                # Create detailed scenario
                detailed_scenario = DetailedScenario(
                    title=title,
                    description=description,
                    queries=queries,
                    keywords=keywords
                )
                
                # Create scenario info for lightweight lookup
                scenario_info = ScenarioInfo(
                    title=title,
                    keywords=keywords,
                    description_summary=self._create_summary(description),
                    has_queries=len(queries) > 0
                )
                
                # Index by normalized title
                normalized_title = self._normalize_title(title)
                self.scenarios_index[normalized_title] = detailed_scenario
                self.scenario_lookup[normalized_title] = scenario_info
                
                # Index keywords
                for keyword in keywords:
                    if keyword not in self.keyword_index:
                        self.keyword_index[keyword] = set()
                    self.keyword_index[keyword].add(normalized_title)
                    
                logger.debug(f"Indexed scenario '{title}' with keywords: {keywords}")
                
        except FileNotFoundError:
            logger.error(f"Instructions file not found: {self.instructions_path}")
        except Exception as e:
            logger.error(f"Error loading scenarios: {e}")
    
    def _extract_keywords(self, title: str, description: str) -> Set[str]:
        """Extract relevant keywords from title and description"""
        text = f"{title} {description}".lower()
        
        # Core domain keywords
        domain_keywords = {
            'device', 'devices', 'compliance', 'compliant', 'policy', 'policies',
            'application', 'applications', 'app', 'apps', 'group', 'groups',
            'tenant', 'user', 'users', 'enrollment', 'autopilot', 'mam',
            'effective', 'assignment', 'assignments', 'status', 'details',
            'troubleshooting', 'investigation', 'timeline', 'kusto', 'query',
            # Add specific technical keywords
            'dcv1', 'dcv2', 'conflict', 'conflicts', 'conflicting',
            'esp', 'jamf', 'third', 'party', 'integration',
            'setting', 'settings', 'payload', 'payloads',
            'identify', 'intune', 'ztd', 'autopilot'
        }
        
        # Extract keywords present in the text
        found_keywords = set()
        for keyword in domain_keywords:
            if keyword in text:
                found_keywords.add(keyword)
        
        # Add ALL title words as keywords (not just >2 chars to capture dcv1, dcv2, id, etc.)
        title_words = set(word.strip('.,!?()[]{}').lower() 
                         for word in title.split() 
                         if len(word) > 1 and (word.isalpha() or word.isalnum()))
        found_keywords.update(title_words)
        
        # Extract compound technical terms (e.g., "dcv1_v_dcv2", "policy_conflicts")
        # Split on common separators and add both compound and parts
        for separator in ['/', '_', '-', ' and ', ' vs ']:
            if separator in text:
                parts = text.split(separator)
                for part in parts:
                    cleaned = part.strip('.,!?()[]{}').lower()
                    if len(cleaned) > 1:
                        found_keywords.add(cleaned)
        
        return found_keywords
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for consistent lookup"""
        return title.lower().strip().replace(' ', '_').replace('/', '_')
    
    def _create_summary(self, description: str) -> str:
        """Create a brief summary of the description"""
        if not description:
            return "No description available"
        
        # Take first sentence or first 100 characters
        sentences = description.split('.')
        if sentences and len(sentences[0]) <= 100:
            return sentences[0].strip() + '.'
        else:
            return description[:100].strip() + '...'
    
    def get_scenario_summary(self) -> str:
        """Get a concise summary of all available scenarios for the system prompt"""
        if not self.scenario_lookup:
            return "No scenarios available"
        
        summary_lines = ["Available diagnostic scenarios:"]
        
        for scenario_info in self.scenario_lookup.values():
            keywords_str = ', '.join(sorted(list(scenario_info.keywords))[:5])  # Show first 5 keywords
            summary_lines.append(
                f"- **{scenario_info.title}**: {scenario_info.description_summary} "
                f"(Keywords: {keywords_str})"
            )
        
        summary_lines.append("\nTo use a scenario, reference it by title or relevant keywords.")
        return '\n'.join(summary_lines)
    
    def find_scenarios_by_keywords(self, user_input: str, max_results: int = 3) -> List[str]:
        """Find scenario titles that match keywords in user input"""
        user_input_lower = user_input.lower()
        
        # Extract words from user input (handle underscores, hyphens, and slashes)
        user_words = set()
        for separator in [' ', '_', '-', '/']:
            for word in user_input_lower.split(separator):
                cleaned = word.strip('.,!?()[]{}').lower()
                if len(cleaned) > 1:
                    user_words.add(cleaned)
        
        # Score scenarios by keyword matches
        scenario_scores = {}
        
        # Check all scenarios for matches
        for normalized_title, scenario_info in self.scenario_lookup.items():
            score = 0
            actual_title = scenario_info.title
            title_lower = actual_title.lower()
            
            # Highest priority: Exact title match or very close match
            if title_lower in user_input_lower or user_input_lower in title_lower:
                score += 20
            
            # High priority: Multiple title words match
            title_words = set()
            for separator in [' ', '_', '-', '/']:
                for word in actual_title.split(separator):
                    cleaned = word.lower().strip('.,!?()[]{}')
                    if len(cleaned) > 1:
                        title_words.add(cleaned)
            
            matching_title_words = title_words.intersection(user_words)
            if matching_title_words:
                score += len(matching_title_words) * 10
            
            # Medium priority: Keyword matches
            for word in user_words:
                if word in scenario_info.keywords:
                    score += 5
            
            # Lower priority: Partial keyword matches (substring matching)
            for word in user_words:
                for keyword in scenario_info.keywords:
                    if len(word) > 2 and (word in keyword or keyword in word):
                        score += 2
            
            # Bonus: Technical term matches (dcv1, dcv2, esp, etc.)
            technical_terms = {'dcv1', 'dcv2', 'esp', 'ztd', 'jamf', 'mam', 'conflict', 'conflicts'}
            for term in technical_terms:
                if term in user_words and term in scenario_info.keywords:
                    score += 15  # High priority for technical terms
            
            # Store score if any matches found
            if score > 0:
                scenario_scores[normalized_title] = score
                logger.debug(f"Scenario '{actual_title}' scored {score} for query '{user_input}'")
        
        # Sort by score and return top matches
        sorted_scenarios = sorted(scenario_scores.items(), key=lambda x: x[1], reverse=True)
        top_titles = [title for title, score in sorted_scenarios[:max_results]]
        
        if top_titles:
            logger.info(f"Top matches for '{user_input}': {[self.scenario_lookup[t].title for t in top_titles]}")
        
        return top_titles
    
    def get_scenario_by_title(self, title: str) -> Optional[DetailedScenario]:
        """Get full scenario details by title"""
        normalized = self._normalize_title(title)
        return self.scenarios_index.get(normalized)
    
    def get_scenarios_by_titles(self, titles: List[str]) -> List[DetailedScenario]:
        """Get multiple scenarios by their titles"""
        scenarios = []
        for title in titles:
            scenario = self.get_scenario_by_title(title)
            if scenario:
                scenarios.append(scenario)
        return scenarios
    
    def list_all_scenario_titles(self) -> List[str]:
        """Get list of all available scenario titles"""
        return [scenario.title for scenario in self.scenario_lookup.values()]

# Global service instance
_scenario_service: Optional[ScenarioLookupService] = None

def get_scenario_service() -> ScenarioLookupService:
    """Get the global scenario lookup service instance"""
    global _scenario_service
    if _scenario_service is None:
        instructions_path = Path(__file__).parent.parent.parent / "instructions.md"
        _scenario_service = ScenarioLookupService(instructions_path)
    return _scenario_service

def reload_scenarios() -> None:
    """Reload scenarios (useful for development/testing)"""
    global _scenario_service
    _scenario_service = None
    get_scenario_service()