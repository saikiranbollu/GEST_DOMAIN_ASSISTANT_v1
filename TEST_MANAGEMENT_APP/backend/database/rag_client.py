"""
RAG (Retrieval Augmented Generation) Client
Queries ChromaDB for semantic collections across unlimited modules
Supports CXPI, LIN, BTL, SWA, and custom modules dynamically
ZERO HARDCODING: All module-specific values derived dynamically

INTELLIGENT SEMANTIC SEARCH:
- Uses sentence-transformers embeddings (local model: all-MiniLM-L6-v2)
- HNSW indexing for fast approximate nearest neighbor search
- Cosine similarity for vector distance (industry standard)
- NLP-based query expansion (intent extraction, synonyms, lemmatization, domain concepts)
- Understands indirect/implicit queries, not just keyword matching
"""

import json
import logging
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
import sqlite3
import struct
import numpy as np
import os
import hnswlib
from sentence_transformers import SentenceTransformer
import nltk
from nltk.corpus import wordnet
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

logger = logging.getLogger(__name__)

# Ensure NLTK data is available
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', quiet=True)
try:
    nltk.data.find('corpora/averaged_perceptron_tagger')
except LookupError:
    nltk.download('averaged_perceptron_tagger', quiet=True)


class RAGClient:
    """
    ChromaDB client for querying RAG collections
    
    DYNAMIC & SCALABLE: Works with any module (CXPI, LIN, BTL, SWA, etc.)
    ZERO HARDCODING: Collection names derived dynamically from module name
    
    For CXPI module, collections are: rag_cxpi_functions, rag_cxpi_enums, etc.
    For LIN module, collections are: rag_lin_functions, rag_lin_enums, etc.
    
    Collection naming pattern: rag_{module_lowercase}_{collection_type}
    
    Collection types supported:
    - functions: C/C++ function definitions
    - enums: Enumeration type definitions
    - structs: Struct/data structure definitions
    - requirements: System requirements & specs
    - hardware: Hardware specifications
    - registers: Register definitions
    - macros: Macro definitions
    - typedefs: Type definitions
    - source: Source code implementations
    - architecture: Architecture documentation
    - pattern_library: PUML design patterns
    
    CHUNK FETCHING STRATEGY (OPTIMIZED):
    - Functions: Top 8 chunks (comprehensive coverage)
    - Structs: Top 8 chunks (full type definitions)
    - Enums: Top 8 chunks (all enum variants)
    - Requirements: Top 8 chunks (complete requirements)
    - Hardware: Top 8 chunks (all hardware sections)
    - Registers: Top 8 chunks (register groups)
    - Pattern Library (PUML): ALL 8 chunks (complete, interconnected)
      * puml_core_functions
      * puml_phase_patterns
      * puml_sequence_patterns
      * puml_features
      * puml_function_dependencies
      * puml_loop_patterns
      * puml_data_variations
      * puml_channel_patterns
    
    RATIONALE:
    - Top 8 balances comprehensive coverage with performance
    - PUML chunks must be complete (all 8) due to interdependencies
    - Top 8 > Top 5 (more context) but < Top 10 (better performance)
    - PUML chunks are pre-chunked by section, so all 8 are needed
    """
    
    # DYNAMIC CHUNK FETCHING CONFIGURATION (NO HARDCODING)
    CHUNK_CONFIG = {
        # OPTIMIZED FOR RAG-PRIMARY FEATURE CLASSIFICATION (Jan 2026)
        # Only fetch essential chunks needed by new approach
        
        # ===================================================================
        # FOR FEATURE CLASSIFICATION (FeatureClassifier uses RAG PRIMARY)
        # ===================================================================
        # ONLY core_functions + phase_patterns needed (they come from pattern_library)
        
        'pattern_library_fetch_all': True,   # Fetch ALL 8 chunks (interconnected)
        'pattern_library_n_results': 8,      # All pattern library chunks
        'puml_patterns_n_results': 0,        # NOT USED (was: fetch all PUML chunks)
        
        # ===================================================================
        # FOR CODE GENERATION & CONTEXT (still needed for PHASE 6+ steps)
        # ===================================================================
        'functions_n_results': 10,           # Top 10 functions (RAG uses these as primary)
        'structs_n_results': 10,             # Top 10 structs (increased for better config struct coverage)
        'enums_n_results': 10,               # Top 10 enums (increased for enum value resolution)
        
        # ===================================================================
        # NOT USED ANYMORE (feature classification doesn't need these)
        # ===================================================================
        'default_n_results': 8,
        'requirements_n_results': 8,         # Top 8 requirements for traceability
        'hardware_n_results': 8,             # Top 8 hardware spec sections
        'registers_n_results': 8,            # Top 8 register definitions
        'macros_n_results': 5,               # Top 5 macros
        'typedefs_n_results': 5,             # Top 5 typedefs
    }
    
    def __init__(self, db_path: Optional[str] = None, module: Optional[str] = None):
        """
        Initialize RAG client
        
        Args:
            db_path: Path to ChromaDB directory (default: from env CHROMA_PATH or ../MCP_DB_INGESTION/output/chroma_data)
            module: Module name (default: from env MODULE_NAME)
                   Format: lowercase module name (e.g., "cxpi", "lin", "btl")
        
        DYNAMIC & SCALABLE: Zero hardcoding
        - Collections derived from module name: rag_{module_lowercase}_{collection_type}
        - Database path from environment or explicit parameter
        - Works with any module automatically
        """
        import os
        
        # Determine module name
        self.module_name = module or os.getenv("MODULE_NAME", "").lower()
        if not self.module_name:
            raise ValueError(
                "Must provide module name via one of:\n"
                "  1. module parameter: RAGClient(module='cxpi')\n"
                "  2. MODULE_NAME env var\n"
                "Module name should be lowercase (e.g., cxpi, lin, btl)"
            )
        
        # Determine ChromaDB path
        if db_path:
            self.db_path = Path(db_path)
        else:
            db_path_env = os.getenv("CHROMA_PATH")
            if db_path_env:
                self.db_path = Path(db_path_env)
            else:
                # Default: relative path from TEST_MANAGEMENT_APP to MCP_DB_INGESTION
                default_path = Path(__file__).parent.parent.parent.parent / "MCP_DB_INGESTION" / "output" / "chroma_data"
                self.db_path = default_path
        
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize with direct SQLite access
        self.sqlite_path = self.db_path / "chroma.sqlite3"
        self.client = None  # We'll use direct SQLite access
        
        try:
            logger.info(f"[RAG] Initializing RAG client for module '{self.module_name}' at {self.db_path}")
            # Verify database exists
            if not self.sqlite_path.exists():
                logger.error(f"[RAG-ERROR] Database not found at {self.sqlite_path}")
                raise FileNotFoundError(f"ChromaDB not found at {self.sqlite_path}")
        except Exception as e:
            logger.error(f"[RAG-ERROR] Failed to initialize RAG: {e}")
            raise
        
        # Load all collections info
        self.collections = self._load_collections()
        
        # Initialize sentence-transformer model for intelligent semantic search
        self._init_embedding_model()
        
        # Initialize HNSW indices for each collection (built on demand)
        self.hnsw_indices = {}  # {collection_key: {'index': hnswlib_index, 'embeddings': list, 'docs': list}}
    
    def _init_embedding_model(self):
        """Initialize sentence-transformer model from local cache"""
        try:
            # Try to load from local cache first
            local_model_path = Path(__file__).parent.parent.parent / "local_models" / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots" / "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
            
            if local_model_path.exists():
                logger.info(f"[RAG] Loading sentence-transformer from local cache: {local_model_path}")
                self.embedding_model = SentenceTransformer(str(local_model_path))
                logger.info(f"[RAG] ✓ Sentence-transformer loaded from local model ({self.embedding_model.get_sentence_embedding_dimension()} dims)")
                self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            else:
                # Fallback: download from HuggingFace
                logger.warning(f"[RAG-WARN] Local model not found at {local_model_path}, downloading from HuggingFace...")
                self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', cache_folder=str(Path(__file__).parent.parent.parent / "local_models"))
                logger.info(f"[RAG] ✓ Sentence-transformer downloaded and cached ({self.embedding_model.get_sentence_embedding_dimension()} dims)")
                self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        except Exception as e:
            logger.error(f"[RAG-ERROR] Failed to initialize embedding model: {e}")
            logger.error("[RAG-ERROR] Falling back to keyword-based search (reduced capability)")
            self.embedding_model = None
            self.embedding_dim = 0
    
    def _expand_query(self, query: str) -> str:
        """
        NLP-based query expansion to understand intent better
        Extracts meaning and context, not just keywords
        
        Techniques:
        1. Lemmatization: normalize words (e.g., "testing" -> "test", "channels" -> "channel")
        2. Synonym expansion: add related words (e.g., "send" -> "transmit", "receive", "fetch")
        3. Domain concept mapping: map abbreviations and jargon (e.g., "TX" -> "transmit", "RX" -> "receive")
        4. Intent extraction: identify the main action/concept
        
        Args:
            query: Original user query
            
        Returns:
            Expanded query with synonyms and normalized forms
        """
        try:
            lemmatizer = WordNetLemmatizer()
            
            # Domain-specific mappings (CXPI/automotive context)
            domain_map = {
                'tx': 'transmit', 'txn': 'transmit', 'transmission': 'transmit',
                'rx': 'receive', 'rcv': 'receive', 'reception': 'receive',
                'req': 'requirement', 'reqs': 'requirements',
                'init': 'initialize', 'initialization': 'initialize',
                'config': 'configuration', 'configure': 'configuration',
                'hw': 'hardware', 'reg': 'register', 'regs': 'registers',
                'param': 'parameter', 'params': 'parameters',
                'chan': 'channel', 'chans': 'channels',
                'err': 'error', 'errs': 'errors',
                'intr': 'interrupt', 'intrs': 'interrupts',
                'timeout': 'timeout_error', 'crc': 'crc_error', 'bit': 'bit_error',
                'test': 'test', 'validate': 'test', 'check': 'test',
                'send': 'transmit', 'submit': 'transmit', 'dispatch': 'transmit',
                'get': 'receive', 'fetch': 'receive', 'retrieve': 'receive',
            }
            
            # Tokenize and lemmatize
            tokens = word_tokenize(query.lower())
            normalized_tokens = []
            
            for token in tokens:
                # Check domain mapping first
                if token in domain_map:
                    normalized_tokens.append(domain_map[token])
                else:
                    # Lemmatize
                    lemma = lemmatizer.lemmatize(token)
                    normalized_tokens.append(lemma)
            
            # Add synonyms for key words
            expanded_words = set(normalized_tokens)
            for token in normalized_tokens:
                # Get synonyms from WordNet
                for syn in wordnet.synsets(token):
                    for lemma in syn.lemmas():
                        synonym = lemma.name().replace('_', ' ')
                        if synonym != token:
                            expanded_words.add(synonym)
            
            # Rebuild expanded query
            expanded_query = query + " " + " ".join(expanded_words)
            
            logger.debug(f"[RAG] Query expansion: '{query}' -> '{expanded_query[:100]}...'")
            return expanded_query
            
        except Exception as e:
            logger.warning(f"[RAG-WARN] Query expansion failed: {e}, using original query")
            return query
    
    def _build_hnsw_index(self, collection_key: str, embeddings: List[np.ndarray], max_elements: int = 10000) -> hnswlib.Index:
        """
        Build HNSW index for fast approximate nearest neighbor search
        
        HNSW = Hierarchical Navigable Small Worlds
        - Fast: O(log n) time complexity for insertion and search
        - Approximate: trade accuracy for speed (configurable ef parameter)
        - Memory-efficient: scales well with large collections
        
        Args:
            collection_key: Collection name (for caching)
            embeddings: List of embedding vectors (numpy arrays)
            max_elements: Maximum capacity of the index
            
        Returns:
            Initialized HNSW index
        """
        try:
            if embeddings is None or (isinstance(embeddings, np.ndarray) and embeddings.size == 0) or (isinstance(embeddings, list) and len(embeddings) == 0) or self.embedding_dim == 0:
                logger.warning(f"[RAG-WARN] Cannot build HNSW index: no embeddings or embedding_dim=0")
                return None
            
            # Create HNSW index
            index = hnswlib.Index(space='cosine', dim=self.embedding_dim)
            index.init_index(max_elements=max_elements, ef_construction=200, M=16)
            
            # Add embeddings - handle both list and numpy array inputs
            if isinstance(embeddings, np.ndarray):
                embeddings_array = embeddings.astype('float32')
            else:
                embeddings_array = np.array(embeddings, dtype='float32')
            
            # Add with IDs
            labels = np.arange(len(embeddings_array))
            index.add_items(embeddings_array, labels)
            
            # Set search parameter (ef controls speed vs accuracy tradeoff)
            index.set_ef(50)  # Higher ef = better accuracy but slower (default ~200)
            
            logger.info(f"[RAG] ✓ HNSW index built for '{collection_key}' ({len(embeddings_array)} items, {self.embedding_dim} dims)")
            return index
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Failed to build HNSW index: {e}")
            return None
    
    def _cosine_similarity_search(self, collection_key: str, query_embedding: np.ndarray, n_results: int = 8, use_hnsw: bool = True) -> List[Dict]:
        """
        Perform intelligent semantic search using cosine similarity
        
        COSINE SIMILARITY:
        - Metric: similarity = dot(a, b) / (||a|| * ||b||) ranges from -1 to 1
        - Interpretation: 1 = identical direction, 0 = orthogonal, -1 = opposite
        - Best for: normalized embeddings (sentence-transformers outputs are normalized)
        - Why better than keyword matching: captures semantic meaning, not just exact words
        
        Args:
            collection_key: Collection to search
            query_embedding: Query vector (from embedding model)
            n_results: Top N results to return
            use_hnsw: If True, use HNSW index (fast approximate). If False, brute-force (slow but exact).
            
        Returns:
            List of results with similarity scores
        """
        collection = self.collections.get(collection_key)
        if not collection:
            return []
        
        try:
            # Fetch all documents, metadata, and embeddings from ChromaDB
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Get documents and their text
            # FIXED: Documents are stored in METADATA segments, not VECTOR segments
            # VECTOR segments store HNSW index data on disk (.bin files)
            # METADATA segments store document text in embedding_metadata table
            cursor.execute("""
                SELECT em.string_value as doc_text, e.embedding_id
                FROM embedding_metadata em
                JOIN embeddings e ON em.id = e.id
                JOIN segments s ON e.segment_id = s.id
                WHERE s.collection = ? 
                  AND em.key = 'chroma:document'
                  AND s.type = 'urn:chroma:segment/metadata/sqlite'
            """, (collection['id'],))
            
            doc_records = cursor.fetchall()
            
            # Also fetch ALL user metadata (function name, struct name, type, etc.)
            # These were stored during ingestion via metadatas= parameter
            cursor.execute("""
                SELECT e.embedding_id, em.key, em.string_value
                FROM embedding_metadata em
                JOIN embeddings e ON em.id = e.id
                JOIN segments s ON e.segment_id = s.id
                WHERE s.collection = ? 
                  AND em.key != 'chroma:document'
                  AND s.type = 'urn:chroma:segment/metadata/sqlite'
                  AND em.string_value IS NOT NULL
            """, (collection['id'],))
            
            metadata_records = cursor.fetchall()
            conn.close()
            
            if not doc_records:
                logger.warning(f"[RAG-WARN] No documents found in collection '{collection_key}'")
                return []
            
            # Build metadata lookup: embedding_id -> {key: value, ...}
            metadata_by_id = {}
            for emb_id, meta_key, meta_value in metadata_records:
                if emb_id not in metadata_by_id:
                    metadata_by_id[emb_id] = {}
                metadata_by_id[emb_id][meta_key] = meta_value
            
            # Extract documents and text
            doc_texts = [rec[0] for rec in doc_records]
            doc_ids = [rec[1] for rec in doc_records]
            # Map each doc index to its metadata dict
            doc_metadata = [metadata_by_id.get(doc_id, {}) for doc_id in doc_ids]
            
            # Generate embeddings for all documents in collection
            logger.debug(f"[RAG] Embedding {len(doc_texts)} documents in collection '{collection_key}'...")
            doc_embeddings = self.embedding_model.encode(doc_texts, convert_to_numpy=True, show_progress_bar=False)
            doc_embeddings = doc_embeddings.astype('float32')
            
            # Ensure query embedding is float32
            query_embedding = np.array(query_embedding, dtype='float32')
            
            if use_hnsw and self.embedding_model:
                # Use HNSW index for fast search
                logger.debug(f"[RAG] Using HNSW for fast approximate search...")
                index = self._build_hnsw_index(collection_key, doc_embeddings)
                if index:
                    # Search using HNSW
                    labels, distances = index.knn_query(np.array([query_embedding]), k=min(n_results, len(doc_texts)))
                    
                    # Convert distances to similarity (HNSW returns distance, we convert to similarity)
                    results = []
                    for idx, dist in zip(labels[0], distances[0]):
                        # For cosine distance: similarity = 1 - distance (since HNSW cosine is in [0, 2])
                        similarity = 1 - (dist / 2)  # Normalize to [0, 1]
                        similarity = max(0, min(1, similarity))  # Clamp to [0, 1]
                        
                        results.append({
                            'embedding_id': doc_ids[int(idx)],
                            'content': doc_texts[int(idx)][:500],
                            'full_content': doc_texts[int(idx)],
                            'similarity': float(similarity),
                            'distance': float(dist),
                            'method': 'hnsw',
                            'metadata': doc_metadata[int(idx)]
                        })
                    
                    if results:
                        logger.info(f"[RAG] ✓ Found {len(results)} results using HNSW (similarity range: {min(r['similarity'] for r in results):.3f}..{max(r['similarity'] for r in results):.3f})")
                    else:
                        logger.info(f"[RAG] ✓ HNSW search returned 0 results")
                    return results
            
            # Fallback: brute-force cosine similarity (exact but slower)
            logger.debug(f"[RAG] Using brute-force cosine similarity search...")
            
            # Compute cosine similarities
            # cosine_sim = (A · B) / (||A|| * ||B||)
            # Since embeddings are already normalized, we can just use dot product
            similarities = np.dot(doc_embeddings, query_embedding)
            
            # Sort by similarity (descending)
            sorted_indices = np.argsort(-similarities)[:n_results]
            
            results = []
            for idx in sorted_indices:
                similarity = float(similarities[idx])
                results.append({
                    'embedding_id': doc_ids[idx],
                    'content': doc_texts[idx][:500],
                    'full_content': doc_texts[idx],
                    'similarity': max(0, min(1, (similarity + 1) / 2)),  # Normalize to [0, 1]
                    'distance': float(1 - similarity),
                    'method': 'cosine_similarity',
                    'metadata': doc_metadata[idx]
                })
            
            if results:
                logger.info(f"[RAG] ✓ Found {len(results)} results using cosine similarity (range: {min(r['similarity'] for r in results):.3f}..{max(r['similarity'] for r in results):.3f})")
            else:
                logger.info(f"[RAG] ✓ Cosine similarity search returned 0 results")
            return results
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Cosine similarity search failed: {e}")
            traceback.print_exc()
            return []

    def _load_collections(self) -> Dict[str, Any]:
        """
        Load all RAG collections for current module directly from SQLite
        
        DYNAMIC & SCALABLE: Supports two naming patterns (ZERO HARDCODING)
        
        Pattern 1 (Current): Generic collections shared across modules
        - rag_functions, rag_enums, rag_structs, rag_requirements, rag_hardware, etc.
        - Used when: Multiple modules share same collection data
        
        Pattern 2 (Future-ready): Module-specific collections
        - rag_{module_lowercase}_{collection_type}
        - Examples: rag_cxpi_functions, rag_lin_enums, rag_btl_structs, etc.
        - Used when: Each module has its own collection data
        
        Logic: Tries module-specific first, falls back to generic collections
        
        Returns:
            Dictionary mapping collection keys to collection metadata
        """
        collections = {}
        # Generic fallback names for each collection type.
        # Strategy 1 (in the loop below) ALWAYS tries rag_{module}_{type} first — fully dynamic.
        # Strategy 2 falls back to these generic names when no module-specific collection exists.
        # NO module names are hardcoded here — the module-specific prefix is built dynamically.
        collection_types = {
            'functions':      ['rag_functions', 'rag_swa_functions'],
            'enums':          ['rag_enums', 'rag_swa_enums'],
            'structs':        ['rag_structs', 'rag_swa_structs'],
            'requirements':   ['rag_requirements'],
            'hardware':       ['rag_hardware_spec'],
            'registers':      ['rag_register_defs'],
            'macros':         ['rag_macros', 'rag_swa_macros'],
            'typedefs':       ['rag_typedefs', 'rag_swa_typedefs'],
            'source':         ['rag_source_implementation'],
            'architecture':   ['rag_architecture_docs'],
            'pattern_library':['rag_puml_pattern_library'],
            'phases':         ['rag_puml_phases'],
        }
        
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Get all collections from database
            cursor.execute("SELECT id, name FROM collections;")
            db_collections = {row[1]: row[0] for row in cursor.fetchall()}
            conn.close()
            
            logger.info(f"[RAG] Found {len(db_collections)} total collections in ChromaDB")
            logger.info(f"[RAG] Available collections: {list(db_collections.keys())}")
            
            # Load collections with fallback logic
            loaded_count = 0
            for collection_type, collection_names in collection_types.items():
                matched_name = None
                
                # Strategy 1: Try module-specific name: rag_{module}_{type}
                if self.module_name:
                    module_specific = f"rag_{self.module_name}_{collection_type}"
                    if module_specific in db_collections:
                        matched_name = module_specific
                
                # Strategy 2: Try each candidate name from the list
                if not matched_name:
                    for candidate in collection_names:
                        if candidate in db_collections:
                            matched_name = candidate
                            break
                
                if matched_name:
                    collection_id = db_collections[matched_name]
                    # Count documents in this collection (from METADATA segments where docs are stored)
                    conn2 = sqlite3.connect(self.sqlite_path)
                    cursor2 = conn2.cursor()
                    cursor2.execute(
                        "SELECT COUNT(DISTINCT e.id) FROM embeddings e "
                        "JOIN segments s ON e.segment_id = s.id "
                        "WHERE s.collection = ? AND s.type = 'urn:chroma:segment/metadata/sqlite'",
                        (collection_id,)
                    )
                    doc_count = cursor2.fetchone()[0]
                    conn2.close()
                    
                    collections[collection_type] = {
                        'id': collection_id,
                        'name': matched_name,
                        'doc_count': doc_count
                    }
                    loaded_count += 1
                    logger.info(f"[RAG] ✓ Loaded collection: {matched_name} ({doc_count} documents) -> key='{collection_type}'")
                else:
                    logger.debug(f"[RAG] Collection '{collection_type}' not found (tried: {collection_names})")
            
            logger.info(f"[RAG] Successfully loaded {loaded_count}/{len(collection_types)} expected collections")
            
            if loaded_count == 0:
                logger.warning(f"[RAG-WARN] No collections found. Available: {list(db_collections.keys())}")
            
            return collections
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Failed to load collections: {e}")
            traceback.print_exc()
            return {}
    
    def _semantic_search(self, collection_key: str, query_text: str, n_results: int = 10) -> List[Dict]:
        """
        Perform INTELLIGENT semantic search using sentence-transformers + HNSW + cosine similarity
        
        This is the core of the intelligent RAG system.
        
        Pipeline:
        1. NLP Query Expansion: understand intent, extract synonyms, lemmatize, map domain concepts
        2. Sentence-Transformer Embedding: convert expanded query to vector (384 dims)
        3. HNSW Index Search: fast approximate nearest neighbor search (or cosine similarity fallback)
        4. Cosine Similarity Scoring: rank by semantic similarity (not keyword matching)
        5. Result Filtering: return top N with high semantic relevance
        
        Why intelligent?
        - Understands "test transmit" even if docs say "test transmission" (lemmatization)
        - Understands "send data" maps to "transmit" (domain synonyms)
        - Understands "channel 0 error handling" is related even without exact words (semantic meaning)
        - Uses neural embeddings (sentence-transformers trained on millions of sentences)
        - Not just keyword matching (which fails on indirect queries)
        
        Args:
            collection_key: Which collection to search ('functions', 'structs', etc.)
            query_text: User's natural language query (can be indirect or informal)
            n_results: Number of top results to return
            
        Returns:
            List of dicts with:
            - content: document text (first 500 chars)
            - full_content: complete document text
            - similarity: semantic similarity score (0-1, higher is better)
            - embedding_id: document ID
            - distance: raw distance metric
            - method: search method used (hnsw or cosine_similarity)
        """
        collection = self.collections.get(collection_key)
        if not collection:
            logger.error(f"[RAG-ERROR] Collection '{collection_key}' not found")
            return []
        
        if not self.embedding_model:
            logger.error("[RAG-ERROR] Embedding model not initialized, cannot perform semantic search")
            return []
        
        try:
            # Step 1: Expand query with NLP (understand intent, extract synonyms, map domain concepts)
            logger.debug(f"[RAG] Step 1: Expanding query '{query_text[:50]}...' for better intent understanding...")
            expanded_query = self._expand_query(query_text)
            
            # Step 2: Embed the query using sentence-transformers
            logger.debug(f"[RAG] Step 2: Embedding query with sentence-transformer...")
            query_embedding = self.embedding_model.encode(expanded_query, convert_to_numpy=True)
            
            # Step 3: Search using cosine similarity (HNSW or brute-force)
            logger.debug(f"[RAG] Step 3: Searching using cosine similarity...")
            results = self._cosine_similarity_search(collection_key, query_embedding, n_results=n_results, use_hnsw=True)
            
            # Step 4: Log summary
            if results:
                avg_sim = np.mean([r['similarity'] for r in results])
                logger.info(f"[RAG] ✓ Semantic search on '{collection_key}': {len(results)} results, avg similarity={avg_sim:.3f}")
            else:
                logger.warning(f"[RAG-WARN] No results found in collection '{collection_key}'")
            
            return results
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Semantic search failed: {e}")
            traceback.print_exc()
            return []

    
    def query_functions(self, intent: str, module: str = "", n_results: Optional[int] = None) -> List[Dict]:
        """
        Query functions based on semantic intent
        
        OPTIMIZED: Fetches top 10 functions for comprehensive sequence building
        
        Args:
            intent: User's natural language intent (e.g., "initialize module")
            module: Module name (optional, for filtering)
            n_results: Number of results to return (default: 10 for comprehensive coverage)
        
        Returns:
            List of matching functions with similarity scores (up to 10)
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['functions_n_results']
        
        collection = self.collections.get('functions')
        if not collection:
            logger.error("[RAG-ERROR] Functions collection not loaded")
            return []
        
        try:
            results = self._semantic_search('functions', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching functions for intent: '{intent[:50]}...'")
            return results
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Function query failed: {e}")
            return []
    
    def query_enums(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query enum types based on semantic intent
        
        OPTIMIZED: Fetches top 8 enum types for comprehensive enum coverage
        
        Args:
            intent: Description of what enum needed
            n_results: Number of results (default: 8 for complete enum type coverage)
        
        Returns:
            List of matching enums
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['enums_n_results']
        
        collection = self.collections.get('enums')
        if not collection:
            logger.error("[RAG-ERROR] Enums collection not loaded")
            return []
        
        try:
            results = self._semantic_search('enums', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching enums")
            return results
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Enum query failed: {e}")
            return []
    
    def query_structs(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query struct types based on intent
        
        OPTIMIZED: Fetches top 10 struct types for comprehensive type coverage
        
        Args:
            intent: Description of needed struct
            n_results: Number of results (default: 10)
        
        Returns:
            List of matching structs
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['structs_n_results']
        
        collection = self.collections.get('structs')
        if not collection:
            return []
        
        try:
            results = self._semantic_search('structs', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching structs")
            return results
        except Exception as e:
            logger.error(f"[RAG-ERROR] Struct query failed: {e}")
            return []
    
    # Note: feature-level queries are now served via `pattern_library` and `query_pattern_library`.
    # The old `query_features` method has been removed to avoid duplication.
    
    def query_requirements(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query requirements based on intent
        
        OPTIMIZED: Fetches top 8 requirements for comprehensive traceability
        
        Args:
            intent: Requirement description/intent
            n_results: Number of results (default: 8)
        
        Returns:
            Top 8 matching requirements
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['requirements_n_results']
        
        collection = self.collections.get('requirements')
        if not collection:
            return []
        
        try:
            results = self._semantic_search('requirements', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching requirements")
            return results
        except Exception as e:
            logger.error(f"[RAG-ERROR] Requirement query failed: {e}")
            return []
    
    def query_hardware(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query hardware specifications
        
        OPTIMIZED: Fetches top 5 hardware specs for sufficient HW context
        
        Args:
            intent: Hardware feature/register description
            n_results: Number of results (default: 5 - PDF chunks, sufficient)
        
        Returns:
            Top 5 matching hardware specifications
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['hardware_n_results']
        
        try:
            results = self._semantic_search('hardware', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching hardware specs")
            return results
        except Exception as e:
            logger.error(f"[RAG-ERROR] Hardware query failed: {e}")
            return []
    
    def query_registers(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query register definitions
        
        OPTIMIZED: Fetches top 8 register definitions for complete register coverage
        
        Args:
            intent: Register name/description (e.g., "channel command register")
            n_results: Number of results (default: 8)
        
        Returns:
            Top 8 matching register definitions
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['registers_n_results']
        
        collection = self.collections.get('registers')
        if not collection:
            logger.warning("[RAG-WARN] Registers collection not found")
            return []
        
        try:
            results = self._semantic_search('registers', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching register definitions")
            return results
        except Exception as e:
            logger.error(f"[RAG-ERROR] Register query failed: {e}")
            return []
    
    def query_macros(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query macro definitions (preprocessor constants)
        
        OPTIMIZED: Fetches top 8 macros for comprehensive macro coverage
        
        Args:
            intent: Macro description (e.g., "channel configuration macros")
            n_results: Number of results (default: 8)
        
        Returns:
            Top 8 matching macro definitions
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['macros_n_results']
        
        collection = self.collections.get('macros')
        if not collection:
            logger.warning("[RAG-WARN] Macros collection not found")
            return []
        
        try:
            results = self._semantic_search('macros', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching macros")
            return results
        except Exception as e:
            logger.error(f"[RAG-ERROR] Macro query failed: {e}")
            return []
    
    def query_typedefs(self, intent: str, n_results: Optional[int] = None) -> List[Dict]:
        """
        Query typedef definitions (custom type definitions)
        
        OPTIMIZED: Fetches top 8 typedefs for complete type coverage
        
        Args:
            intent: Type description (e.g., "channel data types")
            n_results: Number of results (default: 8)
        
        Returns:
            Top 8 matching typedef definitions
        """
        if n_results is None:
            n_results = self.CHUNK_CONFIG['typedefs_n_results']
        
        collection = self.collections.get('typedefs')
        if not collection:
            logger.warning("[RAG-WARN] Typedefs collection not found")
            return []
        
        try:
            results = self._semantic_search('typedefs', intent, n_results)
            logger.info(f"[RAG] Found {len(results)}/{n_results} matching typedefs")
            return results
        except Exception as e:
            logger.error(f"[RAG-ERROR] Typedef query failed: {e}")
            return []
    
    def query_pattern_library(self, fetch_all: bool = True) -> Dict[str, Any]:
        """
        Get complete PUML pattern library (ALL 8 chunks required)
        
        CRITICAL MANDATE: Fetch ALL 8 chunks completely - do NOT limit to top 5 or top 10
        
        All 8 chunks are interconnected and required for correct code generation:
        1. core_functions: Function registry with frequencies
        2. phase_patterns: Execution phases and sequences
        3. sequence_patterns: Validation rules and dependencies
        4. features: Feature definitions (PRIMARY for semantic matching)
        5. function_dependencies: Complete call graph
        6. loop_patterns: Polling and busy-wait patterns
        7. data_variations: Parameter templates and constraints
        8. channel_patterns: Channel configuration and validation
        
        Args:
            fetch_all: If True (default), fetch all 8 chunks completely.
                      If False, fetch top N (not recommended for PUML).
        
        Returns:
            Dictionary with all 8 keys containing complete pattern data:
            {
                'core_functions': {...},
                'phase_patterns': {...},
                'sequence_patterns': {...},
                'features': {...},
                'function_dependencies': {...},
                'loop_patterns': {...},
                'data_variations': {...},
                'channel_patterns': {...}
            }
        """
        collection = self.collections.get('pattern_library')
        if not collection:
            logger.error("[RAG-ERROR] Pattern library collection not loaded")
            return {}
        
        try:
            # CRITICAL: Fetch ALL documents (chunks) from pattern_library collection
            # Do NOT apply top-N limit - all 8 chunks are required
            if fetch_all:
                # Use direct SQLite query (collection is a dict with metadata, not a ChromaDB object)
                collection_id = collection['id']
                conn = sqlite3.connect(self.sqlite_path)
                cursor = conn.cursor()
                
                # Get all documents from this collection (from METADATA segments)
                cursor.execute("""
                    SELECT e.embedding_id, em.string_value
                    FROM embedding_metadata em
                    JOIN embeddings e ON em.id = e.id
                    JOIN segments s ON e.segment_id = s.id
                    WHERE s.collection = ? AND em.key = 'chroma:document'
                      AND s.type = 'urn:chroma:segment/metadata/sqlite'
                """, (collection_id,))
                
                doc_records = cursor.fetchall()
                conn.close()
                
                if not doc_records:
                    logger.warning("[RAG-WARN] Pattern library appears empty")
                    return {}
                
                logger.info(f"[RAG] Fetching ALL {len(doc_records)} pattern library chunks")
                
                # Parse all documents as interconnected pattern library
                pattern_lib = {}
                
                for chunk_id, doc_text in doc_records:
                    # Normalize chunk key: strip 'puml_' prefix so 'puml_core_functions' -> 'core_functions'
                    key = chunk_id
                    if key.startswith('puml_'):
                        key = key[5:]  # Remove 'puml_' prefix
                    
                    # Try to parse the document content
                    # Format: header text lines followed by JSON data
                    parsed = None
                    
                    # Strategy 1: Try direct JSON parse of whole text
                    try:
                        parsed = json.loads(doc_text)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    
                    # Strategy 2: Extract JSON from text (find first '{' or '[')
                    if parsed is None:
                        json_start = -1
                        for i, ch in enumerate(doc_text):
                            if ch in ('{', '['):
                                json_start = i
                                break
                        if json_start >= 0:
                            try:
                                parsed = json.loads(doc_text[json_start:])
                            except (json.JSONDecodeError, ValueError):
                                pass
                    
                    # Store the parsed or raw data under the normalized key
                    if parsed is not None:
                        pattern_lib[key] = parsed
                    else:
                        pattern_lib[key] = {'raw': doc_text}
                
                logger.info(f"[RAG] ✓ Pattern library loaded with ALL chunks ({len(pattern_lib)} keys)")
                
                # Verify all 8 expected keys are present
                expected_keys = [
                    'core_functions', 'phase_patterns', 'sequence_patterns', 'features',
                    'function_dependencies', 'loop_patterns', 'data_variations', 'channel_patterns'
                ]
                
                found_keys = set(pattern_lib.keys())
                missing_keys = set(expected_keys) - found_keys
                if missing_keys:
                    logger.warning(f"[RAG-WARN] Pattern library missing chunks: {missing_keys}")
                    logger.warning(f"         Found chunks: {found_keys}")
                
                return pattern_lib
            else:
                # NOT RECOMMENDED: Limited fetch (for testing only)
                logger.warning("[RAG-WARN] Pattern library fetch_all=False - recommend setting to True")
                results = self._semantic_search('pattern_library', 'pattern library', n_results=3)
                pattern_lib = {}
                for result in results:
                    try:
                        chunk_data = json.loads(result.get('content', '{}'))
                        pattern_lib.update(chunk_data)
                    except:
                        pattern_lib[result.get('id')] = result.get('content', '')
                return pattern_lib
            
        except Exception as e:
            logger.error(f"[RAG-ERROR] Failed to load pattern library: {e}")
            traceback.print_exc()
            return {}
    
    def multi_collection_search(self, intent: str, use_optimized_defaults: bool = True) -> Dict[str, List[Dict]]:
        """
        Search across multiple collections simultaneously (OPTIMIZED)
        
        OPTIMIZED STRATEGY:
        - Functions: Top 10 (comprehensive sequence building)
        - Structs: Top 10 (complete type information)
        - Enums: Top 8 (all enum variants)
        - Features: Top 8 (full feature taxonomy)
        - Requirements: Top 8 (comprehensive traceability)
        - Hardware: Top 8 (complete HW coverage)
        - Pattern Library: CORE_FUNCTIONS and PHASE_PATTERNS only (canonical patterns)
        
        This provides comprehensive context for code generation while maintaining
        good performance. Top 10 balances coverage with efficiency.
        
        Args:
            intent: User's semantic intent
            use_optimized_defaults: If True, use optimized CHUNK_CONFIG. 
                                   If False, use small top-3 (legacy mode)
        
        Returns:
            Dictionary with results from each collection:
            {
                'functions': [top 10],
                'structs': [top 10],
                'enums': [top 8],
                'features': [top 8],
                'requirements': [top 8],
                'hardware': [top 8],
                'pattern_library': [CORE_FUNCTIONS and PHASE_PATTERNS only]
            }
        """
        if use_optimized_defaults:
            # Use optimized configuration for comprehensive coverage
            # Note: 'features' and 'pattern_library' share the same data (both are the full PUML pattern library)
            _pattern_lib = self.query_pattern_library(fetch_all=self.CHUNK_CONFIG['pattern_library_fetch_all'])
            results = {
                'functions': self.query_functions(intent, n_results=self.CHUNK_CONFIG['functions_n_results']),
                'structs': self.query_structs(intent, n_results=self.CHUNK_CONFIG['structs_n_results']),
                'enums': self.query_enums(intent, n_results=self.CHUNK_CONFIG['enums_n_results']),
                'features': _pattern_lib,
                'requirements': self.query_requirements(intent, n_results=self.CHUNK_CONFIG['requirements_n_results']),
                'hardware': self.query_hardware(intent, n_results=self.CHUNK_CONFIG['hardware_n_results']),
                'pattern_library': _pattern_lib
            }
        else:
            # Legacy: limited results (not recommended)
            _pattern_lib = self.query_pattern_library(fetch_all=False)
            results = {
                'functions': self.query_functions(intent, n_results=3),
                'structs': self.query_structs(intent, n_results=3),
                'enums': self.query_enums(intent, n_results=3),
                # Legacy: use a small pattern_library fetch as a proxy for features
                'features': _pattern_lib,
                'pattern_library': _pattern_lib
            }
        
        # Log summary
        logger.info(f"[RAG] Multi-collection search completed:")
        for collection_name, items in results.items():
            if isinstance(items, dict):
                logger.info(f"      {collection_name}: {len(items)} chunks")
            else:
                logger.info(f"      {collection_name}: {len(items)} results")
        
        return results
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded collections (DYNAMIC - no hardcoding)"""
        stats = {
            'module': self.module_name,
            'loaded_collections': len(self.collections),
            'total_documents': sum(c.get('doc_count', 0) for c in self.collections.values()),
            'collections': {}
        }
        
        for key, collection in self.collections.items():
            if collection:
                stats['collections'][key] = {
                    'name': collection['name'],  # Dynamic name from config
                    'documents': collection.get('doc_count', 0),
                    'status': 'loaded'
                }
        
        return stats


# Quick test function
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test the client
    print("=" * 60)
    print("RAG CLIENT TEST")
    print("=" * 60)
    
    # Update path based on your ChromaDB location
    CHROMA_PATH = "../MCP_DB_INGESTION/output/chroma_data"
    
    try:
        rag = RAGClient(CHROMA_PATH)
        
        # Print stats
        stats = rag.get_collection_stats()
        print(f"\n📊 Collections Status:")
        print(f"Loaded: {stats['loaded_collections']}/{stats['total_collections']}")
        
        for key, info in stats['collections'].items():
            status_icon = "✓" if info['status'] == "loaded" else "✗"
            print(f"  {status_icon} {key}: {info['documents']} documents")
        
        # Test a query
        print(f"\n🔍 Testing function query...")
        functions = rag.query_functions("initialize module", n_results=3)
        if functions:
            print(f"Found {len(functions)} functions:")
            for func in functions:
                print(f"  • {func.get('metadata', {}).get('function_name', 'Unknown')} (similarity: {func['similarity']})")
        else:
            print("No functions found")
        
        print("\n✓ RAG client test completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        traceback.print_exc()
