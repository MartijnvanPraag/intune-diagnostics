"""
Scenario Lookup Service

This service provides efficient lookup of scenarios from instructions.md
without loading the entire file into the agent's system prompt.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from services.instructions_parser import parse_instructions

logger = logging.getLogger(__name__)

@dataclass
class ScenarioInfo:
    """Lightweight scenario information for lookup"""
    title: str
    keywords: Set[str]
    description_summary: str
    has_queries: bool
    # Metadata fields
    slug: Optional[str] = None
    domain: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    required_identifiers: List[str] = field(default_factory=list)

@dataclass
class DetailedScenario:
    """Full scenario information with queries"""
    title: str
    description: str
    queries: List[str]
    keywords: Set[str]
    # Metadata fields
    slug: Optional[str] = None
    domain: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    required_identifiers: List[str] = field(default_factory=list)

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
                
                # Extract metadata from parsed data
                slug = scenario_data.get('slug')
                domain = scenario_data.get('domain')
                keywords_meta = scenario_data.get('keywords_meta', '')
                aliases_meta = scenario_data.get('aliases', '')
                required_ids_meta = scenario_data.get('required_identifiers', '')
                description_meta = scenario_data.get('description_meta', '')
                
                # Parse comma-separated lists
                aliases = [a.strip() for a in aliases_meta.split(',') if a.strip()] if aliases_meta else []
                required_identifiers = [r.strip() for r in required_ids_meta.split(',') if r.strip()] if required_ids_meta else []
                
                # Extract keywords - use metadata keywords if available, otherwise extract from text
                if keywords_meta:
                    # Use explicit metadata keywords (comma-separated)
                    meta_keywords = set(k.strip().lower() for k in keywords_meta.split(',') if k.strip())
                    # Also extract from title and description for backward compatibility
                    text_keywords = self._extract_keywords(title, description)
                    keywords = meta_keywords.union(text_keywords)
                else:
                    # Fall back to text extraction
                    keywords = self._extract_keywords(title, description)
                
                # Add slug and aliases as high-priority keywords
                if slug:
                    keywords.add(slug.lower())
                for alias in aliases:
                    keywords.update(alias.lower().split())
                
                # Create detailed scenario
                detailed_scenario = DetailedScenario(
                    title=title,
                    description=description,
                    queries=queries,
                    keywords=keywords,
                    slug=slug,
                    domain=domain,
                    aliases=aliases,
                    required_identifiers=required_identifiers
                )
                
                # Create scenario info for lightweight lookup
                summary = description_meta if description_meta else self._create_summary(description)
                scenario_info = ScenarioInfo(
                    title=title,
                    keywords=keywords,
                    description_summary=summary,
                    has_queries=len(queries) > 0,
                    slug=slug,
                    domain=domain,
                    aliases=aliases,
                    required_identifiers=required_identifiers
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
                
                # Index by slug if available
                if slug:
                    self.keyword_index[slug.lower()] = {normalized_title}
                    
                logger.debug(f"Indexed scenario '{title}' (slug: {slug}, domain: {domain}) with keywords: {keywords}")
                
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
        
        # Group scenarios by domain if available
        by_domain: Dict[str, List[ScenarioInfo]] = {}
        no_domain: List[ScenarioInfo] = []
        
        for scenario_info in self.scenario_lookup.values():
            if scenario_info.domain:
                domain = scenario_info.domain.capitalize()
                if domain not in by_domain:
                    by_domain[domain] = []
                by_domain[domain].append(scenario_info)
            else:
                no_domain.append(scenario_info)
        
        # Output grouped by domain
        for domain in sorted(by_domain.keys()):
            summary_lines.append(f"\n**{domain} Scenarios:**")
            for scenario_info in by_domain[domain]:
                slug_info = f" [{scenario_info.slug}]" if scenario_info.slug else ""
                aliases_info = f" (aliases: {', '.join(scenario_info.aliases)})" if scenario_info.aliases else ""
                summary_lines.append(f"- **{scenario_info.title}**{slug_info}{aliases_info}: {scenario_info.description_summary}")
        
        # Output scenarios without domain
        if no_domain:
            summary_lines.append("\n**Other Scenarios:**")
            for scenario_info in no_domain:
                slug_info = f" [{scenario_info.slug}]" if scenario_info.slug else ""
                aliases_info = f" (aliases: {', '.join(scenario_info.aliases)})" if scenario_info.aliases else ""
                summary_lines.append(f"- **{scenario_info.title}**{slug_info}{aliases_info}: {scenario_info.description_summary}")
        
        summary_lines.append("\nTo use a scenario, reference it by title, slug, alias, or relevant keywords.")
        return '\n'.join(summary_lines)
    
    def find_scenarios_by_keywords(self, user_input: str, max_results: int = 3) -> List[str]:
        """Find scenario titles that match keywords in user input
        
        Enhanced matching strategy:
        1. Exact slug match (highest priority)
        2. Exact alias match (very high priority)
        3. Domain match + keyword overlap (high priority)
        4. Title word matches (high priority)
        5. Keyword matches (medium priority)
        6. Technical term matches (high bonus)
        """
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
            
            # PRIORITY 1: Exact slug match (100 points - definitive match)
            if scenario_info.slug:
                slug_lower = scenario_info.slug.lower()
                if slug_lower == user_input_lower or slug_lower in user_input_lower:
                    score += 100
                    logger.info(f"Exact slug match for '{actual_title}': slug='{scenario_info.slug}'")
            
            # PRIORITY 2: Exact alias match (80 points - very high confidence)
            for alias in scenario_info.aliases:
                alias_lower = alias.lower()
                if alias_lower == user_input_lower or alias_lower in user_input_lower:
                    score += 80
                    logger.info(f"Alias match for '{actual_title}': alias='{alias}'")
                    break  # Only count once per scenario
            
            # PRIORITY 3: Exact title match (50 points)
            if title_lower in user_input_lower or user_input_lower in title_lower:
                score += 50
            
            # PRIORITY 4: Domain match + keyword overlap (bonus multiplier)
            domain_match = False
            if scenario_info.domain:
                domain_lower = scenario_info.domain.lower()
                if domain_lower in user_words or any(domain_lower in word for word in user_words):
                    domain_match = True
                    score += 25
            
            # PRIORITY 5: Title word matches (30 points each)
            title_words = set()
            for separator in [' ', '_', '-', '/']:
                for word in actual_title.split(separator):
                    cleaned = word.lower().strip('.,!?()[]{}')
                    if len(cleaned) > 1:
                        title_words.add(cleaned)
            
            matching_title_words = title_words.intersection(user_words)
            if matching_title_words:
                # Higher weight if domain also matches
                weight = 30 if not domain_match else 40
                score += len(matching_title_words) * weight
            
            # PRIORITY 6: Explicit metadata keyword matches (15 points each)
            # These are more valuable than derived keywords
            metadata_keywords = set()
            if hasattr(scenario_info, 'keywords'):
                for keyword in scenario_info.keywords:
                    if keyword in user_words:
                        metadata_keywords.add(keyword)
                        score += 15
            
            # PRIORITY 7: General keyword matches (8 points each)
            for word in user_words:
                if word in scenario_info.keywords and word not in metadata_keywords:
                    score += 8
            
            # PRIORITY 8: Partial keyword matches (5 points - substring matching)
            for word in user_words:
                if len(word) > 3:  # Only for longer words to avoid false positives
                    for keyword in scenario_info.keywords:
                        if word in keyword or keyword in word:
                            score += 5
                            break  # Only count once per user word
            
            # PRIORITY 9: Technical term bonuses (20 points each)
            technical_terms = {'dcv1', 'dcv2', 'esp', 'ztd', 'jamf', 'mam', 'conflict', 'conflicts', 
                             'autopilot', 'compliance', 'intune', 'kusto'}
            for term in technical_terms:
                if term in user_words and term in scenario_info.keywords:
                    score += 20
            
            # PRIORITY 10: Required identifiers bonus (if user mentions them)
            identifier_keywords = {'deviceid', 'userid', 'accountid', 'contextid', 'policyid', 
                                 'device', 'user', 'account', 'context', 'policy'}
            user_has_identifier = any(ik in user_input_lower for ik in identifier_keywords)
            if user_has_identifier and scenario_info.required_identifiers:
                # Small bonus if user's query suggests they have the required identifiers
                score += 5
            
            # Store score if any matches found
            if score > 0:
                scenario_scores[normalized_title] = score
                logger.debug(f"Scenario '{actual_title}' scored {score} for query '{user_input}'")
        
        # Sort by score and return top matches
        sorted_scenarios = sorted(scenario_scores.items(), key=lambda x: x[1], reverse=True)
        top_titles = [title for title, score in sorted_scenarios[:max_results]]
        
        if top_titles:
            top_scenarios_info = [(self.scenario_lookup[t].title, scenario_scores[t]) for t in top_titles]
            logger.info(f"Top matches for '{user_input}': {top_scenarios_info}")
        else:
            logger.warning(f"No matches found for query: '{user_input}'")
        
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