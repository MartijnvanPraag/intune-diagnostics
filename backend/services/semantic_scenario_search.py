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
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from math import sqrt

logger = logging.getLogger(__name__)

@dataclass
class ScenarioChunk:
    """A scenario chunk with its content and metadata"""
    title: str
    content: str
    section_type: str  # "title", "description", "query", "full"
    normalized_title: str


def _normalize_title_key(title: str) -> str:
    """Normalize scenario titles to a consistent key.

    Steps:
    - lower
    - replace spaces, '/', '-' with underscore
    - strip any remaining non word / underscore chars (parentheses, punctuation)
    - collapse multiple underscores
    - trim leading/trailing underscores
    """
    t = title.lower().strip()
    t = t.replace(' ', '_').replace('/', '_').replace('-', '_')
    t = re.sub(r'[^(\w_)]', '', t)  # remove anything not word or underscore
    t = re.sub(r'[^\w_]', '', t)  # ensure all punctuation removed
    t = re.sub(r'_+', '_', t).strip('_')
    return t


class SemanticScenarioSearch:
    """Semantic search over diagnostic scenarios in instructions.md with hybrid scoring and disk cache.

    Enhancements:
    - Hybrid scoring: semantic cosine + lexical TF-IDF + bonuses (slug/exact phrase/technical tokens).
    - Placeholder extraction so agent can prompt for missing values.
    - Disk caching of parsed chunks + FAISS index + metadata hash to avoid rebuild on restart.
    - search_with_scores returns structured component scores enabling autonomous agent reasoning.
    """
    
    def __init__(self, instructions_path: Path):
        self.instructions_path = instructions_path
        self.cache_dir = instructions_path.parent / ".cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.index_hash_file = self.cache_dir / "scenario_index.meta.json"
        self.faiss_index_path = self.cache_dir / "scenario_index.faiss"
        self.chunks: List[ScenarioChunk] = []
        self._embeddings = None
        self._vectorstore = None
        self._initialized = False
    # Lexical stats
        self._scenario_docs: Dict[str, str] = {}  # normalized_title -> doc text
        self._tf: Dict[str, Dict[str, int]] = {}  # normalized_title -> term -> freq
        self._df: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._placeholders: Dict[str, List[str]] = {}  # normalized_title -> placeholders
        # Full scenario metadata (title, description, queries)
        self._scenario_map: Dict[str, Dict[str, Any]] = {}
        
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
    
    def _compute_hash(self) -> str:
        try:
            raw = self.instructions_path.read_bytes()
            return hashlib.sha256(raw).hexdigest()
        except Exception:
            return ""

    def _extract_placeholders(self, text: str) -> List[str]:
        raw = re.findall(r"<([^<>]+?)>", text)
        cleaned: List[str] = []
        for r in raw:
            # Trim guidance fragments like " from Step 1"
            c = r.strip()
            c = re.sub(r"\s+from\s+Step.*$", "", c, flags=re.IGNORECASE)
            if c and c not in cleaned:
                cleaned.append(c)
        return cleaned

    def _build_lexical(self):
        term_pattern = re.compile(r"[a-zA-Z0-9_]+")
        for chunk in self.chunks:
            nt = chunk.normalized_title
            if nt not in self._scenario_docs:
                self._scenario_docs[nt] = chunk.content.lower()
            # Only build lexical once per scenario (use title_description chunk preference)
            if chunk.section_type != "title_description":
                continue
            terms = term_pattern.findall(chunk.content.lower())
            tf: Dict[str, int] = {}
            for t in terms:
                tf[t] = tf.get(t, 0) + 1
            self._tf[nt] = tf
            for t in tf.keys():
                self._df[t] = self._df.get(t, 0) + 1
            # Aggregate placeholders from all queries/descriptions inside chunk
            phs = self._extract_placeholders(chunk.content)
            if phs:
                self._placeholders[nt] = phs
        N = max(len(self._tf), 1)
        import math
        for term, df in self._df.items():
            self._idf[term] = math.log((N + 1) / (df + 1)) + 1.0

    def _lexical_vector(self, text: str) -> Dict[str, float]:
        term_pattern = re.compile(r"[a-zA-Z0-9_]+")
        terms = term_pattern.findall(text.lower())
        counts: Dict[str, int] = {}
        for t in terms:
            counts[t] = counts.get(t, 0) + 1
        vec: Dict[str, float] = {}
        for t, c in counts.items():
            idf = self._idf.get(t)
            if idf:
                vec[t] = c * idf
        return vec

    def _cosine(self, v1: Dict[str, float], v2: Dict[str, float]) -> float:
        if not v1 or not v2:
            return 0.0
        dot = 0.0
        for k, v in v1.items():
            if k in v2:
                dot += v * v2[k]
        n1 = sqrt(sum(v*v for v in v1.values()))
        n2 = sqrt(sum(v*v for v in v2.values()))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)

    async def initialize(self):
        if self._initialized:
            return
        try:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
            except ImportError:
                from langchain_community.embeddings import HuggingFaceEmbeddings
            from langchain_community.vectorstores import FAISS
            from langchain_core.documents import Document
            # Parse full scenarios (with queries) first for semantic-only mode support
            try:
                from services.instructions_parser import parse_instructions
                full_parsed = parse_instructions(self.instructions_path.read_text(encoding='utf-8'))
                for sc in full_parsed:
                    norm = _normalize_title_key(sc['title'])
                    self._scenario_map[norm] = sc
            except Exception as p_err:  # noqa: BLE001
                logger.warning(f"Failed to build full scenario map: {p_err}")

            current_hash = self._compute_hash()
            use_cache = False
            if self.index_hash_file.exists() and self.faiss_index_path.exists():
                try:
                    meta = json.loads(self.index_hash_file.read_text())
                    if meta.get("hash") == current_hash:
                        use_cache = True
                        logger.info("Loading semantic scenario search from cache")
                except Exception:
                    pass

            if use_cache:
                # Rebuild minimal structures even if FAISS reused
                self.chunks = self._parse_scenarios()
                self._embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
                # Load FAISS index
                self._vectorstore = FAISS.load_local(
                    folder_path=str(self.cache_dir),
                    embeddings=self._embeddings,
                    index_name="scenario_index",
                    allow_dangerous_deserialization=True
                )
            else:
                logger.info("Initializing semantic scenario search (fresh build)...")
                self.chunks = self._parse_scenarios()
                if not self.chunks:
                    logger.warning("No scenarios found in instructions.md")
                    return
                self._embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
                documents = [
                    Document(
                        page_content=chunk.content,
                        metadata={
                            "title": chunk.title,
                            "section_type": chunk.section_type,
                            "normalized_title": chunk.normalized_title
                        }
                    ) for chunk in self.chunks
                ]
                from langchain_community.vectorstores import FAISS as FAISSClass
                self._vectorstore = FAISSClass.from_documents(documents, self._embeddings)
                # Persist
                self._vectorstore.save_local(str(self.cache_dir), index_name="scenario_index")
                self.index_hash_file.write_text(json.dumps({"hash": current_hash}), encoding='utf-8')

            # Build lexical stats & placeholders
            self._build_lexical()
            self._initialized = True
            logger.info("Semantic scenario search initialized successfully (hybrid-ready)")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to initialize semantic search: {e}")
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

    def search_with_scores(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Hybrid scoring variant returning component scores and placeholders.

        Returns a list sorted by final score desc.
        Scoring Components:
        - semantic: FAISS similarity (normalized heuristic via 1/(1+d)).
        - lexical: TF-IDF cosine between query and title/description chunk.
        - bonuses:
            * slug: query directly contains normalized slug.
            * all_title_tokens: every token in the title appears in query.
            * tech_terms: overlap with a curated technical term set.
            * title_token_overlap: partial overlap of meaningful (non-stopword) title tokens.
            * domain_anchor: NEW generalized boost – title contains one or more "salient" query tokens (rare across corpus).
        - penalties:
            * missing_placeholders: encourages filling placeholders early.
            * anchor_absent: slight penalty when query has salient anchors but title lacks any (lets anchored titles float up without hard exclusion).

        Generalization Rationale:
        Previously a compliance-specific boost existed; this was replaced by a neutral salient-token mechanism so ANY rare, explicit concept
        (e.g., autopilot, timeline, mam, dcv2) is favored when present in a title. This avoids hardcoding domain labels while improving precision.
        """
        if not self._initialized or not self._vectorstore:
            return []
        # Broader initial candidate pool (3x) to reduce early pruning of concise scenarios
        base_titles = self.search(query, max_results=max_results * 3)
        if not base_titles:
            return []

        # Build semantic score map via direct similarity_search_with_score
        semantic_scores: Dict[str, float] = {}
        try:
            # Underlying FAISS wrapper may expose similarity_search_with_score
            results = self._vectorstore.similarity_search_with_score(query, k=min(len(self.chunks), max_results * 6))
            for doc, score in results:
                nt = doc.metadata["normalized_title"]
                # Convert distance to similarity if needed (FAISS sometimes returns distance)
                # Here we assume smaller score => closer; transform via 1 / (1 + d)
                sim = 1.0 / (1.0 + score) if score >= 0 else 0.0
                prev = semantic_scores.get(nt, 0.0)
                if sim > prev:
                    semantic_scores[nt] = sim
        except Exception:
            # Fallback: assign descending semantics to base_titles
            for i, nt in enumerate(base_titles):
                semantic_scores[nt] = 1.0 - (i * 0.05)

        query_vec = self._lexical_vector(query)
        results_out: List[Tuple[str, Dict[str, Any]]] = []
        technical_terms = {"dcv1", "dcv2", "esp", "ztd", "autopilot", "timeline"}
        q_lower = query.lower()
        q_terms = set(re.findall(r"[a-zA-Z0-9_]+", q_lower))

        # Lightweight stopword set for title token overlap (kept deliberately small)
        stopwords = {"the", "and", "of", "for", "to", "in", "last", "days"}
        # Generalized anchor logic: determine salient query tokens (not stopwords, appear <=2 times across all scenario titles)
        # Build a lightweight global token frequency map lazily (from existing scenario docs)
        global_token_freq: Dict[str, int] = {}
        for doc in self._scenario_docs.values():
            for tok in re.findall(r"[a-zA-Z0-9_]+", doc):
                global_token_freq[tok] = global_token_freq.get(tok, 0) + 1
        # Salient query tokens = tokens present in query that are relatively rare in corpus
        salient_query_tokens = {t for t in q_terms if global_token_freq.get(t, 0) <= 2 and len(t) > 3}
        for nt in set(base_titles):
            # Lexical score
            doc_tf = self._tf.get(nt, {})
            doc_vec: Dict[str, float] = {t: c * self._idf.get(t, 0.0) for t, c in doc_tf.items()}
            lexical = self._cosine(query_vec, doc_vec)
            semantic = semantic_scores.get(nt, 0.0)

            bonuses: Dict[str, float] = {}
            penalties: Dict[str, float] = {}

            title_tokens = set(nt.split('_'))
            if nt in q_lower:
                bonuses['slug'] = 0.30
            if title_tokens and title_tokens.issubset(q_terms):
                bonuses['all_title_tokens'] = bonuses.get('all_title_tokens', 0.0) + 0.15
            tech_overlap = technical_terms.intersection(q_terms)
            if tech_overlap:
                bonuses['tech_terms'] = min(0.10 * len(tech_overlap), 0.30)

            # Title token overlap bonus (partial matches) – favors concise domain names like 'compliance'
            core_tokens = {t for t in title_tokens if t not in stopwords and len(t) > 2}
            overlap = core_tokens.intersection(q_terms)
            if overlap:
                bonuses['title_token_overlap'] = min(0.10 * len(overlap), 0.30)

            # Domain anchor boost (generalized): if a title contains a salient query token, reward it.
            salient_overlap = core_tokens.intersection(salient_query_tokens)
            if salient_overlap:
                # Scale bonus by number of overlaps, capped
                bonuses['domain_anchor'] = min(0.12 * len(salient_overlap), 0.30)
            else:
                # If query contains salient anchors but this title has none, apply a tiny penalty to let anchored ones float up
                if salient_query_tokens:
                    penalties['anchor_absent'] = penalties.get('anchor_absent', 0.0) - 0.03

            phs = self._placeholders.get(nt, [])
            missing_phs = [p for p in phs if p.lower() not in q_lower]
            if missing_phs:
                penalties['missing_placeholders'] = -0.05 * len(missing_phs)

            base = 0.55 * semantic + 0.30 * lexical
            total = base + sum(bonuses.values()) + sum(penalties.values())
            # Clamp
            total = max(0.0, min(1.0, total))

            results_out.append((nt, {
                'normalized_title': nt,
                'semantic': round(semantic, 4),
                'lexical': round(lexical, 4),
                'bonuses': bonuses,
                'penalties': penalties,
                'placeholders': phs,
                'missing_placeholders': missing_phs,
                'score': round(total, 4)
            }))

        ranked = sorted(results_out, key=lambda x: x[1]['score'], reverse=True)[:max_results]
        # Diagnostic logging when salient anchors present (helps debugging without hardcoding specific domains)
        if salient_query_tokens:
            debug_lines = [f"[semantic_scenario_search] Scoring for query '{query}' (salient={sorted(salient_query_tokens)}):"]
            for r in ranked:
                meta = r[1]
                debug_lines.append(f" - {meta['normalized_title']}: score={meta['score']} sem={meta['semantic']} lex={meta['lexical']} bonuses={meta['bonuses']} penalties={meta['penalties']}")
            logger.info("\n".join(debug_lines))
        return [r[1] for r in ranked]

    # -------- Scenario metadata access (semantic-only mode support) ---------
    def get_all_scenarios(self) -> List[Dict[str, Any]]:
        return list(self._scenario_map.values())

    def get_scenario_by_normalized(self, normalized: str) -> Optional[Dict[str, Any]]:
        # Direct lookup
        scen = self._scenario_map.get(normalized)
        if scen:
            if not scen.get('queries'):
                # Attempt one-time reparse to pick up newly added fallback extractions
                try:
                    from services.instructions_parser import parse_instructions as _p
                    full = _p(self.instructions_path.read_text(encoding='utf-8'))
                    for s in full:
                        k = _normalize_title_key(s['title'])
                        if k not in self._scenario_map:
                            self._scenario_map[k] = s
                        elif not self._scenario_map[k].get('queries') and s.get('queries'):
                            self._scenario_map[k] = s
                    scen = self._scenario_map.get(normalized) or scen
                except Exception as _rp:  # noqa: BLE001
                    logger.debug(f"[semantic_scenario_search] Reparse fallback failed: {_rp}")
            return scen
        # Fallback: attempt to re-normalize input and search tokens (handles older cached formats)
        alt = _normalize_title_key(normalized)
        if alt != normalized:
            scen = self._scenario_map.get(alt)
            if scen:
                return scen
        # Final fallback: token containment (rare path) – find first whose key without underscores matches
        import re as _re
        key_simple = _re.sub(r"[^a-z0-9]", "", normalized)
        for k, v in self._scenario_map.items():
            if _re.sub(r"[^a-z0-9]", "", k) == key_simple:
                return v
        return None

    def get_scenario_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        norm = title.lower().strip().replace(' ', '_').replace('/', '_')
        return self._scenario_map.get(norm)

    def build_summary(self, max_keywords: int = 5) -> str:
        lines = ["Available diagnostic scenarios (semantic index):"]
        for sc in self._scenario_map.values():
            desc = sc.get('description', '').split('\n')[0][:160]
            lines.append(f"- {sc.get('title')} : {desc}")
        return '\n'.join(lines) if len(lines) > 1 else "No scenarios indexed"


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
