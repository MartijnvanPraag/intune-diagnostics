"""
Semantic search for diagnostic scenarios using local embeddings

This module provides semantic search over instructions.md scenarios using
FAISS (Facebook AI Similarity Search) for fast local vector search.

Unlike the keyword-based approach, this uses embeddings to understand
semantic meaning, so "policy_conflicts_dcv1_v_dcv2" naturally matches
"Identify conflicting DCv1 and DCv2 policies".
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

@dataclass
class ScenarioChunk:
    """A scenario chunk with its content and metadata"""
    title: str
    content: str
    section_type: str  # "title", "description", "query", "full"
    normalized_title: str


class SemanticScenarioSearch:
    """Semantic search over diagnostic scenarios in instructions.md"""
    
    def __init__(self, instructions_path: Path):
        """Initialize semantic search with instructions.md"""
        self.instructions_path = instructions_path
        self.chunks: List[ScenarioChunk] = []
        self._embeddings = None
        self._vectorstore = None
        self._initialized = False
        
    def _parse_scenarios(self) -> List[ScenarioChunk]:
        """Parse instructions.md into searchable chunks"""
        try:
            content = self.instructions_path.read_text(encoding='utf-8')
            chunks = []
            
            # Split by scenario headings (### headings)
            scenario_pattern = re.compile(r'^###\s+(.+?)$', re.MULTILINE)
            scenarios = re.split(scenario_pattern, content)
            
            # Process scenario pairs (title, content)
            for i in range(1, len(scenarios), 2):
                if i + 1 >= len(scenarios):
                    break
                    
                title = scenarios[i].strip()
                content_text = scenarios[i + 1].strip()
                
                # Skip non-scenario sections
                if not content_text or len(content_text) < 50:
                    continue
                
                normalized_title = title.lower().replace(' ', '_').replace('/', '_').replace('-', '_')
                normalized_title = re.sub(r'[^\w_]', '', normalized_title)
                
                # Extract Kusto queries
                query_pattern = re.compile(r'```kusto\s*\n(.*?)\n```', re.DOTALL)
                queries = query_pattern.findall(content_text)
                
                # Extract description (text before first query)
                description_match = re.match(r'^(.*?)```', content_text, re.DOTALL)
                description = description_match.group(1).strip() if description_match else ""
                
                # Create searchable chunks
                # Chunk 1: Title + Description (most important for matching user queries)
                title_desc_content = f"Title: {title}\n\nDescription: {description}"
                chunks.append(ScenarioChunk(
                    title=title,
                    content=title_desc_content,
                    section_type="title_description",
                    normalized_title=normalized_title
                ))
                
                # Chunk 2: Full scenario (for comprehensive context)
                # Remove code blocks for better semantic matching
                content_no_code = re.sub(r'```kusto.*?```', '', content_text, flags=re.DOTALL)
                content_no_code = re.sub(r'\n\s*\n+', '\n\n', content_no_code).strip()
                
                full_content = f"Scenario: {title}\n\n{content_no_code}"
                chunks.append(ScenarioChunk(
                    title=title,
                    content=full_content,
                    section_type="full",
                    normalized_title=normalized_title
                ))
            
            logger.info(f"Parsed {len(chunks)} searchable chunks from {len(chunks) // 2} scenarios")
            return chunks
            
        except Exception as e:
            logger.error(f"Error parsing instructions.md: {e}")
            return []
    
    async def initialize(self):
        """Initialize embeddings and vector store (async for compatibility)"""
        if self._initialized:
            return
            
        try:
            # Import here to avoid startup delay if semantic search not used
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
            except ImportError:
                # Fallback to old import if new package not installed
                from langchain_community.embeddings import HuggingFaceEmbeddings
            
            from langchain_community.vectorstores import FAISS
            from langchain_core.documents import Document
            
            logger.info("Initializing semantic scenario search...")
            
            # Parse scenarios into chunks
            self.chunks = self._parse_scenarios()
            
            if not self.chunks:
                logger.warning("No scenarios found in instructions.md")
                return
            
            # Create embeddings model (using free local model)
            # all-MiniLM-L6-v2 is fast and good for semantic search
            self._embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},  # Use CPU for compatibility
                encode_kwargs={'normalize_embeddings': True}
            )
            
            # Create documents for FAISS
            documents = [
                Document(
                    page_content=chunk.content,
                    metadata={
                        "title": chunk.title,
                        "section_type": chunk.section_type,
                        "normalized_title": chunk.normalized_title
                    }
                )
                for chunk in self.chunks
            ]
            
            # Build FAISS index
            logger.info(f"Building FAISS index for {len(documents)} chunks...")
            self._vectorstore = FAISS.from_documents(documents, self._embeddings)
            
            self._initialized = True
            logger.info("Semantic scenario search initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize semantic search: {e}")
            logger.info("Falling back to keyword-based search")
            self._initialized = False
    
    def search(self, query: str, max_results: int = 3) -> List[str]:
        """Search for scenarios matching the query
        
        Args:
            query: Natural language query (e.g., "policy_conflicts_dcv1_v_dcv2")
            max_results: Maximum number of scenario titles to return
            
        Returns:
            List of normalized scenario titles matching the query
        """
        if not self._initialized or not self._vectorstore:
            logger.warning("Semantic search not initialized, returning empty results")
            return []
        
        try:
            # Search with similarity threshold
            # k=6 because we have 2 chunks per scenario, so we need more to get unique scenarios
            results = self._vectorstore.similarity_search(
                query, 
                k=min(max_results * 3, len(self.chunks))
            )
            
            # Deduplicate by normalized_title and preserve order
            seen_titles = set()
            unique_titles = []
            
            for doc in results:
                normalized_title = doc.metadata["normalized_title"]
                if normalized_title not in seen_titles:
                    seen_titles.add(normalized_title)
                    unique_titles.append(normalized_title)
                    
                    if len(unique_titles) >= max_results:
                        break
            
            # Log results for debugging
            scenario_titles = [
                doc.metadata["title"] 
                for doc in results[:max_results * 2]
            ]
            logger.info(f"Semantic search for '{query}' found: {scenario_titles[:5]}")
            
            return unique_titles
            
        except Exception as e:
            logger.error(f"Error during semantic search: {e}")
            return []


# Singleton instance
_semantic_search: SemanticScenarioSearch | None = None


async def get_semantic_search() -> SemanticScenarioSearch:
    """Get or create the semantic search instance"""
    global _semantic_search
    
    if _semantic_search is None:
        # Navigate from backend/services/ up to workspace root
        instructions_path = Path(__file__).parent.parent.parent / "instructions.md"
        _semantic_search = SemanticScenarioSearch(instructions_path)
        await _semantic_search.initialize()
    
    return _semantic_search
