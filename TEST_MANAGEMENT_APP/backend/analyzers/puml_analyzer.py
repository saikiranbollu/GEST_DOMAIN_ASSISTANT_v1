#!/usr/bin/env python3
"""
PUML Pattern Analyzer - Loads CORE patterns from RAG database for reference

SIMPLIFIED APPROACH (v2.0):
- PRIMARY: Top 10 RAG function + struct hits (authoritative)
- SECONDARY: PUML pattern library as supplement (reference only)

PATTERN LIBRARY USAGE (2 chunks only):
1. core_functions: which functions are always/frequently/rarely used
2. phase_patterns: init/operation/error_handling phases with example sequences

These 2 chunks tell us:
- Which functions are essential (always_present vs frequently_present vs rare)
- Which functions belong to initialization phase
- Which functions belong to operation phase  
- Which functions belong to cleanup/error handling
- Real-world example sequences from observed patterns

The pattern library is NOT the authoritative source for function signatures or detailed specs
(that comes from top-10 RAG hits). It's a guide for sequence building and phase structure.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import json


class PUMLPatternAnalyzer:
    """
    Loads PUML pattern analysis from RAG database (v2: Simplified to 2 chunks)
    
    ARCHITECTURE (v2.0):
    - PRIMARY SOURCE: Top 10 RAG function hits + Top 10 RAG struct hits (authoritative)
    - SUPPLEMENTAL SOURCE: PUML pattern library (reference only, 2 chunks only)
    
    Pattern Library Usage:
    The pattern library provides 2 essential chunks as a guide for sequence building:
    1. core_functions: Function priority levels (always/frequently/rarely used)
    2. phase_patterns: Phase structure and example sequences
    
    This is a REFERENCE guide, NOT the authoritative source for:
    - Function signatures (use RAG top-10 hits)
    - Complete dependency graphs (use KG or RAG)
    - All possible functions (use RAG)
    
    The 2 chunks tell us:
    - Which functions are essential (always_present)
    - Which functions are typical (frequently_present)
    - Which functions are rare
    - Which phase each function belongs to
    - Real-world example sequences from observed patterns
    """
    
    def __init__(self, rag_client, kg_client, cache=None):
        """Initialize analyzer with database clients
        
        Args:
            rag_client: RAGClient instance (for querying pattern library)
            kg_client: KGClient instance (for querying function relationships)
            cache: Optional HybridCache for caching patterns
        
        Note: kg_client used for enhanced relationship queries, but pattern library
              itself comes from RAG (pre-computed by MCP_DB_INGESTION)
        """
        self.rag_client = rag_client
        self.kg_client = kg_client
        self.cache = cache
        self.module = rag_client.module_name if rag_client else None
        
    def load_pattern_library(self) -> Dict[str, Any]:
        """Load ONLY essential PUML pattern library chunks (core_functions and phase_patterns)
        
        SIMPLIFIED: Fetch ONLY 2 chunks:
        1. core_functions: Always/frequently/rarely present functions
        2. phase_patterns: Init/Operation/Error_handling phases with example sequences
        
        These are sufficient for:
        - Deciding which functions are core vs optional
        - Understanding which phase each function belongs to
        - Learning typical sequence patterns from real code
        
        Returns:
            {
                'core_functions': {...},
                'phase_patterns': {...}
            }
        
        Cache: Caches the 2 essential chunks for performance
        """
        # Check cache first
        cache_key = f"puml_patterns_{self.module}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                print(f"[PUML-ANALYZER] ✓ Loaded 2 essential pattern chunks from cache for module '{self.module}'")
                return cached
        
        try:
            # Query RAG for pattern library (fetch ALL to extract the 2 chunks we need)
            print(f"[PUML-ANALYZER] Loading pattern library from RAG database...")
            full_pattern_lib = self.rag_client.query_pattern_library(fetch_all=True)
            
            if not full_pattern_lib or len(full_pattern_lib) == 0:
                print(f"[PUML-ANALYZER-WARN] Pattern library empty or not found in RAG")
                return self._empty_pattern_library()
            
            # Extract ONLY the 2 essential chunks
            pattern_library = {
                'core_functions': full_pattern_lib.get('core_functions', {}),
                'phase_patterns': full_pattern_lib.get('phase_patterns', {})
            }
            
            print(f"[PUML-ANALYZER] ✓ Successfully loaded 2 essential chunks:")
            print(f"     ✓ core_functions: {len(pattern_library.get('core_functions', {}))} categories")
            print(f"     ✓ phase_patterns: {len(pattern_library.get('phase_patterns', {}))} phases")
            
            # Verify both chunks are present
            if not pattern_library['core_functions'] or not pattern_library['phase_patterns']:
                print(f"[PUML-ANALYZER-WARN] One or both essential chunks are missing!")
                print(f"                    core_functions: {bool(pattern_library['core_functions'])}")
                print(f"                    phase_patterns: {bool(pattern_library['phase_patterns'])}")
            
            # Cache the result
            if self.cache:
                self.cache.set(cache_key, pattern_library)
            
            return pattern_library
            
        except Exception as e:
            print(f"[PUML-ANALYZER-ERROR] Failed to load pattern library: {e}")
            import traceback
            traceback.print_exc()
            return self._empty_pattern_library()
    
    def load_code_generation_rules(self) -> Dict[str, Any]:
        """Extract code generation rules from 2 essential PUML chunks
        
        Uses core_functions (function priorities) and phase_patterns (phase structure)
        to derive:
        - Which functions are essential (always_present)
        - Which functions are optional (frequently_present, rare)
        - Phase structure and typical sequences
        
        Returns:
            {
                'module': module name,
                'core_functions': always/frequently/rare function lists,
                'phase_structure': phases detected from pattern library,
                'init_functions': functions in initialization phase,
                'operation_functions': functions in operation phase,
                'error_functions': functions in error handling,
                'typical_phase_sequences': example sequences per phase
            }
        """
        try:
            pattern_lib = self.load_pattern_library()
            
            # Extract core function priority information
            core_funcs = pattern_lib.get('core_functions', {})
            always_present = core_funcs.get('always_present', [])
            frequently_present = core_funcs.get('frequently_present', [])
            rare = core_funcs.get('rare', [])
            
            # Extract phase information
            phase_patterns = pattern_lib.get('phase_patterns', {})
            
            # Build phase-to-functions mapping
            init_functions = set(phase_patterns.get('initialization', {}).get('common_functions', []))
            operation_functions = set(phase_patterns.get('operation', {}).get('common_functions', []))
            error_functions = set(phase_patterns.get('error_handling', {}).get('common_functions', []))
            
            # Extract typical sequences from each phase
            init_sequences = phase_patterns.get('initialization', {}).get('example_sequences', [])
            operation_sequences = phase_patterns.get('operation', {}).get('example_sequences', [])
            error_sequences = phase_patterns.get('error_handling', {}).get('example_sequences', [])
            
            rules = {
                'module': self.module,
                'core_functions': {
                    'always_present': always_present,
                    'frequently_present': frequently_present,
                    'rare': rare
                },
                'phase_structure': list(phase_patterns.keys()),
                'init_functions': list(init_functions),
                'operation_functions': list(operation_functions),
                'error_functions': list(error_functions),
                'typical_phase_sequences': {
                    'initialization': init_sequences[:3] if init_sequences else [],  # Top 3 example sequences
                    'operation': operation_sequences[:3] if operation_sequences else [],
                    'error_handling': error_sequences[:3] if error_sequences else []
                },
                'default_timeout': 1000,
                'default_retry_count': 3
            }
            
            print(f"[PUML-ANALYZER] Code generation rules extracted:")
            print(f"     Always present: {len(always_present)} functions")
            print(f"     Frequently used: {len(frequently_present)} functions")
            print(f"     Rare functions: {len(rare)} functions")
            print(f"     Phase structure: {rules['phase_structure']}")
            
            return rules
            
        except Exception as e:
            print(f"[PUML-ANALYZER-ERROR] Failed to load code generation rules: {e}")
            return {
                'module': self.module,
                'default_timeout': 1000,
                'default_retry_count': 3,
                'phase_structure': ['initialization', 'operation', 'error_handling']
            }
    
    def analyze(self, primary_function: Optional[str] = None, module: Optional[str] = None) -> Dict[str, Any]:
        """Analyze PUML patterns using 2 essential chunks: core_functions and phase_patterns
        
        This is the main entry point. Uses the 2 chunks to provide:
        - Core function priorities (always/frequently/rarely used)
        - Phase-to-function mappings (what functions belong to each phase)
        - Example sequences (real patterns from code)
        - Phase ordering and typical workflow
        
        Args:
            primary_function: Optional primary function (not used with v2 approach, kept for compatibility)
            module: Module name (uses self.module if not provided)
            
        Returns:
            {
                'pattern_library': {...},              # The 2 chunks (core_functions, phase_patterns)
                'code_generation_rules': {...},        # Extracted rules for code generation
                'module': 'cxpi',
                'core_functions': {...},               # Function priority info
                'phase_patterns': {...},               # Phase structure and examples
                'function_priority_map': {...},        # Which functions are essential
                'phase_to_functions': {...}            # Phase -> function mappings
            }
        """
        if module:
            self.module = module
        
        try:
            # Load the 2 essential chunks
            pattern_library = self.load_pattern_library()
            
            # Load code generation rules (derived from the 2 chunks)
            code_generation_rules = self.load_code_generation_rules()
            
            # Extract and organize the 2 chunks for maximum usability
            core_functions = pattern_library.get('core_functions', {})
            phase_patterns = pattern_library.get('phase_patterns', {})
            
            # Build priority map: function_name -> priority level
            function_priority_map = {}
            for func in core_functions.get('always_present', []):
                function_priority_map[func] = 'always'
            for func in core_functions.get('frequently_present', []):
                function_priority_map[func] = 'frequently'
            for func in core_functions.get('rare', []):
                function_priority_map[func] = 'rare'
            
            # Build phase-to-functions mapping with example sequences
            phase_to_functions = {}
            for phase_name, phase_data in phase_patterns.items():
                phase_to_functions[phase_name] = {
                    'common_functions': phase_data.get('common_functions', []),
                    'example_sequences': phase_data.get('example_sequences', [])[:3],  # Top 3 examples
                    'typical_length': phase_data.get('typical_length', 0)
                }
            
            result = {
                'pattern_library': pattern_library,
                'code_generation_rules': code_generation_rules,
                'module': self.module,
                'core_functions': core_functions,
                'phase_patterns': phase_patterns,
                'function_priority_map': function_priority_map,
                'phase_to_functions': phase_to_functions,
                'primary_function': primary_function
            }
            
            print(f"[PUML-ANALYZER] Analysis complete for module '{self.module}'")
            print(f"     Function priority map: {len(function_priority_map)} functions categorized")
            print(f"     Phase structure: {list(phase_to_functions.keys())}")
            print(f"     Total phases: {len(phase_to_functions)}")
            for phase_name, phase_data in phase_to_functions.items():
                print(f"       - {phase_name}: {len(phase_data['common_functions'])} functions, {len(phase_data['example_sequences'])} examples")
            
            return result
            
        except Exception as e:
            print(f"[PUML-ANALYZER-ERROR] Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'pattern_library': self._empty_pattern_library(),
                'code_generation_rules': {'module': self.module},
                'module': self.module,
                'core_functions': {},
                'phase_patterns': {},
                'function_priority_map': {},
                'phase_to_functions': {}
            }
    
    # Helper methods
    
    def _check_test_mode_support(self, pattern_lib: Dict) -> bool:
        """Check if pattern library indicates test mode support (from function names)"""
        core_funcs = pattern_lib.get('core_functions', {})
        all_funcs = []
        all_funcs.extend(core_funcs.get('always_present', []))
        all_funcs.extend(core_funcs.get('frequently_present', []))
        all_funcs.extend(core_funcs.get('rare', []))
        
        # Check if any function has 'ForTest' suffix
        for func_name in all_funcs:
            if 'ForTest' in func_name or 'fortest' in func_name.lower():
                return True
        return False
    
    def _check_error_injection_support(self, pattern_lib: Dict) -> bool:
        """Check if pattern library indicates error injection support (from function names)"""
        core_funcs = pattern_lib.get('core_functions', {})
        all_funcs = []
        all_funcs.extend(core_funcs.get('always_present', []))
        all_funcs.extend(core_funcs.get('frequently_present', []))
        all_funcs.extend(core_funcs.get('rare', []))
        
        # Check if any function has 'Error' or 'Inject' keywords
        for func_name in all_funcs:
            func_lower = func_name.lower()
            if 'error' in func_lower or 'inject' in func_lower or 'forerror' in func_lower:
                return True
        return False
    
    def _extract_phase_order(self, pattern_lib: Dict) -> List[str]:
        """Extract phase execution order from phase_patterns"""
        phase_patterns = pattern_lib.get('phase_patterns', {})
        if isinstance(phase_patterns, dict):
            # Typical order: initialization -> operation -> error_handling
            phases = list(phase_patterns.keys())
            # Reorder to ensure initialization first, then operation, then error
            preferred_order = ['initialization', 'operation', 'error_handling']
            ordered = [p for p in preferred_order if p in phases]
            ordered.extend([p for p in phases if p not in preferred_order])
            return ordered
        return ['initialization', 'operation', 'error_handling']
    
    def _empty_pattern_library(self) -> Dict[str, Any]:
        """Return empty pattern library structure (2 chunks only)"""
        return {
            'core_functions': {
                'always_present': [],
                'frequently_present': [],
                'conditional': [],
                'rare': []
            },
            'phase_patterns': {
                'initialization': {'common_functions': [], 'example_sequences': [], 'typical_length': 0},
                'operation': {'common_functions': [], 'example_sequences': [], 'typical_length': 0},
                'error_handling': {'common_functions': [], 'example_sequences': [], 'typical_length': 0}
            }
        }
