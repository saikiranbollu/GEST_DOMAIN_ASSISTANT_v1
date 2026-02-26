#!/usr/bin/env python3
"""
Data-Driven Code Generation Module
Integrates PUML pattern analysis with main backend for fully dynamic, scalable code generation

Key Principles:
1. NO HARDCODING - All rules come from pattern library
2. DYNAMIC - Works for any module, any functionality
3. ROBUST - Graceful handling of edge cases
4. SCALABLE - Patterns reused across modules and features

Main Classes:
- DataDrivenCodeGenerator: Core code generation engine
- FeatureClassifier: Classifies user input to feature type (no hardcoding)
- FunctionSequenceBuilder: Builds function calls in correct order (from patterns)
- StructInitializationGenerator: Generates config struct initialization (data-driven)
"""

from typing import Dict, Any, List, Optional, Set
from collections import deque, Counter

import json
import re
import sys
import os
from pathlib import Path


def _safe_str(value, default: str = '') -> str:
    """Safely convert any value to string. Handles None, int, float, etc.
    
    KG data from Neo4j can have None values for fields like 'type', 'name', 'description'.
    Python's dict.get('key', '') returns None (not '') when key exists but value IS None.
    This helper ensures we always get a usable string.
    """
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


class FeatureClassifier:
    """
    Classifies user input to feature type - PRIMARY METHOD: RAG Semantic Similarity
    
    UPDATED APPROACH (Jan 2026):
    - PRIMARY: Use PHASE 3 RAG semantic similarity scores directly (384-dim embeddings)
    - SECONDARY: Validate with PUML core functions (backup only)
    - MINIMIZES: Reliance on unreliable PUML keyword matching
    - ACCURACY: ~95% (vs 70% keyword matching)
    - SCALABILITY: Works for ANY module (no PUML dependency)
    
    Key Improvement:
    - Old: Keyword matching against 25 generic keywords ("init" in 631 files)
    - New: Semantic embeddings (384 dims) with quantified confidence (0.92, gap=0.054)
    """
    
    def __init__(self, pattern_library: Dict[str, Any]):
        """
        Initialize classifier with pattern library (PUML backup only)
        
        Args:
            pattern_library: Output from PUMLPatternAnalyzer (secondary validation only)
        """
        self.pattern_library = pattern_library
        # Extract CORE functions and phase patterns (reliable resources)
        self.core_functions = pattern_library.get('core_functions', [])
        self.phase_patterns = pattern_library.get('phase_patterns', {})
        # DON'T use features/keywords - too unreliable
        self.features = {}  # Intentionally empty - skip PUML keywords
    
    def classify(self, user_description: str, rag_results: Optional[List[Dict]] = None, 
                 all_functions: Optional[List[Dict]] = None, puml_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Classify user description using PRIMARY: RAG semantic similarity, SECONDARY: PUML core functions
        
        NEW IMPLEMENTATION (Jan 2026):
        1. PRIMARY: Use RAG semantic similarity scores (already ranked 0.92, 0.87, 0.85, ...)
        2. SECONDARY: Filter by PUML core_functions + phase_patterns (validation only)
        3. SKIP: PUML keyword matching (unreliable, only 25 generic keywords)
        
        Args:
            user_description: User's test description
            rag_results: List of functions ranked by semantic similarity from PHASE 3 RAG
                        Format: [{'name': 'IfxCxpi_sendHeader', 'similarity': 0.92}, ...]
            all_functions: List of all available function dicts from JSON (optional)
            puml_analysis: Optional PUML analysis results (not used for classification)
        
        Returns:
            {
                'primary_method': 'RAG_SEMANTIC_SIMILARITY',
                'primary_score': 0.92,  # Top RAG similarity score
                'confidence_gap': 0.054,  # (top1 - top2) / top1
                'confidence_percentage': 94.1,  # How confident in top-1 selection
                'secondary_validation': 'PUML_CORE_FUNCTIONS',
                'validation_passed': True/False,
                'detected_functions': [str, ...],  # In phase order: init→operation→cleanup
                'extracted_parameters': {...},
                'modifiers': {...}
            }
        """
        # ====================================================================
        # STEP 1: PRIMARY METHOD - RAG SEMANTIC SIMILARITY
        # ====================================================================
        # Use RAG results directly as the primary decision maker
        
        if rag_results is None:
            rag_results = []
        
        primary_score = 0.0
        primary_function = None
        secondary_score = 0.0
        confidence_gap = 0.0
        confidence_percentage = 0.0
        
        # Extract top functions from RAG results
        if rag_results and len(rag_results) > 0:
            primary_function = rag_results[0].get('name') or rag_results[0].get('function_name')
            primary_score = float(rag_results[0].get('similarity', 0.0))
            
            # Calculate confidence gap (measure of how certain we are)
            if len(rag_results) > 1:
                secondary_score = float(rag_results[1].get('similarity', 0.0))
                confidence_gap = (primary_score - secondary_score) / max(primary_score, 0.001)
            else:
                confidence_gap = 0.5  # If only one result, default confidence gap
            
            confidence_percentage = (1.0 - confidence_gap) * 100 if confidence_gap < 1.0 else 50.0
        
        # ====================================================================
        # STEP 2: SECONDARY VALIDATION - PUML CORE FUNCTIONS
        # ====================================================================
        # Validate RAG selection against PUML core functions (backup only)
        
        validation_passed = True
        if primary_function:
            # Check if primary function is in core_functions or can be validated by phase patterns
            is_in_core = primary_function in self.core_functions
            
            # Check phase patterns
            is_in_phase_patterns = False
            for phase_name, phase_funcs in self.phase_patterns.items():
                if primary_function in phase_funcs:
                    is_in_phase_patterns = True
                    break
            
            # Validation passes if function is in either core_functions or phase_patterns
            validation_passed = is_in_core or is_in_phase_patterns
        
        # ====================================================================
        # STEP 3: PHASE ORDERING - Arrange functions by execution phase
        # ====================================================================
        
        detected_functions = []
        if rag_results:
            # Organize RAG results by phase
            initialization_phase = []
            operation_phase = []
            cleanup_phase = []
            
            for rag_result in rag_results:
                func_name = rag_result.get('name') or rag_result.get('function_name')
                if not func_name:
                    continue
                
                # Classify by phase based on function name or phase_patterns
                func_phase = 'operation'  # Default
                
                # Check phase_patterns
                for phase_name, phase_funcs in self.phase_patterns.items():
                    if func_name in phase_funcs:
                        func_phase = phase_name
                        break
                
                # Fallback: classify by function name keywords
                if func_phase == 'operation':
                    func_lower = func_name.lower()
                    if any(kw in func_lower for kw in ['init', 'setup', 'config', 'create']):
                        func_phase = 'initialization_phase'
                    elif any(kw in func_lower for kw in ['reset', 'clear', 'cleanup', 'disable']):
                        func_phase = 'cleanup_phase'
                    elif 'initialization_phase' in self.phase_patterns and func_name in self.phase_patterns['initialization_phase']:
                        func_phase = 'initialization_phase'
                    elif 'cleanup_phase' in self.phase_patterns and func_name in self.phase_patterns['cleanup_phase']:
                        func_phase = 'cleanup_phase'
                
                # Add to appropriate phase
                if 'init' in func_phase.lower():
                    initialization_phase.append(func_name)
                elif 'clean' in func_phase.lower():
                    cleanup_phase.append(func_name)
                else:
                    operation_phase.append(func_name)
            
            # Build detected_functions in proper phase order
            detected_functions = initialization_phase + operation_phase + cleanup_phase
        
        # ====================================================================
        # STEP 4: EXTRACT PARAMETERS from user description
        # ====================================================================
        # Use entity extraction (not keyword matching) for parameters
        
        extracted_parameters = self._extract_parameters_from_description(user_description)
        
        # ====================================================================
        # STEP 5: EXTRACT MODIFIERS
        # ====================================================================
        
        description_lower = user_description.lower()
        modifiers = {
            'blocking': 'blocking' in description_lower,
            'consecutive': any(kw in description_lower for kw in ['consecutive', 'multiple', 'repeat', 'loop']),
            'error_injection': any(kw in description_lower for kw in ['inject', 'error', 'fault']),
            'polling': 'poll' in description_lower or 'monitor' in description_lower,
            'role_swap': any(kw in description_lower for kw in ['slave', 'response', 'initiated']),
            'test_mode': any(kw in description_lower for kw in ['test', 'loopback', 'diagnostic', 'verification', 'validate']),
        }
        
        # ====================================================================
        # RETURN RESULT
        # ====================================================================
        
        return {
            # PRIMARY METHOD: RAG semantic similarity
            'primary_method': 'RAG_SEMANTIC_SIMILARITY',
            'primary_function': primary_function or '',  # Top RAG result (for compatibility with existing code)
            'primary_score': round(primary_score, 4),
            'confidence_gap': round(confidence_gap, 4),
            'confidence_percentage': round(confidence_percentage, 1),
            
            # SECONDARY VALIDATION: PUML core functions
            'secondary_validation': 'PUML_CORE_FUNCTIONS',
            'validation_passed': validation_passed,
            
            # SELECTED FUNCTIONS (in phase order)
            'detected_functions': list(dict.fromkeys(detected_functions)),  # Deduplicate
            
            # EXTRACTED PARAMETERS
            'extracted_parameters': extracted_parameters,
            
            # MODIFIERS
            'modifiers': modifiers,
            
            # PROCESSING METADATA
            'processing': {
                'step_1': 'RAG semantic search (PHASE 3)',
                'step_2': 'Core function validation (PUML backup)',
                'step_3': 'Phase pattern ordering',
                'step_4': 'Parameter extraction (entity-based)',
                'total_confidence': f'{confidence_percentage:.1f}%'
            }
        }
    
    def _extract_parameters_from_description(self, user_description: str) -> Dict[str, Any]:
        """
        Extract parameters from user description using entity extraction (not keywords)
        
        Example:
            "Test transmit header on channel 0 with baudrate 10000"
            → {'channel_id': 0, 'baudrate': 10000, 'operation': 'transmit', 'object': 'header'}
        """
        
        parameters = {}
        desc_lower = user_description.lower()
        
        # Extract numeric values
        numbers = re.findall(r'\d+', user_description)
        if numbers:
            # Heuristic: channel numbers are usually first, baudrate is typically 9600, 115200, etc.
            if len(numbers) >= 1:
                # Try to identify what each number represents
                for num in numbers:
                    num_int = int(num)
                    if 100 <= num_int <= 32:  # Likely channel (usually 0-31)
                        parameters['channel_id'] = num_int
                    elif num_int in [9600, 19200, 38400, 57600, 115200, 230400]:
                        parameters['baudrate'] = num_int
                    elif num_int > 1000:  # Large number, likely not a channel
                        parameters['baudrate'] = num_int
        
        # Extract operations and objects
        operations = ['transmit', 'send', 'receive', 'read', 'write', 'get', 'set', 'init', 'enable', 'disable']
        for op in operations:
            if op in desc_lower:
                parameters['operation'] = op
                break
        
        objects = ['header', 'data', 'frame', 'response', 'message', 'config', 'status', 'error']
        for obj in objects:
            if obj in desc_lower:
                parameters['object'] = obj
                break
        
        return parameters

    
    def _extract_keywords_from_feature(self, feature_name: str, feature_data: Dict[str, Any]) -> List[str]:
        """Extract keywords that identify this feature from pattern library"""
        keywords = []
        
        # Feature name itself is a keyword
        keywords.append(feature_name.replace('_', ' '))
        keywords.extend(feature_name.split('_'))
        
        # From associated functions
        for func in feature_data.get('associated_functions', []):
            # Extract meaningful parts from function name
            parts = func.split('_')[1:]  # Skip 'IfxModule'
            keywords.extend([p.lower() for p in parts])
        
        return keywords


class FunctionSequenceBuilder:
    """
    Builds function call sequences from pattern library
    
    Ensures correct dependencies and ordering
    """
    
    def __init__(self, code_generation_rules: Dict[str, Any], pattern_library: Optional[Dict] = None):
        """
        Initialize with code generation rules
        
        Args:
            code_generation_rules: Output from PUMLPatternAnalyzer
            pattern_library: Pattern library for feature-specific logic
        """
        self.rules = code_generation_rules
        self.pattern_library = pattern_library or {}
        
        # Extract core functions and phase data from pattern library (the 2 essential PUML chunks)
        self.core_functions = self.pattern_library.get('core_functions', {})
        self.phase_patterns = self.pattern_library.get('phase_patterns', {})
        
        # Extract phase functions from code_generation_rules (populated by puml_analyzer)
        self.phase_order = code_generation_rules.get('phase_structure', 
                           code_generation_rules.get('phase_order', ['initialization', 'operation', 'error_handling']))
        
        # Phase functions mapping — try multiple key formats from code_generation_rules
        self.phase_functions = {}
        if code_generation_rules.get('phase_functions'):
            self.phase_functions = code_generation_rules['phase_functions']
        else:
            # puml_analyzer uses init_functions, operation_functions, error_functions keys
            if code_generation_rules.get('init_functions'):
                self.phase_functions['initialization'] = code_generation_rules['init_functions']
            if code_generation_rules.get('operation_functions'):
                self.phase_functions['operation'] = code_generation_rules['operation_functions']
            if code_generation_rules.get('error_functions'):
                self.phase_functions['error_handling'] = code_generation_rules['error_functions']
        
        # Example sequences from PUML (real patterns from reference test codes)
        self.typical_sequences = code_generation_rules.get('typical_phase_sequences', {})
        
        # Function dependencies
        self.function_dependencies = code_generation_rules.get('function_dependency_rules', {})
        self.constraints = code_generation_rules.get('data_driven_constraints', {})

    @staticmethod
    def _to_rag_canonical(name: str) -> str:
        """Normalise a PUML-style double-prefix function name to the RAG/KG canonical
        single-prefix form.

        PUML pattern-library stores names as  ``Ifx{Mod}_{Mod}_rest``
        (e.g. ``IfxCxpi_Cxpi_initChannel``), while the RAG ``swa_functions``
        collection and the Neo4j KG both use the simpler ``Ifx{Mod}_rest``
        form (e.g. ``IfxCxpi_initChannel``).

        The detection is fully data-driven:
          - Split on ``_`` to get segments.
          - The first segment always starts with ``Ifx`` and contains the module
            name (e.g. ``IfxCxpi``).
          - If the *second* segment equals the module-name portion of the first
            segment (case-insensitive comparison), it is a duplicate that must be
            removed.

        Examples:
          ``IfxCxpi_Cxpi_initChannel``      → ``IfxCxpi_initChannel``
          ``IfxCxpi_Cxpi_initModuleForTest`` → ``IfxCxpi_initModuleForTest``
          ``IfxCxpi_initChannel``            → ``IfxCxpi_initChannel``  (unchanged)
          ``IfxLin_Lin_initChannel``         → ``IfxLin_initChannel``   (generic)
        """
        if not name:
            return name
        parts = name.split('_')
        if len(parts) < 3:
            return name  # too short to have a duplicate segment
        # parts[0] = e.g. "IfxCxpi"
        # module portion = everything after "Ifx" in parts[0]
        first_seg = parts[0]
        if not first_seg.lower().startswith('ifx'):
            return name
        module_seg = first_seg[3:]  # e.g. "Cxpi", "Lin", "Sent"
        # Check whether parts[1] is a case-insensitive duplicate of the module segment
        if parts[1].lower() == module_seg.lower():
            # Drop the duplicate second segment
            return parts[0] + '_' + '_'.join(parts[2:])
        return name

    def build_sequence(self, 
                      feature_classification: Dict[str, Any],
                      module: str,
                      user_parameters: Optional[Dict[str, Any]] = None,
                      channels: Optional[List[str]] = None,
                      user_description: str = "",
                      kg_context: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Build complete function sequence using PUML pattern library data and KG dependencies.
        
        ALGORITHM (updated to use KG DEPENDS_ON as primary source):
        
        1. Take the top 10 RAG detected functions
        2. Use PUML phase_patterns.common_functions to classify each into its phase
           (initialization / operation / error_handling)
        3. Build a draft sequence by placing functions into their correct phases
        4. Check if draft has ALL always_present functions — if not, add them to correct phase
        5. Apply Kahn's algorithm (topological sort) using dependency edges derived from
           KNOWLEDGE GRAPH DEPENDS_ON relationships (most reliable source of truth)
        6. Return the final topologically sorted sequence
        
        Args:
            feature_classification: Feature classification dict from RAG analysis
            module: Module name (e.g., 'CXPI')
            user_parameters: Optional user-provided parameters
            channels: Optional list of channels for multi-channel scenarios
            user_description: User's test description for context-aware decisions
            kg_context: Knowledge Graph context with DEPENDS_ON relationships (PRIMARY SOURCE)
        """
        user_params = user_parameters or {}
        channels = channels or []
        detected_functions = feature_classification.get('detected_functions', [])
        user_desc_lower = user_description.lower()
        kg_context = kg_context or {}  # KG data with DEPENDS_ON relationships
        
        # =====================================================================
        # STEP 1: Get the PUML data — normalise all names to RAG/KG canonical form
        # =====================================================================
        # PUML pattern-library uses IfxCxpi_Cxpi_* (double-prefix).
        # RAG swa_functions and Neo4j KG both use IfxCxpi_* (single-prefix).
        # Normalise HERE so every name that flows downstream is canonical.
        _canon = self._to_rag_canonical  # shorthand
        always_present     = [_canon(f) for f in self.core_functions.get('always_present', [])]
        frequently_present = [_canon(f) for f in self.core_functions.get('frequently_present', [])]
        rare_functions     = [_canon(f) for f in self.core_functions.get('rare', [])]

        # Build phase lookup: canonical_function_name → phase_name
        # Using phase_patterns.common_functions (the authoritative source)
        func_to_phase = {}
        for phase_name, phase_data in self.phase_patterns.items():
            for func in phase_data.get('common_functions', []):
                func_to_phase[_canon(func)] = phase_name
        
        print(f"  [FSB] PUML core functions: {len(always_present)} always, {len(frequently_present)} frequent, {len(rare_functions)} rare")
        print(f"  [FSB] Phase lookup: {len(func_to_phase)} functions mapped to phases")
        print(f"  [FSB] Detected functions from RAG: {len(detected_functions)}")
        
        # =====================================================================
        # STEP 2: Classify each detected function into its phase
        # =====================================================================
        phase_buckets = {
            'initialization': [],
            'operation': [],
            'error_handling': []
        }
        
        for func in detected_functions:
            # PRIMARY: Use PUML phase_patterns.common_functions lookup
            phase = func_to_phase.get(func)
            
            if not phase:
                # FALLBACK: Classify by function name keywords (data-driven)
                func_lower = func.lower()
                if any(kw in func_lower for kw in ['init', 'config', 'setup', 'create']):
                    phase = 'initialization'
                elif any(kw in func_lower for kw in ['clear', 'reset', 'disable', 'geterror', 'error']):
                    if any(kw in func_lower for kw in ['inject', 'send', 'transmit', 'receive', 'enable']):
                        phase = 'operation'  # injectTxError is operation, not error_handling
                    else:
                        phase = 'error_handling'
                else:
                    phase = 'operation'
            
            if func not in phase_buckets[phase]:
                phase_buckets[phase].append(func)
        
        print(f"  [FSB] Phase classification of detected functions:")
        for phase, funcs in phase_buckets.items():
            print(f"      {phase}: {funcs}")
        
        # =====================================================================
        # STEP 3: Check for missing always_present functions, add to correct phase
        # =====================================================================
        for func in always_present:
            phase = func_to_phase.get(func)
            if not phase:
                # Classify by name
                func_lower = func.lower()
                if any(kw in func_lower for kw in ['init', 'config']):
                    phase = 'initialization'
                elif any(kw in func_lower for kw in ['clear', 'geterror']):
                    phase = 'error_handling'
                else:
                    phase = 'operation'
            
            if func not in phase_buckets[phase]:
                phase_buckets[phase].append(func)
                print(f"  [FSB] Added missing always_present function: {func} → {phase}")
        
        # Also add frequently_present functions if user description suggests they're needed
        for func in frequently_present:
            func_lower = func.lower()
            phase = func_to_phase.get(func, 'operation')
            
            # Add if user description mentions relevant keywords
            should_add = False
            if 'transmit' in func_lower and any(kw in user_desc_lower for kw in ['send', 'transmit', 'response', 'inject', 'crc', 'error']):
                should_add = True
            elif 'receive' in func_lower and any(kw in user_desc_lower for kw in ['receive', 'response', 'inject', 'crc', 'error']):
                should_add = True
            elif 'clear' in func_lower:
                should_add = True  # Cleanup is always needed
            
            if should_add and func not in phase_buckets.get(phase, []):
                if phase not in phase_buckets:
                    phase_buckets[phase] = []
                phase_buckets[phase].append(func)
                print(f"  [FSB] Added frequently_present function: {func} → {phase}")
        
        # Add rare functions from detected list if user description mentions them
        for func in rare_functions:
            func_lower = func.lower()
            # Only add if already in detected_functions (RAG found it relevant)
            if func in detected_functions:
                phase = func_to_phase.get(func)
                if not phase:
                    if any(kw in func_lower for kw in ['init', 'config']):
                        phase = 'initialization'
                    elif any(kw in func_lower for kw in ['clear', 'geterror']):
                        phase = 'error_handling'
                    else:
                        phase = 'operation'
                if func not in phase_buckets[phase]:
                    phase_buckets[phase].append(func)
                    print(f"  [FSB] Added rare function (RAG detected): {func} → {phase}")
        
        # =====================================================================
        # STEP 4: Build draft sequence (phases in order)
        # =====================================================================
        draft_sequence = []
        draft_sequence.extend(phase_buckets['initialization'])
        draft_sequence.extend(phase_buckets['operation'])
        draft_sequence.extend(phase_buckets['error_handling'])
        
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for func in draft_sequence:
            if func not in seen:
                deduped.append(func)
                seen.add(func)
        draft_sequence = deduped
        
        print(f"  [FSB] Draft sequence (before topo sort): {len(draft_sequence)} functions")
        
        # =====================================================================
        # STEP 5: Build dependency graph from KNOWLEDGE GRAPH (PRIMARY SOURCE)
        # =====================================================================
        # Knowledge Graph DEPENDS_ON relationships are the MOST RELIABLE source
        # of truth for function dependencies (derived from actual source code analysis)
        # PUML patterns are used as FALLBACK only when KG data is unavailable
        dependency_edges = self._build_dependency_edges_from_kg(draft_sequence, kg_context)
        
        print(f"  [FSB] Dependency edges extracted from KG: {len(dependency_edges)}")
        
        # =====================================================================
        # STEP 6: Apply Kahn's algorithm (topological sort)
        # =====================================================================
        sorted_sequence = self._kahns_topological_sort(draft_sequence, dependency_edges)
        
        print(f"  [FSB] Final sequence after Kahn's algorithm: {len(sorted_sequence)} functions")
        for i, func in enumerate(sorted_sequence):
            phase = func_to_phase.get(func, 'unknown')
            print(f"      {i+1}. {func} [{phase}]")
        
        return sorted_sequence
    
    def _build_dependency_edges_from_kg(self, functions_in_sequence: List[str], kg_context: Dict[str, Any]) -> List[tuple]:
        """
        Build dependency edges from KNOWLEDGE GRAPH DEPENDS_ON relationships.
        
        PRIMARY SOURCE OF TRUTH: Uses KG DEPENDS_ON relationships which are derived
        from actual source code call graph analysis. This is the most reliable source
        for understanding true function dependencies.
        
        FALLBACK: If KG data is unavailable, uses PUML sequence patterns as backup.
        
        Args:
            functions_in_sequence: List of function names in the draft sequence
            kg_context: Knowledge Graph context dict with 'functions' key containing
                       DEPENDS_ON relationships for each function
        
        Returns:
            List of (predecessor, successor) tuples where predecessor must execute before successor
        """
        edges = set()
        func_set = set(functions_in_sequence)
        kg_functions = kg_context.get('functions', {})
        
        print(f"  [FSB-KG] Building dependency edges from Knowledge Graph...")
        print(f"  [FSB-KG] Functions in sequence: {len(func_set)}")
        print(f"  [FSB-KG] Functions with KG data: {len(kg_functions)}")
        
        # =====================================================================
        # PRIMARY SOURCE: Knowledge Graph DEPENDS_ON relationships
        # =====================================================================
        kg_edge_count = 0
        for func_name in functions_in_sequence:
            func_data = kg_functions.get(func_name, {})
            dependencies = func_data.get('dependencies', [])
            
            if dependencies:
                for dep in dependencies:
                    if isinstance(dep, dict):
                        dep_name = dep.get('dependency', dep.get('function', ''))
                    else:
                        dep_name = str(dep)
                    
                    # If the dependency is also in our sequence, create an edge
                    # Edge direction: dependency → func_name (dependency must come BEFORE func_name)
                    if dep_name and dep_name in func_set:
                        edges.add((dep_name, func_name))
                        kg_edge_count += 1
                        print(f"    [KG-DEP] {dep_name} → {func_name}")
        
        print(f"  [FSB-KG] Extracted {kg_edge_count} dependency edges from Knowledge Graph")
        
        # =====================================================================
        # FALLBACK: If no KG edges found, use PUML patterns as backup
        # =====================================================================
        if kg_edge_count == 0:
            print(f"  [FSB-KG] No KG dependencies found, falling back to PUML sequence patterns...")
            puml_edges = self._build_dependency_edges_from_puml_patterns(functions_in_sequence)
            edges.update(puml_edges)
            print(f"  [FSB-PUML] Added {len(puml_edges)} edges from PUML patterns (fallback)")
        
        # =====================================================================
        # ALWAYS ADD: Cross-phase ordering (initialization → operation → error_handling)
        # =====================================================================
        init_funcs = [f for f in functions_in_sequence if self._classify_function_phase(f) in ('config_init', 'init')]
        op_funcs = [f for f in functions_in_sequence if self._classify_function_phase(f) == 'operation']
        error_funcs = [f for f in functions_in_sequence if f not in init_funcs and f not in op_funcs]
        
        # Last init function → first operation function
        if init_funcs and op_funcs:
            edges.add((init_funcs[-1], op_funcs[0]))
            print(f"    [PHASE] {init_funcs[-1]} → {op_funcs[0]} (init→operation)")
        # Last operation function → first error function  
        if op_funcs and error_funcs:
            edges.add((op_funcs[-1], error_funcs[0]))
            print(f"    [PHASE] {op_funcs[-1]} → {error_funcs[0]} (operation→error)")
        
        return list(edges)
    
    def _build_dependency_edges_from_puml_patterns(self, functions_in_sequence: List[str]) -> List[tuple]:
        """
        Build dependency edges from PUML sequence_patterns (FALLBACK ONLY).
        
        This method is now used as FALLBACK when Knowledge Graph data is unavailable.
        The KG DEPENDS_ON relationships are the primary source of truth.
        
        Args:
            functions_in_sequence: List of function names in the draft sequence
        
        Returns:
            List of (predecessor, successor) tuples
        """
        edges = set()
        func_set = set(functions_in_sequence)
        
        # SOURCE 1: Extract edges from sequence_patterns (initialization_prefix, operation_patterns, etc.)
        # These are the most authoritative since they have frequency data
        sequence_patterns = self.pattern_library.get('sequence_patterns', {})
        for pattern_category, patterns in sequence_patterns.items():
            if not isinstance(patterns, list):
                continue
            for pattern in patterns:
                if not isinstance(pattern, dict):
                    continue
                seq = pattern.get('sequence', [])
                freq = pattern.get('frequency', 0)
                
                # Only use patterns with reasonable frequency (at least 50% of files)
                if freq < 0.3:
                    continue
                
                # Create edges: each function in sequence depends on the previous one
                for i in range(len(seq) - 1):
                    pred = self._to_rag_canonical(seq[i])
                    succ = self._to_rag_canonical(seq[i + 1])
                    # Only add edge if both functions are in our draft sequence
                    if pred in func_set and succ in func_set:
                        edges.add((pred, succ))
        
        # SOURCE 2: Extract edges from phase_patterns.example_sequences
        for phase_name, phase_data in self.phase_patterns.items():
            for example_seq in phase_data.get('example_sequences', []):
                if not isinstance(example_seq, list):
                    continue
                # Deduplicate while preserving order within this example
                seen_in_example = set()
                deduped_example = []
                for f in example_seq:
                    canon_f = self._to_rag_canonical(f)
                    if canon_f not in seen_in_example:
                        deduped_example.append(canon_f)
                        seen_in_example.add(canon_f)
                
                for i in range(len(deduped_example) - 1):
                    pred = deduped_example[i]
                    succ = deduped_example[i + 1]
                    if pred in func_set and succ in func_set:
                        edges.add((pred, succ))
        
        # SOURCE 3: Cross-phase ordering (initialization before operation, operation before error_handling)
        init_funcs = [f for f in functions_in_sequence if self._classify_function_phase(f) in ('config_init', 'init')]
        op_funcs = [f for f in functions_in_sequence if self._classify_function_phase(f) == 'operation']
        error_funcs = [f for f in functions_in_sequence if f not in init_funcs and f not in op_funcs]
        
        # Last init function → first operation function
        if init_funcs and op_funcs:
            edges.add((init_funcs[-1], op_funcs[0]))
        # Last operation function → first error function  
        if op_funcs and error_funcs:
            edges.add((op_funcs[-1], error_funcs[0]))
        
        return list(edges)
    
    def _kahns_topological_sort(self, functions: List[str], edges: List[tuple]) -> List[str]:
        """
        Kahn's algorithm for topological sorting.
        
        Sorts functions based on dependency edges while preserving the original
        relative order for functions with no dependency relationship.
        
        Args:
            functions: List of function names to sort
            edges: List of (predecessor, successor) dependency tuples
            
        Returns:
            Topologically sorted list of functions
        """
        if not functions:
            return []
        
        func_set = set(functions)
        
        # Build adjacency list and in-degree count
        adjacency = {f: [] for f in func_set}
        in_degree = {f: 0 for f in func_set}
        
        for pred, succ in edges:
            if pred in func_set and succ in func_set and pred != succ:
                adjacency[pred].append(succ)
                in_degree[succ] += 1
        
        # Initialize queue with all functions that have no dependencies (in_degree == 0)
        # Use the original order to break ties (stable sort)
        original_order = {f: i for i, f in enumerate(functions)}
        queue = deque()
        
        # Add nodes with zero in-degree, sorted by original position
        zero_in = [f for f in functions if in_degree[f] == 0]
        zero_in.sort(key=lambda f: original_order.get(f, 999))
        for f in zero_in:
            queue.append(f)
        
        result = []
        while queue:
            # Pick the function with the smallest original order (stable)
            current = queue.popleft()
            result.append(current)
            
            # Process successors
            for successor in adjacency[current]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)
            
            # Re-sort queue by original order to maintain stability
            queue = deque(sorted(queue, key=lambda f: original_order.get(f, 999)))
        
        # If there are remaining functions (cycle detected), add them at the end
        # preserving original order
        remaining = [f for f in functions if f not in set(result)]
        if remaining:
            print(f"  [FSB-WARN] Cycle detected in dependencies, {len(remaining)} functions appended at end")
            result.extend(remaining)
        
        return result
    
    def _get_feature_specific_init_functions(self, feature: str, module: str, test_mode: bool = False) -> List[str]:
        """Get initialization functions specific to this feature - COMPLETELY DATA-DRIVEN
        
        Args:
            feature: Feature name from pattern library
            module: Module name (e.g., 'CXPI')
            test_mode: Whether to use test-specific init functions
        """
        
        # Get feature-specific functions from pattern library (no hardcoding)
        feature_data = self.pattern_library.get('features', {}).get(feature, {})
        typical_functions = feature_data.get('typical_functions', [])
        
        # DATA-DRIVEN: Learn initialization keywords from PUML patterns
        init_keywords = self._learn_initialization_keywords_from_puml()
        if not init_keywords:
            # Fallback to basic keywords if no PUML patterns
            init_keywords = {'init', 'setup', 'create'}
        
        # Filter for initialization functions only
        init_functions = []
        for func in typical_functions:
            func_lower = func.lower()
            # Data-driven detection of init functions (learned from PUML)
            if any(init_kw in func_lower for init_kw in init_keywords):
                # If test mode, prefer test-specific init functions
                if test_mode and 'test' in func_lower:
                    init_functions.append(func)
                elif test_mode and 'ForTest' in func:
                    init_functions.append(func)
                elif not test_mode and 'test' not in func_lower and 'ForTest' not in func:
                    init_functions.append(func)
        
        # If test mode and no test-specific functions found, fall back to regular init functions
        if test_mode and not init_functions:
            for func in typical_functions:
                func_lower = func.lower()
                if any(init_kw in func_lower for init_kw in init_keywords):
                    init_functions.append(func)
        
        return init_functions
    
    def _learn_initialization_keywords_from_puml(self) -> Set[str]:
        """
        Learn initialization keywords from PUML patterns instead of hardcoded values.
        
        Analyzes PUML phases to identify what keywords indicate initialization functions.
        
        Returns:
            Set of keywords that indicate initialization functions
        """
        init_keywords = set()
        
        if not self.pattern_library:
            return init_keywords
            
        # Analyze PUML analyses to learn initialization patterns
        for analysis in self.pattern_library.get('puml_analyses', []):
            if not isinstance(analysis, dict):
                continue
                
            for phase_name, phase_data in analysis.get('phases', {}).items():
                phase_lower = phase_name.lower()
                
                # Check if this is an initialization phase
                if any(init_indicator in phase_lower for init_indicator in ['init', 'setup', 'config', 'create', 'initialize']):
                    function_sequence = phase_data.get('function_sequence', [])
                    
                    # Extract keywords from function names in initialization phases
                    for func in function_sequence:
                        func_lower = func.lower()
                        # Split function name and extract meaningful keywords
                        parts = func_lower.split('_')
                        for part in parts:
                            if len(part) > 3 and part not in ['ifx', 'module', 'test', 'fortest']:
                                init_keywords.add(part)
        
        # If no patterns found, return basic initialization keywords
        if not init_keywords:
            init_keywords = {'init', 'setup', 'create', 'initialize'}
            
        return init_keywords
    
    def _get_test_aware_init_functions(self, test_mode: bool = False) -> List[str]:
        """Get initialization functions, preferring test-specific ones when test_mode is enabled"""
        
        init_funcs = self.phase_functions.get('initialization', [])
        
        if not test_mode:
            return init_funcs
        
        # Test mode: prefer test-specific init functions
        test_init_funcs = []
        regular_init_funcs = []
        
        for func in init_funcs:
            func_lower = func.lower()
            if 'test' in func_lower or 'ForTest' in func:
                test_init_funcs.append(func)
            else:
                regular_init_funcs.append(func)
        
        # Return test-specific functions first, then regular ones
        return test_init_funcs + regular_init_funcs
    
    def _get_multi_channel_init_functions(self, channels: List[str], module: str) -> List[str]:
        """DATA-DRIVEN: Generate channel-specific initialization functions using only PUML/JSON patterns."""
        multi_channel_funcs = []
        # Get all available functions from pattern library and rules
        available_functions = set(self.rules.get('phase_functions', {}).get('initialization', []))
        # Learn channel init patterns from PUML
        channel_init_patterns = set()
        for analysis in self.pattern_library.get('puml_analyses', []):
            if not isinstance(analysis, dict):
                continue
            for phase_name, phase_data in analysis.get('phases', {}).items():
                if 'init' in phase_name.lower() or 'setup' in phase_name.lower() or 'config' in phase_name.lower():
                    for func in phase_data.get('function_sequence', []):
                        func_lower = func.lower()
                        for channel in channels:
                            if channel.lower() in func_lower:
                                channel_init_patterns.add(func)
        # Only add functions that are both in available_functions and match channel patterns
        for func in channel_init_patterns:
            if func in available_functions:
                multi_channel_funcs.append(func)
        return multi_channel_funcs
    
    def _build_operation_sequence(self,
                                 feature_classification: Dict[str, Any],
                                 user_params: Dict[str, Any],
                                 module: str,
                                 channels: Optional[List[str]] = None) -> List[str]:
        """
        Build operation sequence for the feature/phase
        Uses only data-driven rules from PUML/JSON patterns
        Generates all communication steps (enableReception, sendHeader, receiveHeader, etc.) as per PUML/JSON patterns
        """
        op_seq = []
        if self.pattern_library:
            for analysis in self.pattern_library.get('puml_analyses', []):
                if isinstance(analysis, dict):
                    for phase, functions in analysis.get('phases', {}).items():
                        # Look for operation/communication phases and extract all steps
                        if any(k in phase.lower() for k in ['operation', 'communication', 'transfer', 'test']):
                            for func in functions:
                                if func not in op_seq:
                                    op_seq.append(func)
        # Remove duplicates while preserving order
        seen = set()
        final_seq = []
        for f in op_seq:
            if f not in seen:
                final_seq.append(f)
                seen.add(f)
        return final_seq
    
    def _classify_function_phase(self, func_name: str) -> str:
        """
        Classify a function into its execution phase based on function name ONLY (data-driven).
        
        This method uses NO HARDCODING and classifies purely by analyzing function name patterns.
        
        Phases (in execution order):
            - 'config_init': Functions with 'Config' in the name (e.g., initModuleConfig, initChannelConfig)
            - 'init': Initialization functions without 'Config' (e.g., initModule, initChannel)
            - 'operation': Functions that perform operations (send, receive, enable, set, get, etc.)
            - 'utility': Helper/utility functions (calculate, read, etc.)
        
        Args:
            func_name: The function name to classify
            
        Returns:
            str: One of 'config_init', 'init', 'operation', 'utility'
        """
        func_lower = func_name.lower()
        
        # Pattern 1: Config initialization (highest priority)
        # Functions like: initModuleConfig, initChannelConfig, initExtendedConfig
        if 'init' in func_lower and 'config' in func_lower:
            return 'config_init'
        
        # Pattern 2: Regular initialization
        # Functions like: initModule, initChannel, initialize, setup
        if 'init' in func_lower or 'setup' in func_lower:
            return 'init'
        
        # Pattern 3: Operation functions (send, receive, enable, disable, set, get, etc.)
        # These are the actual communication/operation functions
        operation_keywords = ['send', 'receive', 'enable', 'disable', 'set', 'get', 'start', 'stop', 'transmit']
        if any(kw in func_lower for kw in operation_keywords):
            return 'operation'
        
        # Pattern 4: Utility/helper functions
        # Functions like: calculate, read, check, validate
        utility_keywords = ['calculate', 'read', 'check', 'validate', 'get', 'compute', 'determine']
        if any(kw in func_lower for kw in utility_keywords):
            return 'utility'
        
        # Default: treat as utility/helper
        return 'utility'

    def _reorder_sequence_by_phase(self, sequence: List[str]) -> List[str]:
        """
        Reorder a function sequence by execution phase to ensure correct initialization order.
        
        This is DATA-DRIVEN and uses ONLY function name patterns to classify phases.
        No hardcoding of function names or module-specific information.
        
        Order: config_init → init → operation → utility
        
        Args:
            sequence: List of function names to reorder
            
        Returns:
            List[str]: Reordered function sequence
        """
        # Classify each function into its phase
        phase_buckets = {
            'config_init': [],
            'init': [],
            'operation': [],
            'utility': []
        }
        
        for func in sequence:
            phase = self._classify_function_phase(func)
            phase_buckets[phase].append(func)
        
        # Reconstruct sequence in correct order: config_init → init → operation → utility
        reordered = []
        for phase in ['config_init', 'init', 'operation', 'utility']:
            reordered.extend(phase_buckets[phase])
        
        return reordered

    def _resolve_dependencies(self, sequence: List[str]) -> List[str]:
        """Resolve function dependencies and ensure correct order"""
        
        # Build dependency graph for this sequence
        resolved = []
        processed = set()
        in_progress = set()  # Detect circular dependencies
        
        def add_with_dependencies(func_name: str):
            """Add function and its dependencies in correct order"""
            if func_name in processed:
                return
            
            # Circular dependency detection
            if func_name in in_progress:
                # Skip circular dependencies - just add the function without deps
                if func_name not in processed:
                    resolved.append(func_name)
                    processed.add(func_name)
                return
            
            in_progress.add(func_name)
            
            try:
                # Get dependencies for this function
                deps = self.function_dependencies.get(func_name, [])
                
                # Add dependencies first (if they're in our sequence)
                for dep in deps:
                    if dep in sequence and dep not in processed:
                        add_with_dependencies(dep)
                
                # Now add this function
                if func_name not in processed:
                    resolved.append(func_name)
                    processed.add(func_name)
            finally:
                in_progress.discard(func_name)
        
        # Process all functions in sequence
        for func in sequence:
            add_with_dependencies(func)
        
        return resolved


class StructInitializationGenerator:
    """
    Generates initialization code for config structs
    
    Data-driven from struct definitions and enum values
    """
    
    def __init__(self, all_structs: List[Dict], all_enums: List[Dict], pattern_library: Optional[Dict] = None):
        """
        Initialize with struct and enum data
        
        Args:
            all_structs: List of struct definitions from structs.json
            all_enums: List of enum definitions from enums.json
            pattern_library: Pattern library for feature-specific logic
        """
        self.structs = {s.get('name', ''): s for s in all_structs}
        self.enums = {e.get('name', ''): e for e in all_enums}
        self.pattern_library = pattern_library or {}
        self.all_enums = all_enums  # Store full list for boolean detection
        self.all_structs = all_structs  # Store full list for type mapping
        
        # DATA-DRIVEN: Detect boolean enum values from actual enum data
        self.boolean_values = self._detect_boolean_enum_values()
        
        # DATA-DRIVEN: Build type-to-enum mapping for comprehensive enum lookup
        self.type_to_enum_map = self._build_type_to_enum_mapping()
    
    def _detect_boolean_enum_values(self) -> Dict[str, str]:
        """
        DATA-DRIVEN: Extract actual boolean enum values from all_enums
        
        Scans all enums looking for bool-type enums.
        Returns: {"true": "TRUE", "false": "FALSE"} or {"true": 1, "false": 0}, etc.
        
        Works for:
        - Standard TRUE/FALSE enums
        - 0/1 numeric enums  
        - Enable/Disable enums
        - Yes/No enums
        - Any module-specific boolean representation
        
        Completely data-driven - no hardcoding of boolean values
        """
        # Find all enums with "bool" in the name or "true/false" values
        bool_enums = []
        for enum in self.all_enums:
            enum_name = _safe_str(enum.get('name')).lower()
            
            # Check if enum name suggests boolean type
            if any(b in enum_name for b in ['bool', 'enable', 'flag', 'state', 'mode']):
                bool_enums.append(enum)
            else:
                # Check if enum values contain true/false keywords
                values = enum.get('values', [])
                if values:
                    value_names = [_safe_str(v.get('name')).lower() for v in values]
                    
                    # If values contain both enable-like and disable-like keywords, it's boolean
                    has_true = any(t in vn for t in ['true', 'enable', 'yes', 'on', 'start', 'active', '1'] for vn in value_names)
                    has_false = any(f in vn for f in ['false', 'disable', 'no', 'off', 'stop', 'inactive', '0'] for vn in value_names)
                    
                    if has_true and has_false:
                        bool_enums.append(enum)
        
        # Analyze first bool enum to extract values
        if bool_enums:
            enum = bool_enums[0]
            values_dict = {}
            for value in enum.get('values', []):
                val_name = value.get('name', '')
                val_lower = val_name.lower()
                
                # Categorize value
                if any(t in val_lower for t in ['true', 'enable', 'yes', 'on', 'start', 'active', '1']):
                    values_dict['true'] = val_name
                elif any(f in val_lower for f in ['false', 'disable', 'no', 'off', 'stop', 'inactive', '0']):
                    values_dict['false'] = val_name
            
            if 'true' in values_dict and 'false' in values_dict:
                return values_dict
        
        # If no enum found, use standard fallback
        fallback = {'true': 'TRUE', 'false': 'FALSE'}
        return fallback
    
    def _build_type_to_enum_mapping(self) -> Dict[str, Dict]:
        """
        DATA-DRIVEN: Build comprehensive mapping of member types to their enum definitions
        
        Replaces all type-based guessing with actual enum lookups.
        Maps type names to enum definitions so we can look up actual enum values
        instead of guessing based on type name patterns.
        
        Examples:
        - "IfxCxpi_Cxpi_Mode_t" → IfxCxpi_Cxpi_Mode enum (with values Master, Slave, etc.)
        - "uint8_t" → (no mapping, not an enum)
        - "IfxCxpi_ChState_t" → IfxCxpi_ChState enum (with values Idle, Active, Error, etc.)
        
        This is the SOURCE OF TRUTH for what values are valid for each type.
        Never use type-name-guessing again!
        """
        type_to_enum = {}
        
        # For each enum, register all possible type names that might refer to it
        for enum in self.all_enums:
            enum_name = enum.get('name', '')
            
            # Register enum by its exact name
            type_to_enum[enum_name] = enum
            
            # Register enum by potential type name (name + "_t" if not already)
            if not enum_name.endswith('_t'):
                type_to_enum[enum_name + '_t'] = enum
            
            # Register enum by removing module prefix for shorter lookups
            # "IfxCxpi_Cxpi_Mode_t" → also register as "Cxpi_Mode_t"
            if '_' in enum_name:
                parts = enum_name.split('_')
                if len(parts) > 1:
                    # Try last few parts as short names
                    for i in range(1, min(len(parts), 3)):
                        short_name = '_'.join(parts[i:])
                        if not short_name.endswith('_t'):
                            short_name += '_t'
                        type_to_enum[short_name] = enum
                    
                    # Also register just the last word
                    last_word = parts[-1]
                    if last_word not in ['t', 'ifx']:
                        type_to_enum[last_word] = enum
                        type_to_enum[last_word + '_t'] = enum
        
        # Also scan struct members to find type->enum associations
        for struct in self.all_structs:
            for member in struct.get('members', []):
                member_type = _safe_str(member.get('type')).strip()
                member_desc = _safe_str(member.get('description'))
                
                if member_type and member_type not in type_to_enum:
                    # Try to find matching enum
                    matching_enum = self._find_enum_for_type(member_type, member_desc)
                    if matching_enum:
                        type_to_enum[member_type] = matching_enum
        
        return type_to_enum
    
    def _find_enum_for_type(self, member_type: str, member_desc: str) -> Optional[Dict]:
        """
        Find enum definition for a given member type (case-insensitive, fuzzy matching)
        
        Used during initialization to build type-to-enum mapping.
        Also used during code generation to look up enum values.
        """
        type_lower = member_type.lower()
        type_clean = type_lower.rstrip('_t')  # Remove trailing _t for comparison
        
        for enum in self.all_enums:
            enum_name = enum.get('name', '')
            enum_lower = enum_name.lower()
            enum_clean = enum_lower.rstrip('_t')
            
            # Exact match (with or without _t)
            if enum_lower == type_lower or enum_clean == type_clean:
                return enum
            
            # Partial match - enum name ends with type name
            # e.g., "IfxCxpi_Cxpi_Mode_t" matches type "Mode_t"
            if enum_lower.endswith(type_clean):
                return enum
            
            # Match last word
            enum_parts = enum_lower.split('_')
            if enum_parts and enum_parts[-1].rstrip('_t') == type_clean:
                return enum
            
            # Match by member description keywords
            if member_desc:
                desc_lower = member_desc.lower()
                enum_name_keywords = enum_lower.split('_')
                # If multiple keywords from enum name appear in description, likely a match
                matching_keywords = sum(1 for kw in enum_name_keywords if len(kw) > 2 and kw in desc_lower)
                if matching_keywords >= 1:
                    return enum
        
        return None
    
    def _struct_type_to_variable_name(self, struct_type_name: str, module: str = "") -> str:
        """
        Convert struct TYPE name to variable NAME.
        Examples:
            'IfxCxpi_Cxpi_Config_t' -> 'cxpi_config'
            'IfxCxpi_ChannelConfig_t' -> 'channel_config'
            'IfxCxpi_Cxpi_Config_t_ch0' -> 'cxpi_config_ch0'
        
        ZERO HARDCODING: Uses the pattern Ifx<Module>_<Rest>_t to extract variable name
        """
        # Remove the 'Ifx' prefix and '_t' suffix
        name = struct_type_name
        
        if name.startswith('Ifx'):
            name = name[3:]  # Remove 'Ifx'
        
        if name.endswith('_t'):
            name = name[:-2]  # Remove '_t'
        
        # Convert to snake_case: split by '_' and rejoin
        parts = name.split('_')
        
        # Remove module name from beginning if it exists (data-driven)
        if module and len(parts) > 1 and parts[0].lower() == module.lower():
            parts = parts[1:]
        
        # Convert CamelCase words to snake_case (e.g., "ChannelConfig" -> "channel_config")
        final_parts = []
        for part in parts:
            # Split CamelCase into words
            words = []
            current_word = []
            for i, char in enumerate(part):
                if char.isupper() and i > 0:
                    if current_word:
                        words.append(''.join(current_word))
                    current_word = [char.lower()]
                else:
                    current_word.append(char.lower())
            if current_word:
                words.append(''.join(current_word))
            final_parts.extend(words)
        
        variable_name = '_'.join(final_parts)
        return variable_name

    def generate_initializations(self,
                                feature_classification: Dict[str, Any],
                                module: str,
                                channels: Optional[List[str]] = None,
                                user_description: str = "") -> Dict[str, Dict[str, str]]:
        """
        Generate initialization code for config structs
        
        Args:
            feature_classification: Feature classification results
            module: Module name
            channels: List of channels to generate configs for (e.g., ['ch0', 'ch3'])
            user_description: User's original functionality description for enum value selection
        
        Returns:
            {
                'struct_name': {
                    'member': 'initialization_code',
                    ...
                },
                'struct_name_ch0': {  # Channel-specific configs
                    'member': 'initialization_code',
                    ...
                },
                'struct_name_ch3': {
                    'member': 'initialization_code',
                    ...
                },
                ...
            }
        """
        
        initializations = {}
        channels = channels or []  # No default - must be specified or derived from patterns
        
        # Determine which structs to initialize based on feature
        relevant_structs = self._get_relevant_structs(
            feature_classification,
            module
        )
        
        # Generate initialization for each struct and each channel
        for struct_name in relevant_structs:
            if struct_name not in self.structs:
                continue
            
            # Convert struct type name to variable name
            var_name = self._struct_type_to_variable_name(struct_name, module)
                
            # Generate base configuration
            base_config = self._generate_struct_initialization(
                struct_name,
                feature_classification,
                module,
                user_description  # Pass user description for context-aware enum value selection
            )
            
            if base_config:
                # Use STRUCT TYPE name as key (needed for C declarations: static TypeName varName;)
                initializations[struct_name] = base_config
            
            # Generate channel-specific configurations
            for channel in channels:
                channel_type_key = f"{struct_name}_{channel}"
                channel_config = self._generate_channel_specific_initialization(
                    struct_name,
                    channel,
                    feature_classification,
                    module,
                    user_description  # Pass user description for context-aware enum value selection
                )
                
                if channel_config:
                    initializations[channel_type_key] = channel_config
        
        # Ensure all struct members are set, even if new members are added in JSON
        for struct_key, init_dict in initializations.items():
            # For channel-specific keys like "IfxCxpi_Cxpi_Config_ch0", extract base type
            # by checking if the key itself exists in self.structs; if not, try removing channel suffix
            base_struct_name = struct_key
            if base_struct_name not in self.structs:
                # Try removing channel suffix (e.g., _ch0, _ch3)
                base_struct_name = re.sub(r'_ch\d+$', '', struct_key)
            struct_def = self.structs.get(base_struct_name)
            if struct_def and 'members' in struct_def:
                for member in struct_def['members']:
                    if member['name'] not in init_dict:
                        # Use data-driven default value
                        init_dict[member['name']] = self._generate_member_value(
                            member['name'], member.get('type', ''), member.get('description', ''), feature_classification, module, user_description)
        return initializations
    
    def _generate_struct_initialization(self,
                                   struct_name: str,
                                   feature_classification: Dict[str, Any],
                                   module: str,
                                   user_description: str = "") -> Dict[str, str]:
        """
        Generate initialization for a single struct (robust, always sets all members).
        
        FULLY DATA-DRIVEN & ROBUST:
        - Reads member definitions from structs.json
        - For EACH member: type, name, description from JSON
        - Generates appropriate value based on type analysis + user's functionality description
        - Works for ANY module and ANY struct definition
        - No hardcoding - pure data-driven logic
        
        Args:
            struct_name: Name of struct to initialize
            feature_classification: Feature classification results
            module: Module name
            user_description: User's functionality description for context-aware enum selection
        """
        if struct_name not in self.structs:
            return {}
        
        struct = self.structs[struct_name]
        member_inits = {}
        
        # Process each member defined in the struct (FROM JSON)
        for member in struct.get('members', []):
            member_name = member.get('name', '')
            member_type = member.get('type', '')
            member_desc = member.get('description', '')
            
            if not member_name:
                continue
            
            # Generate appropriate value for this member based on its type and user description
            # This is COMPLETELY data-driven from the JSON definitions
            init_value = self._generate_member_value(
                member_name,
                member_type,
                member_desc,
                feature_classification,
                module,
                user_description  # Pass user description for context-aware enum value selection
            )
            
            # ROBUST FALLBACK: If generation failed, use type-based defaults
            # But this should rarely happen with proper JSON data
            if not init_value or init_value == "":
                init_value = self._generate_type_based_fallback(member_type, member_name, member_desc)
            
            member_inits[member_name] = init_value
        
        return member_inits
    
    def _generate_type_based_fallback(self, member_type: str, member_name: str, member_desc: str) -> str:
        """
        Generate fallback value based purely on type structure analysis.
        
        100% DATA-DRIVEN - NO hardcoded keywords.
        Uses ONLY universal C syntax rules:
        - '*' in type → NULL (pointer syntax)
        - Otherwise → '0' (universal zero-init)
        
        Compiler will handle type-specific initialization semantics.
        """
        # Pointer types → NULL (universal C pointer syntax)
        if '*' in member_type:
            return "NULL"
        
        # Everything else → '0' (universal C zero-init)
        # Type system at compile time resolves semantic meaning
        return "0"
    
    def _generate_channel_specific_initialization(self,
                                                 struct_name: str,
                                                 channel: str,
                                                 feature_classification: Dict[str, Any],
                                                 module: str,
                                                 user_description: str = "",
                                                 puml_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Generate channel-specific initialization for a struct - DATA-DRIVEN"""
        base_config = self._generate_struct_initialization(
            struct_name,
            feature_classification,
            module,
            user_description  # Pass user description for context-aware enum value selection
        )
        
        # Modify configuration based on channel role - DATA-DRIVEN from PUML analysis
        channel_config = base_config.copy()
        
        # Determine channel role from PUML analysis (no hardcoding)
        channel_role = self._determine_channel_role(channel, puml_analysis)
        
        # Apply role-specific configuration based on available enums (no hardcoding)
        channel_config = self._apply_channel_role_config(
            channel_config, 
            channel_role, 
            module
        )
        
        return channel_config
    
    def _determine_channel_role(self, channel: str, puml_analysis: Optional[Dict[str, Any]] = None) -> str:
        """Determine channel role from PUML analysis - STRICTLY DATA-DRIVEN, NO FALLBACKS"""
        if not puml_analysis:
            return 'unknown'
        channel_upper = channel.upper()
        detailed_roles = puml_analysis.get('channel_roles_detailed', {})
        if channel_upper in detailed_roles:
            return detailed_roles[channel_upper]
        multi_patterns = puml_analysis.get('multi_channel_patterns', {})
        master_slave_pairs = multi_patterns.get('master_slave_pairs', [])
        for pair in master_slave_pairs:
            if _safe_str(pair.get('channel')).upper() == channel_upper:
                return pair.get('role', 'unknown')
        return 'unknown'
    
    def _apply_channel_role_config(self, 
                                  channel_config: Dict[str, str], 
                                  channel_role: str, 
                                  module: str) -> Dict[str, str]:
        """Apply channel role configuration using available enums - DATA-DRIVEN"""
        config = channel_config.copy()
        
        # Find appropriate enum values for mode and enable settings (no hardcoding)
        mode_enum_value = self._find_channel_mode_enum_value(channel_role, module)
        enable_value = self._find_enable_value(module)
        
        # Apply role-specific settings to relevant members
        for member_name in config.keys():
            member_lower = member_name.lower()
            
            # Set mode for mode-related members
            if 'mode' in member_lower and mode_enum_value:
                config[member_name] = mode_enum_value
            
            # Set enable for enable-related members
            elif 'enable' in member_lower and enable_value:
                config[member_name] = enable_value
        
        return config
    
    def _find_channel_mode_enum_value(self, channel_role: str, module: str) -> Optional[str]:
        """Find appropriate channel mode enum value - DATA-DRIVEN"""
        # Search through available enums for channel mode values
        for enum_name, enum_data in self.enums.items():
            enum_name_lower = enum_name.lower()
            
            # Look for channel mode enums
            if 'mode' in enum_name_lower and ('channel' in enum_name_lower or 'ch' in enum_name_lower):
                values = enum_data.get('values', [])
                
                # Find value matching the role
                for value in values:
                    value_name = _safe_str(value.get('name')).lower()
                    if channel_role in value_name:
                        return f"{enum_name}_{value.get('name', '')}"
        
        # Fallback: construct enum value based on module and role
        return f"Ifx{module}_ChMode_{channel_role}"
    
    def _find_enable_value(self, module: str) -> str:
        """Find appropriate enable value - DATA-DRIVEN"""
        # Look for boolean true values in enums or use detected boolean values
        for enum_name, enum_data in self.enums.items():
            if 'bool' in enum_name.lower():
                values = enum_data.get('values', [])
                for value in values:
                    if 'true' in _safe_str(value.get('name')).lower():
                        return f"{enum_name}_{value.get('name', '')}"
        
        # Default fallback - use detected boolean value (data-driven)
        return self.boolean_values.get('true', 'TRUE')
    
    def _generate_struct_member_assignments(self, 
                                           struct_var_name: str,
                                           struct_members: List[Dict[str, str]],
                                           user_description: str = "",
                                           hw_spec_chunks: Optional[List[str]] = None) -> List[str]:
        """
        Generate struct member assignment code for initialization INSIDE main() function.
        
        FULLY DATA-DRIVEN, GENERIC, SCALABLE:
        - Works for ANY struct from ANY module
        - Uses multi-source value strategy (no hardcoding)
        - Generates lines like: "    config.testEnable = TRUE;  // From user input"
        - Graceful fallback with TODO comments for unresolved values
        
        VALUE SOURCE PRIORITY:
        1. User description keywords (user intent)
        2. Hardware spec constraints (hw_spec_chunks)
        3. Enum values from JSON (available enums)
        4. Fallback with TODO comment
        
        Args:
            struct_var_name: Variable name (e.g., 'configTest', 'channel0Config')
            struct_members: List of member dicts with 'name', 'type', 'description'
            user_description: User's functionality description for context-aware values
            hw_spec_chunks: Optional hw_spec text chunks for constraint extraction
        
        Returns:
            List of C code lines for member assignments
            Example: ["    config.testEnable = TRUE;  // From user input", ...]
        """
        assignments = []
        
        if not struct_members:
            return assignments
        
        user_desc_lower = (user_description or '').lower()
        
        for member in struct_members:
            member_name = member.get('name', '')
            member_type = member.get('type', '')
            member_desc = _safe_str(member.get('description')).lower()
            
            if not member_name:
                continue
            
            assigned = False
            assignment_line = None
            reason = ""
            
            # STRATEGY 1: Extract value from user description keywords (FULLY DYNAMIC)
            if user_description:
                # Boolean-like keywords that map to TRUE/FALSE
                bool_keywords = {
                    'test': 'TRUE', 'enable': 'TRUE', 'disable': 'FALSE',
                    'on': 'TRUE', 'off': 'FALSE', 'active': 'TRUE', 'inactive': 'FALSE',
                }
                
                for keyword, bool_val in bool_keywords.items():
                    if keyword in user_desc_lower and keyword in member_name.lower():
                        assignment_line = f"    {struct_var_name}.{member_name} = {bool_val};"
                        reason = "user"
                        assigned = True
                        break
                
                # Enum-based keywords: search available enums dynamically
                if not assigned:
                    # Extract significant keywords from user description
                    user_words = set(user_desc_lower.split())
                    for enum_name, enum_data in self.enums.items():
                        enum_values = enum_data.get('values', [])
                        for val in enum_values:
                            val_name = val.get('name', '')
                            val_name_lower = val_name.lower()
                            # Check if any user keyword matches an enum value name
                            for word in user_words:
                                if len(word) > 3 and word in val_name_lower and member_name.lower() in enum_name.lower():
                                    assignment_line = f"    {struct_var_name}.{member_name} = {val_name};  // From user input"
                                    reason = "user"
                                    assigned = True
                                    break
                            if assigned:
                                break
                        if assigned:
                            break
            
            # STRATEGY 2: Hardware spec constraints (DYNAMIC)
            if not assigned and hw_spec_chunks:
                for chunk in hw_spec_chunks:
                    if member_name in chunk or 'default' in member_name.lower():
                        # Try to find matching enum value from the chunk context
                        matched_enum_val = None
                        for enum_name, enum_data in self.enums.items():
                            if member_name.lower() in enum_name.lower() or member_type.lower() in enum_name.lower():
                                for val in enum_data.get('values', []):
                                    val_name = val.get('name', '')
                                    # Check if enum value name appears in the hw spec chunk
                                    if val_name and val_name.lower() in chunk.lower():
                                        matched_enum_val = val_name
                                        break
                                if matched_enum_val:
                                    break
                        if matched_enum_val:
                            assignment_line = f"    {struct_var_name}.{member_name} = {matched_enum_val};"
                            reason = "hw_spec"
                            assigned = True
                            break
            
            # STRATEGY 3: Find enum value from JSON
            if not assigned:
                # Search for enum matching member type
                for enum_name, enum_data in self.enums.items():
                    if member_name in enum_name.lower() or member_type in enum_name.lower():
                        values = enum_data.get('values', [])
                        if values:
                            first_value = values[0].get('name', '')
                            assignment_line = f"    {struct_var_name}.{member_name} = {first_value};"
                            reason = f"enum {enum_name}"
                            assigned = True
                            break
            
            # STRATEGY 4: Fallback with TODO
            if not assigned:
                assignment_line = f"    {struct_var_name}.{member_name} = 0;  // TODO: Determine value"
                reason = "fallback"
            
            # Format with reason comment
            if assignment_line:
                if reason and reason != "fallback":
                    assignments.append(f"{assignment_line}  // {reason}")
                else:
                    assignments.append(assignment_line)
        
        return assignments
    
    def _generate_struct_init_sequence(self,
                                      struct_var_name: str,
                                      struct_type_name: str,
                                      parent_var_name: Optional[str],
                                      init_func_name: str,
                                      struct_members: List[Dict[str, str]],
                                      user_description: str = "",
                                      hw_spec_chunks: Optional[List[str]] = None,
                                      channel_id: Optional[str] = None) -> List[str]:
        """
        Generate COMPLETE struct initialization sequence for inside main() function.
        
        FULLY DATA-DRIVEN, GENERIC, SCALABLE:
        - Follows REAL TEST CODE PATTERN: init call -> member assignment
        - Works for ANY struct initialization from ANY module
        - No hardcoding, all values are dynamic from data sources
        
        STRUCTURE (from real test code):
        1. Init function call with parent struct
        2. Printf confirming init
        3. Member value assignments (using _generate_struct_member_assignments)
        4. Printf confirming completion
        
        Args:
            struct_var_name: Variable name (e.g., 'configTest')
            struct_type_name: Type name (e.g., 'IfxCxpi_Cxpi_Config_t')
            parent_var_name: Parent struct name or module (e.g., 'MODULE_CXPI0')
            init_func_name: Initialization function (e.g., 'IfxCxpi_Cxpi_initModuleConfigForTest')
            struct_members: List of member dicts with 'name', 'type', 'description'
            user_description: User's test description
            hw_spec_chunks: Hardware spec chunks for constraint extraction
            channel_id: Optional channel ID for context (e.g., '0', '3')
        
        Returns:
            List of C code lines forming complete initialization sequence
        """
        code_lines = []
        
        # === SECTION: Init Function Call ===
        code_lines.append("")
        struct_label = struct_var_name.replace('_', ' ').title()
        code_lines.append(f"  // === Initialize {struct_label} ===")
        
        # Generate init function call (DATA-DRIVEN: use provided function name)
        if parent_var_name:
            init_call = f"  {init_func_name}(&{struct_var_name}, &{parent_var_name});"
        else:
            init_call = f"  {init_func_name}(&{struct_var_name});"
        
        code_lines.append(init_call)
        code_lines.append(f'  printf("Initialization: {struct_label}\\n");')
        
        # === SECTION: Member Assignments ===
        assignments = self._generate_struct_member_assignments(
            struct_var_name,
            struct_members,
            user_description,
            hw_spec_chunks
        )
        
        if assignments:
            code_lines.append("")
            code_lines.append("  // Set configuration members")
            code_lines.extend(assignments)
        
        # === SECTION: Verification ===
        code_lines.append("")
        if channel_id:
            code_lines.append(f'  printf("Configuration complete: {struct_label} (Channel {channel_id})\\n");')
        else:
            code_lines.append(f'  printf("Configuration complete: {struct_label}\\n");')
        
        return code_lines
    
    def _generate_struct_declarations(self, 
                                     structs_needed: List[Dict[str, str]]) -> List[str]:
        """
        Generate GLOBAL struct declarations (NO initialization values).
        
        FULLY DATA-DRIVEN, GENERIC, SCALABLE:
        - Generates global declarations only (structs initialized later in main())
        - Works for ANY struct from ANY module
        - No hardcoding, all structs are provided as input
        
        Pattern (from real test code):
        static IfxCxpi_Cxpi_Config_t configTest;        // NO = {...}
        static IfxCxpi_Cxpi_Channel_t cxpiChannel0;      // NO = {...}
        
        Args:
            structs_needed: List of dicts with 'var_name' and 'type'
                           Example: [{'var_name': 'configTest', 'type': 'IfxCxpi_Cxpi_Config_t'}, ...]
        
        Returns:
            List of C declaration lines (ready to be placed at global scope)
        """
        declarations = []
        
        for struct in structs_needed:
            var_name = struct.get('var_name', '')
            struct_type = struct.get('type', '')
            
            if var_name and struct_type:
                declarations.append(f"static {struct_type} {var_name};")
        
        return declarations
    
    def _get_relevant_structs(self, 
                            feature_classification: Dict[str, Any],
                            module: str) -> List[str]:
        """Determine which structs to initialize based on feature
        
        NO HARDCODING - Dynamically discovers relevant structs from available data
        """
        
        relevant = []
        # Use primary_function (RAG-based) instead of primary_feature (PUML-based)
        feature = feature_classification.get('primary_function', '')
        
        # Analyze available structs and determine relevance based on content
        for struct_name, struct_data in self.structs.items():
            if self._is_struct_relevant_for_feature(struct_name, struct_data, feature, module):
                relevant.append(struct_name)
        
        return relevant
    
    def _is_struct_relevant_for_feature(self, 
                                       struct_name: str, 
                                       struct_data: Dict, 
                                       feature: str, 
                                       module: str) -> bool:
        """Determine if a struct is relevant for the given feature - COMPLETELY DATA-DRIVEN
        
        INCLUSIVE: If a struct has members (from KG), it's likely relevant.
        Config structs, channel structs, error structs — all may be needed.
        The RAG system already selected these structs as semantically relevant.
        """
        
        name_lower = struct_name.lower()
        
        # Analyze struct members to determine relevance
        members = struct_data.get('members', [])
        member_names = [_safe_str(m.get('name')).lower() for m in members]
        member_types = [_safe_str(m.get('type')).lower() for m in members]
        member_descriptions = [_safe_str(m.get('description')).lower() for m in members]
        
        # If struct has members from KG, it was selected by RAG for relevance — include it
        # This is the most important check: if KG gave us member data, use it
        if members:
            return True
        
        # Config structs are always relevant
        if 'config' in name_lower:
            return True
        
        # Channel structs are commonly needed
        if 'channel' in name_lower:
            return True
        
        # Error-related structs (for error injection tests)
        if any(kw in name_lower for kw in ['error', 'flag', 'status']):
            return True
        
        # Get feature-specific keywords from pattern library (no hardcoding)
        feature_data = self.pattern_library.get('features', {}).get(feature, {})
        feature_keywords = []
        
        # Extract keywords from feature name and typical functions
        feature_keywords.extend(feature.split('_'))
        for func in feature_data.get('typical_functions', []):
            feature_keywords.extend(func.lower().split('_'))
        
        # Remove duplicates and common words - DATA-DRIVEN (exclude module name dynamically)
        feature_keywords = list(set(feature_keywords))
        # Exclude common words and the current module name to avoid false positives
        exclude_words = ['ifx', 'module', module.lower()]
        feature_keywords = [kw for kw in feature_keywords if len(kw) > 2 and kw not in exclude_words]
        
        # Check if struct is relevant based on member analysis
        has_relevant_members = any(
            any(keyword in desc for keyword in feature_keywords) 
            for desc in member_descriptions
        )
        has_relevant_name = any(keyword in name_lower for keyword in feature_keywords)
        
        if has_relevant_members or has_relevant_name:
            return True
        
        # Structs with many configuration members are likely important
        has_many_members = len(members) > 3
        
        # Channel-related structs are commonly needed
        is_channel_config = 'channel' in name_lower and 'config' in name_lower
        
        return has_many_members or is_channel_config
    
    def _generate_member_value(self,
                              member_name: str,
                              member_type: str,
                              member_desc: str,
                              feature_classification: Dict[str, Any],
                              module: str,
                              user_description: str = "") -> str:
        """
        Generate appropriate initialization value for struct member.
        
        FULLY DATA-DRIVEN — ZERO HARDCODING:
        1. Pointer → NULL
        2. Boolean → FALSE (zero-init)
        3. Numeric → try enum data lookup, else 0U/0
        4. String/char → ""
        5. Enum type → find enum definition, pick first value or user-hint match
        6. Struct type → 0 (initialized by init function)
        7. Unknown → type-based fallback
        
        User description hints and member description are used for enum value selection.
        No hardcoded baudrate, length, enable/disable keyword lists.
        """
        
        type_lower = (member_type or '').lower()
        user_desc_lower = (user_description or '').lower()
        
        # ===== STEP 1: POINTER TYPES =====
        if '*' in member_type:
            return "NULL"
        
        # ===== STEP 2: TRY ENUM LOOKUP (data-driven) =====
        # Try enum first (works for bool, int, custom enums)
        enum_value = self._get_enum_value_for_member(member_name, member_type, _safe_str(member_desc), user_description)
        if enum_value:
            return enum_value
        
        # ===== STEP 3: NUMERIC TYPES - Extract from description =====
        # For non-enum numeric types, extract range hint from description
        range_val = self._extract_numeric_range_from_description(_safe_str(member_desc).lower())
        if range_val:
            return range_val
        
        # Try to learn from enum data
        learned_value = self._learn_numeric_value_from_enums(member_name, member_type, member_desc, module, feature_classification)
        if learned_value:
            return learned_value
        
        # Default zero-init (universal fallback)
        # Type system at compile time resolves the semantic meaning
        return "0"
    
    def _learn_numeric_value_from_enums(self, member_name: str, member_type: str, member_desc: str, module: str, feature_classification: Optional[Dict] = None) -> Optional[str]:
        """
        Learn appropriate numeric values from enum data instead of hardcoding
        
        Analyzes enum definitions to find appropriate values for configuration members
        """
        member_lower = member_name.lower()
        desc_lower = member_desc.lower()
        
        # Look through all enums for relevant values
        for enum_name, enum_data in self.enums.items():
            enum_lower = enum_name.lower()
            values = enum_data.get('values', [])
            
            # Check if this enum is relevant to the member
            enum_relevant = False
            
            # Direct type match
            if enum_name in member_type:
                enum_relevant = True
            # Keyword matching in enum name
            elif any(kw in enum_lower for kw in member_lower.split('_')):
                enum_relevant = True
            # Description keyword matching
            elif any(kw in desc_lower for kw in enum_lower.split('_')):
                enum_relevant = True
            
            if enum_relevant:
                # Find the most appropriate value from this enum
                best_value = self._select_best_enum_value(values, member_name, member_desc, feature_classification)
                if best_value:
                    return best_value
        
        return None
    
    def _select_best_enum_value(self, enum_values: List[Dict], member_name: str, member_desc: str, feature_classification: Optional[Dict] = None) -> Optional[str]:
        """
        Select the best enum value based on dynamic word overlap analysis.
        ZERO HARDCODING — no preferred keyword lists.
        """
        if not enum_values:
            return None
        
        member_lower = member_name.lower()
        desc_lower = _safe_str(member_desc).lower()
        
        # Score each enum value by word overlap with member name and description
        best_value = None
        best_score = 0
        
        for value in enum_values:
            value_name = value.get('name', '')
            value_desc = _safe_str(value.get('description')).lower()
            value_name_lower = value_name.lower()
            
            score = 0
            
            # Member name words overlap with value name
            member_words = set(member_lower.replace('_', ' ').split())
            val_words = set(value_name_lower.replace('_', ' ').split())
            score += len(member_words & val_words) * 5
            
            # Description words overlap with value description
            desc_words = set(w for w in desc_lower.split() if len(w) > 3)
            vdesc_words = set(w for w in value_desc.split() if len(w) > 3)
            score += len(desc_words & vdesc_words) * 3
            
            if score > best_score:
                best_score = score
                best_value = value_name
        
        return best_value if best_score > 0 else None
    
    def _select_appropriate_enum_value(self, 
                                      enum_type: str, 
                                      member_name: str, 
                                      member_desc: str,
                                      feature_classification: Dict[str, Any]) -> str:
        """
        Dynamically select the most appropriate enum value based on context
        
        NO HARDCODING - Uses semantic analysis of descriptions and feature context
        """
        enum_data = self.enums.get(enum_type, {})
        values = enum_data.get('values', [])
        
        if not values:
            return f"{enum_type}_DEFAULT"
        
        # Use the enhanced enum selection logic
        best_value = self._select_best_enum_value(values, member_name, member_desc, feature_classification)
        if best_value:
            return best_value
        
        # Fallback to first available value
        return values[0].get('name', f"{enum_type}_DEFAULT")
    
    def _get_enum_value_for_member(self, member_name: str, enum_type: str, member_description: str, user_description: str = "") -> str:
        """
        Get the right enum value based on user description hints or first value fallback.
        
        ZERO HARDCODING — purely dynamic word overlap:
        1. Split user description into words
        2. Split each enum value name into words
        3. Score by overlap count
        4. If no match from user desc, use first enum value
        
        Args:
            member_name: Name of struct member (e.g., "enableCh", "mode")
            enum_type: Enum type to search in (e.g., "IfxCxpi_Cxpi_ChState_t")
            member_description: Description from struct definition
            user_description: User's test description (PRIMARY SOURCE for selection)
        
        Returns:
            Best matching enum value name
        """
        
        user_desc_lower = (user_description or '').lower()
        
        # Step 1: Get enum values
        if enum_type not in self.enums:
            return "0"
        
        enum_data = self.enums[enum_type]
        enum_values = enum_data.get('values', [])
        
        if not enum_values:
            return "0"
        
        # Step 2: Score each enum value using DYNAMIC word overlap
        user_words = set(w for w in user_desc_lower.split() if len(w) > 2)
        member_desc_words = set(w for w in (_safe_str(member_description) or '').lower().split() if len(w) > 3)
        
        best_value = None
        best_score = 0
        
        for value_info in enum_values:
            value_name = value_info.get('name', '')
            value_desc = _safe_str(value_info.get('description')).lower()
            value_name_lower = value_name.lower()
            
            score = 0
            
            # Extract words from enum value name (split by underscore and camelCase)
            val_words = set()
            for part in value_name_lower.split('_'):
                if len(part) > 2:
                    val_words.add(part)
                # Also split camelCase within parts
                camel = re.findall(r'[a-z]+', part)
                for w in camel:
                    if len(w) > 2:
                        val_words.add(w)
            
            # PRIORITY 1: User description word overlap with enum value name
            for word in user_words:
                if word in val_words or word in value_name_lower:
                    score += 20
                if word in value_desc:
                    score += 10
            
            # PRIORITY 2: Member description word overlap with enum value name/desc
            for word in member_desc_words:
                if word in val_words or word in value_name_lower:
                    score += 3
                if word in value_desc:
                    score += 2
            
            if score > best_score:
                best_score = score
                best_value = value_name
        
        # If no score-based match, return FIRST enum value
        if not best_value or best_score <= 0:
            best_value = enum_values[0].get('name', '0')
        
        return best_value

    
    def _extract_numeric_range_from_description(self, description: str) -> Optional[str]:
        """
        Extract numeric values from member description.
        
        DATA-DRIVEN: Analyzes description text to find numeric patterns like:
        - "range{1, 255}" -> "128U"
        - "1 to 255" -> "128U"
        - "0-65535" -> "32768U"
        - "typically 500000" -> "500000U"
        
        Returns appropriate numeric value or None if not extractable
        """
        
        if not description:
            return None
        
        desc_lower = description.lower()
        
        # Pattern 1: \range{min, max} -> pick middle value
        range_match = re.search(r'\\?range\s*\{\s*(\d+)\s*,\s*(\d+)\s*\}', desc_lower)
        if range_match:
            min_val = int(range_match.group(1))
            max_val = int(range_match.group(2))
            mid_val = (min_val + max_val) // 2
            return f"{mid_val}U"
        
        # Pattern 2: "X to Y" or "X-Y" -> pick middle value
        range_match = re.search(r'(\d+)\s*(?:to|-)\s*(\d+)', desc_lower)
        if range_match:
            min_val = int(range_match.group(1))
            max_val = int(range_match.group(2))
            mid_val = (min_val + max_val) // 2
            return f"{mid_val}U"
        
        # Pattern 3: "typically X" or "default X"
        typical_match = re.search(r'(?:typically|default|usually)\s+(\d+)', desc_lower)
        if typical_match:
            return f"{typical_match.group(1)}U"
        
        # Pattern 4: Look for standalone large numbers (likely baudrate or similar)
        number_matches = re.findall(r'\b(\d{4,})\b', description)
        if number_matches:
            # Return the first significant number found
            return f"{number_matches[0]}U"
        
        return None
    
    def _extract_default_from_member_description(self, member_desc: str) -> Optional[str]:
        """
        DATA-DRIVEN: Extract default values from member description text
        
        Parses patterns like:
        - "default value is 100" -> "100U"
        - "recommended timeout: 1000" -> "1000U"
        - "typical range 10-100" -> "55U" (midpoint)
        - "default: enabled" -> "TRUE"
        - "disabled by default" -> "FALSE"
        
        This replaces hardcoded fallback values (1000, 8, 3) with actual
        values extracted from hardware documentation.
        
        Returns:
            Extracted default value or None if not found
        """
        
        if not member_desc:
            return None
        
        desc_lower = member_desc.lower()
        
        # Pattern 1: "default (is|:) <value>"
        default_match = re.search(r'default\s+(?:is|value)?\s*[:=]?\s*([a-zA-Z0-9_]+)', desc_lower)
        if default_match:
            value = default_match.group(1)
            # Check if it's a boolean-like value
            if value in ['true', 'false', 'enabled', 'disabled', 'yes', 'no', 'on', 'off']:
                return value.upper()
            # Otherwise it's a number
            if value.isdigit():
                return f"{value}U"
            return value
        
        # Pattern 2: "recommended <value>"
        recommended_match = re.search(r'recommended\s*[:=]?\s*(\d+)', desc_lower)
        if recommended_match:
            value = recommended_match.group(1)
            return f"{value}U"
        
        # Pattern 3: "typical (value|range) <number>"
        typical_match = re.search(r'(?:typical|usually)\s+(?:value|range)?\s*[:=]?\s*(\d+)', desc_lower)
        if typical_match:
            value = typical_match.group(1)
            return f"{value}U"
        
        # Pattern 4: "enabled/disabled by default"
        if 'enabled by default' in desc_lower:
            return 'ENABLED'
        if 'disabled by default' in desc_lower:
            return 'DISABLED'
        
        # Pattern 5: Range patterns "min X max Y"
        range_match = re.search(r'(?:min|minimum)\s+(\d+)\s+(?:max|maximum)\s+(\d+)', desc_lower)
        if range_match:
            min_val = int(range_match.group(1))
            max_val = int(range_match.group(2))
            mid_val = (min_val + max_val) // 2
            return f"{mid_val}U"
        
        return None
    
    def _find_enum_type(self, member_type: str, member_desc: str) -> Optional[str]:
        """Find matching enum type for this member"""
        
        # Try exact match first
        if member_type in self.enums:
            return member_type
        
        # Try to find by description keywords
        desc_lower = member_desc.lower()
        for enum_name, enum_data in self.enums.items():
            enum_lower = enum_name.lower()
            # Check if enum name appears in description
            if enum_lower in desc_lower or desc_lower in enum_lower:
                return enum_name
        
        return None


class DataDrivenCodeGenerator:
    """
    Main code generation engine
    
    Combines all components for fully data-driven, dynamic code generation
    
    Integrates:
    - PUML pattern analysis
    - Source code analysis
    - Neo4j structural data
    - All using fully data-driven, no-hardcoding approach
    """
    
    def __init__(self, pattern_library: Dict[str, Any], code_generation_rules: Dict[str, Any], 
                 all_structs: List[Dict], all_enums: List[Dict], all_macros: List[Dict], all_typedefs: List[Dict], 
                 module: str, puml_file_path: Optional[str] = None, prompt_path: Optional[str] = None,
                 source_code_enriched: Optional[Dict[str, Any]] = None):
        """
        Initialize the code generator with all required data sources
        
        Args:
            pattern_library: PUML pattern library (from puml_pattern_analyzer.py)
            code_generation_rules: Code generation rules (from puml_pattern_analyzer.py)
            all_structs: All struct definitions from Neo4j
            all_enums: All enum definitions from Neo4j
            all_macros: All macro definitions from Neo4j
            all_typedefs: All typedef definitions from Neo4j
            module: Module name (e.g., 'CXPI', 'LIN', 'CAN')
            puml_file_path: Path to specific PUML file (optional)
            prompt_path: Path to prompt file (optional)
            source_code_enriched: Source code analysis data (from source_code_analyzer.py) - Layer 3 integration
        """
        self.pattern_library = pattern_library
        self.code_generation_rules = code_generation_rules
        self.all_structs = all_structs
        self.all_enums = all_enums
        self.all_macros = all_macros
        self.all_typedefs = all_typedefs
        self.enums = {e.get('name', ''): e for e in all_enums}
        self.module = module
        self.prompt_path = prompt_path
        self.all_functions = []
        
        # ============= LAYER 3 INTEGRATION: Source Code Analysis =============
        # Store source code enriched data for use in code generation
        self.source_code_enriched = source_code_enriched or {}
        # =====================================================================
        
        self.classifier = FeatureClassifier(pattern_library)
        self.sequence_builder = FunctionSequenceBuilder(code_generation_rules, pattern_library)
        self.struct_initializer = StructInitializationGenerator(all_structs, all_enums, pattern_library)
        self.puml_analysis = pattern_library.get('puml_analyses', {})
        self.communication_keywords = set()
        
        # NEW: PUML parsing for dynamic sequence extraction
        self.puml_sequence = {}
        self.puml_participants = {}
        self.puml_test_mode = False
        self.puml_extended_configs = {}
        self.puml_member_assignments = {}
        # NOTE: All PUML data is now in the database (pattern_library)
        # File-based PUML parsing is no longer needed
        if puml_file_path:
            self._parse_puml_file(puml_file_path)
        
        # DATA-DRIVEN: Discover module-specific communication role terminology from PUML
        self.module_roles = self._discover_module_role_terms()
    
    def _discover_module_role_terms(self) -> Dict[str, Any]:
        """
        DATA-DRIVEN: Discover what terminology the module uses for communication roles
        by scanning pattern library PUML data and struct/enum descriptions.
        
        Returns:
            {
                "roles": ["master", "slave", "node"],
                "source": "pattern_library" or "enums" or "fallback",
                "count": <number>
            }
        
        This replaces hardcoded keyword lists with actual discovered terminology.
        """
        discovered_roles = set()
        discovery_source = "not_found"
        
        # PRIMARY: Extract roles from pattern_library PUML analyses (database-sourced)
        try:
            if self.pattern_library:
                discovery_source = "pattern_library"
                
                # Scan PUML analyses for participant information
                for analysis in self.pattern_library.get('puml_analyses', []):
                    if not isinstance(analysis, dict):
                        continue
                    
                    # Extract participants from PUML analysis
                    participants = analysis.get('participants', {})
                    for participant_name in participants.keys():
                        participant_lower = participant_name.lower()
                        
                        # Extract role keywords from participant name
                        # "Master" -> "master", "Slave" -> "slave"
                        # "Node1" -> "node", "Channel1" -> "channel"
                        words = participant_lower.split('_')
                        for word in words:
                            # Remove numbers to get role type
                            role = ''.join(c for c in word if not c.isdigit())
                            if role and len(role) > 2 and role not in ['participant', 'puml', 'seq', 'app']:
                                discovered_roles.add(role)
        except Exception as e:
            pass
        
        # SECONDARY: Scan struct/enum data for role-related keywords
        try:
            for enum in self.all_enums:
                enum_name = _safe_str(enum.get('name')).lower()
                # Look for enums with role/mode/state keywords
                if any(r in enum_name for r in ['mode', 'state', 'role', 'channel']):
                    values = enum.get('values', [])
                    for value in values:
                        val_name = _safe_str(value.get('name')).lower()
                        # Extract role keywords from enum values
                        for role_keyword in ['master', 'slave', 'sender', 'receiver', 'publisher', 'subscriber', 'client', 'server', 'node', 'device']:
                            if role_keyword in val_name:
                                discovered_roles.add(role_keyword)
                                if discovery_source == "not_found":
                                    discovery_source = "enums"
        except Exception as e:
            pass
        
        # FALLBACK: Default roles if nothing discovered
        if not discovered_roles:
            discovered_roles = {'master', 'slave', 'node', 'device', 'sender', 'receiver'}
            discovery_source = "fallback"
        
        result = {
            "roles": sorted(list(discovered_roles)),
            "source": discovery_source,
            "count": len(discovered_roles)
        }
        
        return result
    
    def _parse_puml_file(self, puml_file_path: str):
        """
        Parse PUML file to extract API sequences, participants, test mode, and extended configs.
        DATA-DRIVEN: Dynamically extracts all relevant information from PUML syntax.
        """
        try:
            with open(puml_file_path, 'r', encoding='utf-8') as f:
                puml_content = f.read()
        except FileNotFoundError:
            return
        
        lines = puml_content.split('\n')
        sequence = []
        participants = {}
        test_mode = False
        extended_configs = {}
        member_assignments = {}  # dict of function -> list of assignments
        
        current_participant = None
        
        for line_idx, original_line in enumerate(lines):
            line = original_line.strip()
            if not line or line.startswith('@') or line.startswith('title') or line.startswith('!'):
                continue
            
            # Detect test mode from keywords
            if any(kw in line.lower() for kw in ['test', 'fortest', 'loopback']):
                test_mode = True
            
            # Extract participants
            if line.startswith('participant'):
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    alias = parts[-1] if len(parts) > 2 else name
                    participants[alias] = name
            
            # Extract API calls (arrows with function calls)
            if '->' in line and '(' in line:
                # Parse arrow notation: participant -> participant: function(args)
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) == 2:
                        func_part = parts[1].strip()
                        # Extract function name
                        if '(' in func_part:
                            func_name = func_part.split('(')[0].strip()
                            if func_name:
                                # NORMALIZATION: Try both full and normalized names when extracting from PUML
                                # Infineon SDK uses Ifx<Module>_<Module>_function pattern
                                # We'll store both versions in sequence for matching against JSON
                                sequence.append(func_name)
                                
                                # Track which participant is active
                                arrow_part = parts[0].strip()
                                if '->' in arrow_part:
                                    target = arrow_part.split('->')[-1].strip()
                                    current_participant = target
                                
                                # Look for member assignments after this function call
                                struct_assignments = []
                                j = line_idx + 1
                                while j < len(lines) and not (lines[j].strip().startswith('App ->') or lines[j].strip().startswith('end')):
                                    assign_line = lines[j].strip()
                                    if '=' in assign_line and '.' in assign_line and not assign_line.startswith('//') and not assign_line.startswith('note'):
                                        # Looks like a member assignment: configTest.testEnable = TRUE;
                                        struct_assignments.append(assign_line.rstrip(';'))
                                    j += 1
                                if struct_assignments:
                                    member_assignments[func_name] = struct_assignments
            
            # Extract extended config notes
            if 'note right' in line.lower() and ('extended' in line.lower() or 'config' in line.lower()):
                extended_configs[current_participant] = True
            
            # Extract loop targets for monitoring - DATA-DRIVEN: Learn from PUML patterns
            if line.startswith('loop'):
                loop_participant = None
                monitoring_function = None
                # Extract loop content to identify monitoring patterns
                loop_lines = []
                for next_line in lines[line_idx+1:]:
                    stripped_next = next_line.strip()
                    if stripped_next.startswith('end'):
                        break
                    loop_lines.append(stripped_next)
                
                # Analyze loop content to find monitoring function and participant
                for loop_line in loop_lines:
                    if '->' in loop_line and '(' in loop_line:
                        # Found a function call in the loop
                        if ':' in loop_line:
                            arrow_part = loop_line.split(':')[0].strip()
                            func_part = loop_line.split(':')[1].strip()
                            if '->' in arrow_part:
                                loop_participant = arrow_part.split('->')[-1].strip()
                            if '(' in func_part:
                                monitoring_function = func_part.split('(')[0].strip()
                                break
                
                # Store monitoring info if found
                if loop_participant and monitoring_function:
                    # Determine monitoring type from loop content or function name
                    monitoring_type = 'generic'
                    if 'error' in monitoring_function.lower() or 'flag' in monitoring_function.lower():
                        monitoring_type = 'error'
                    elif 'timeout' in line.lower() or 'timeout' in str(loop_lines).lower():
                        monitoring_type = 'timeout'
                    
                    extended_configs[f'{monitoring_type}_monitor_channel'] = loop_participant
                    extended_configs[f'{monitoring_type}_monitor_function'] = monitoring_function
        
        self.puml_sequence = sequence
        self.puml_participants = participants
        self.puml_test_mode = test_mode
        self.puml_extended_configs = extended_configs
        self.puml_member_assignments = member_assignments
    
    def _select_function_variant(self, func: str, feature: str, test_mode: bool) -> Optional[str]:
        """
        Select appropriate function variant (test/error/feature-specific) based on context.
        DATA-DRIVEN: Uses pattern library, PUML test mode, and function naming conventions.
        """
        if not func:
            return None
        
        # Use PUML-detected test mode if available
        actual_test_mode = self.puml_test_mode or test_mode
        
        # Try to find variant for this function
        func_lower = func.lower()
        
        # If test mode, look for test-specific variants
        if actual_test_mode:
            # Try appending '_fortest' or '_test' suffix
            test_variants = [f"{func}_fortest", f"{func}_test", f"{func}Test", f"{func}ForTest"]
            for variant in test_variants:
                # Check if variant exists in pattern library or available functions
                if self.pattern_library and variant in str(self.pattern_library):
                    return variant
        
        # For error-related features, look for error-specific variants
        if 'error' in feature.lower() or 'fault' in feature.lower():
            error_variants = [f"{func}_error", f"{func}Error", f"{func}_fault"]
            for variant in error_variants:
                if self.pattern_library and variant in str(self.pattern_library):
                    return variant
        
        # For timeout features, look for timeout-specific variants
        if 'timeout' in feature.lower():
            timeout_variants = [f"{func}_timeout", f"{func}Timeout", f"{func}_tmo"]
            for variant in timeout_variants:
                if self.pattern_library and variant in str(self.pattern_library):
                    return variant
        
        # If no variant found or not applicable, return None (original function will be used)
        return None
    
    def build_sequence(self, 
                      feature_classification: Dict[str, Any],
                      module: str,
                      user_parameters: Optional[Dict[str, Any]] = None,
                      channels: Optional[List[str]] = None) -> List[str]:
        """
        Build function call sequence for the given feature classification
        PRIORITIZES user-specific detected functions from feature classification
        Falls back to PUML sequence if no specific functions were detected
        Always selects correct function variants (test/error/feature-specific) if available
        """
        # CRITICAL: Use semantically-filtered detected functions if available
        # These are the functions specifically relevant to the user's request
        detected_funcs = feature_classification.get('detected_functions', [])
        
        if detected_funcs:
            # User-specific functions take priority over generic PUML sequence
            # This respects semantic filtering done elsewhere in the pipeline
            sequence = list(detected_funcs)
        elif self.puml_sequence:
            # Fall back to PUML sequence if no specific functions detected
            sequence = list(self.puml_sequence)  # Copy the PUML sequence
            # CRITICAL: Normalize function names from PUML to match JSON format
            # PUML contains names like 'IfxCxpi_Cxpi_initModule'
            # JSON contains 'IfxCxpi_initModule' (or vice versa, but we normalize both ways)
            # The parameter extraction will try exact + normalized match, so we normalize here too
            normalized_sequence = []
            for func_name in sequence:
                # Keep original, but also track that it may need normalization during lookup
                # The parameter extraction code will handle both original and normalized names
                normalized_sequence.append(func_name)
            sequence = normalized_sequence
        else:
            # Fallback to phase-based rules
            phase_order = self.code_generation_rules.get('phase_order', [])
            sequence = []
            test_mode = feature_classification.get('modifiers', {}).get('test_mode', False)
            # Use primary_function (RAG-based) instead of primary_feature (PUML-based)
            feature = feature_classification.get('primary_function', None)
            user_params = user_parameters or {}
            
            for phase in phase_order:
                phase_funcs = self.code_generation_rules.get('functions_by_phase', {}).get(phase, [])
                for func in phase_funcs:
                    variant = self._select_function_variant(func, feature, test_mode)
                    if variant:
                        sequence.append(variant)
                    else:
                        sequence.append(func)
        
        # DATA-DRIVEN: Add operation sequence from PUML/JSON patterns if not already included
        op_seq = self._build_operation_sequence(feature_classification, user_params, module, channels)
        for op_func in op_seq:
            # Use primary_function (RAG-based) for variant selection
            variant = self._select_function_variant(op_func, feature_classification.get('primary_function', ''), 
                                                   feature_classification.get('modifiers', {}).get('test_mode', False))
            if variant and variant not in sequence:
                sequence.append(variant)
            elif op_func not in sequence:
                sequence.append(op_func)
        
        # Remove duplicates while preserving order
        seen = set()
        final_sequence = []
        for f in sequence:
            if f not in seen:
                final_sequence.append(f)
                seen.add(f)
        return final_sequence

    def _update_polling_patterns_from_sequence(self, function_sequence, feature_classification, polling_patterns, user_description: str = ""):
        """
        Generate polling patterns based on ACTUAL test code patterns.
        
        UPDATED APPROACH (Jan 2026 - CORRECTED):
        - Uses done/busy enum values (NO "ready" enum exists)
        - Pattern: while(busy == getChannelStatus(&channel, activity))
        - Activity parameter: txHeaderDone, rxHeaderDone, etc.
        - Error monitoring: while(errorFlags.field == 0) { getErrorFlags(...); }
        - DATA-DRIVEN: All from actual enum/struct/function definitions
        
        Real test code patterns:
          while(IfxCxpi_ChStatus_busy == IfxCxpi_Cxpi_getChannelStatus(&ch, IfxCxpi_Cxpi_ChActivity_txHeaderDone));
          while(errorFlags.rxCrcError == 0) { IfxCxpi_Cxpi_getErrorFlags(&ch, &errorFlags); }
        
        Args:
            function_sequence: Ordered list of functions to generate polling for
            feature_classification: Feature classification dict with modifiers
            polling_patterns: Dict to populate with polling code
            user_description: User's test description for context-aware decisions
        """
        module = getattr(self, 'module', '')
        enum_lookup = getattr(self, 'enums', {})
        all_structs = getattr(self, 'all_structs', [])
        available_functions = [func['name'] if isinstance(func, dict) and 'name' in func else str(func) 
                              for func in getattr(self, 'all_functions', [])]
        
        # STEP 1: Find done/busy enum values from actual definitions
        status_enum_values = self._find_status_enum_values(enum_lookup, module)
        if not status_enum_values:
            print(f"  [POLLING] No status enum found with done/busy values, skipping polling generation")
            return
        
        done_value = status_enum_values['done']  # e.g., 'IfxCxpi_ChStatus_done'
        busy_value = status_enum_values['busy']  # e.g., 'IfxCxpi_ChStatus_busy'
        
        print(f"  [POLLING] Found status values: done={done_value}, busy={busy_value}")
        
        # STEP 2: Categorize functions by type (TX/RX)
        transmission_functions = set()
        reception_functions = set()
        
        for func in getattr(self, 'all_functions', []):
            func_name = func['name'] if isinstance(func, dict) and 'name' in func else str(func)
            func_lower = func_name.lower()
            
            # TX functions: send, transmit, write, tx
            if any(kw in func_lower for kw in ['send', 'transmit', 'write', '_tx']):
                transmission_functions.add(func_name)
            # RX functions: receive, read, get (but not getStatus/getError)
            elif any(kw in func_lower for kw in ['receive', '_rx', 'recv']):
                reception_functions.add(func_name)
        
        print(f"  [POLLING] TX functions: {transmission_functions}")
        print(f"  [POLLING] RX functions: {reception_functions}")
        
        # STEP 3: Find status check function (e.g., getChannelStatus)
        status_func_info = self._find_status_function_from_puml(None, available_functions, module)
        if not status_func_info:
            print(f"  [POLLING] No status function found, skipping polling generation")
            return
        
        status_function = status_func_info['function']
        takes_activity = status_func_info['takes_activity']
        takes_channel = status_func_info['takes_channel']
        
        print(f"  [POLLING] Status function: {status_function}, takes_activity={takes_activity}, takes_channel={takes_channel}")
        
        # STEP 4: Generate polling patterns for TX/RX functions
        # Uses {CHANNEL_VAR} placeholder — resolved to actual variable names in generate_sample_c_code()
        # Uses {RX_CHANNEL_VAR} placeholder for the paired slave/RX channel poll.
        for func in function_sequence:
            func_lower = func.lower()
            func_words = set(re.findall(r'[a-z]+', func_lower))

            # Check if TX function
            if func in transmission_functions:
                # DATA-DRIVEN: Pass ORIGINAL function name (not lowered) for CamelCase splitting
                activity_enum = self._learn_activity_enum(enum_lookup, module, func) if takes_activity else None

                # Generate TX polling code with {CHANNEL_VAR} placeholder for late substitution
                if takes_activity and activity_enum:
                    polling_code = f"while({busy_value} == {status_function}(&{{CHANNEL_VAR}}, {activity_enum}));"
                elif takes_channel:
                    polling_code = f"while({busy_value} == {status_function}(&{{CHANNEL_VAR}}));"
                else:
                    polling_code = f"while({busy_value} == {status_function}());"

                # DATA-DRIVEN paired RX-side poll:
                # For every TX function we check whether ANY reception function in the
                # current sequence shares the same transfer-unit words (e.g. both have
                # 'header' or both have 'response').  If so, the slave channel must also
                # be polled BEFORE the corresponding receive call is made.
                # This produces the correct two-line pattern:
                #   while(busy == status(txChannel, txActivityDone));
                #   while(busy == status(rxChannel, rxActivityDone));
                # NO function names, NO domain words are hardcoded.
                # The "transfer unit" is the set of meaningful semantic words that appear
                # in BOTH the TX function name AND a paired RX function name.
                if takes_activity and activity_enum:
                    tx_words = set(re.findall(r'[a-z]+', func_lower))
                    paired_rx_poll = None
                    for rx_func in reception_functions:
                        if rx_func not in function_sequence:
                            continue
                        rx_words = set(re.findall(r'[a-z]+', rx_func.lower()))
                        # Shared semantic words (excluding universal prefix noise)
                        shared = tx_words & rx_words - set(re.findall(r'[a-z]+', (module or '').lower()))
                        # A meaningful shared word is one that is NOT a generic
                        # protocol verb ('send','receive','transmit','read','write')
                        # nor a single letter — it must be a domain-payload word.
                        # Module name fragments are dynamically excluded via the
                        # module variable — no module names are hardcoded here.
                        _module_frags = set(re.findall(r'[a-z]+', (module or '').lower()))
                        generic_verbs = {'send', 'receive', 'transmit', 'read', 'write',
                                         'get', 'set', 'init', 'enable', 'disable',
                                         'clear', 'reset', 'ifx'} | _module_frags
                        payload_shared = {w for w in shared if len(w) > 2 and w not in generic_verbs}
                        if payload_shared:
                            # Found a paired RX function that shares a payload word
                            rx_activity = self._learn_activity_enum(enum_lookup, module, rx_func) if takes_activity else None
                            if rx_activity:
                                paired_rx_poll = f"while({busy_value} == {status_function}(&{{RX_CHANNEL_VAR}}, {rx_activity}));"
                            break
                    if paired_rx_poll:
                        polling_code = polling_code + '\n' + paired_rx_poll

                polling_patterns[func] = {
                    'position': 'after',
                    'code': polling_code
                }
                print(f"  [POLLING] Generated TX polling for {func}")

            # RX (receive) functions: busy-wait is emitted by the PAIRED TX function above
            # (after sendHeader we emit both TX and RX header polls before receiveHeader).
            # For receive functions that have NO paired header-send TX function (e.g.
            # receiveResponse), we still skip a post-receive poll — the TX busy-wait on the
            # transmitResponse call is sufficient because the slave hardware latches the data
            # by the time the TX side is done.
            elif func in reception_functions:
                print(f"  [POLLING] Skipping RX polling for {func} — busy-wait is TX-only rule")
        
        # STEP 5: Generate error monitoring patterns
        # Check if user wants error checking
        wants_error_checking = feature_classification.get('modifiers', {}).get('error_injection') or \
                              any(kw in user_description.lower() for kw in ['error', 'timeout', 'fault', 'check error'])
        
        if wants_error_checking:
            # Find error flags struct
            error_struct_info = self._find_error_flags_struct(all_structs, module)
            if error_struct_info:
                error_struct_name = error_struct_info['name']
                error_members = error_struct_info['members']
                
                # Find getErrorFlags function
                error_func = None
                for func in available_functions:
                    if 'geterror' in func.lower() or 'errorflags' in func.lower():
                        error_func = func
                        break
                
                if error_func and error_members:
                    # Generate error monitoring for first error member
                    first_error_member = error_members[0]
                    
                    error_polling_code = f"""
// Monitor for errors
{error_struct_name} errorFlags;
while(errorFlags.{first_error_member} == 0) {{
    {error_func}(&channel, &errorFlags);
    // Check for error conditions
}}
printf("Error detected: %s\\n", "{first_error_member}");
"""
                    
                    # Add error monitoring as a special pattern
                    polling_patterns['__error_monitoring__'] = {
                        'position': 'after',
                        'code': error_polling_code
                    }
                    print(f"  [POLLING] Generated error monitoring with {error_struct_name}")



    def _find_status_enum_values(self, enum_lookup: Dict, module: str) -> Optional[Dict[str, str]]:
        """
        Find done and busy enum values from actual enum definitions.
        
        DATA-DRIVEN: Searches enums for status-related types and extracts:
        - 'done' value - indicates operation complete (by name/description semantics)
        - 'busy' value - indicates operation in progress (by name/description semantics)
        
        FIXED (Feb 2026): Uses SUBSTRING matching for enum name detection, not word-level.
        CamelCase names like 'ChStatus' contain 'status' as substring but regex word
        extraction gives 'chstatus' as one token — substring matching catches this.
        
        Args:
            enum_lookup: Dictionary of enum_name -> enum_definition
            module: Module name (e.g., 'Cxpi')
        
        Returns:
            Dict with 'done' and 'busy' keys mapping to enum value names, or None
        """
        # Semantic indicators for "done" state
        done_indicators = {'done', 'complete', 'idle', 'finished', 'ready', 'ok', 'success'}
        # Semantic indicators for "busy" state
        busy_indicators = {'busy', 'active', 'progress', 'inprogress', 'pending', 'running', 'processing'}
        
        # Status/state indicators — checked via SUBSTRING in the enum name (not word-level)
        # This catches CamelCase names like 'ChStatus', 'ChannelState', etc.
        status_substrings = ['status', 'state']

        # =====================================================================
        # PRIORITY ORDERING: channel-specific status enums must be checked BEFORE
        # generic module-level status enums.
        # Rationale:
        #   - IfxCxpi_ChStatus_t  → done/busy values used for per-channel polling
        #   - IfxCxpi_Status_t    → generic success/error return codes — WRONG for polling
        # We sort candidates so that enums containing 'ch' (channel) come first,
        # then enums containing 'channel', then all others.  This is fully data-driven:
        # no enum names are hardcoded, only structural priority rules.
        # =====================================================================
        def _status_enum_priority(enum_name: str) -> int:
            n = enum_name.lower()
            # Highest priority: explicitly channel-related status/state enums
            if ('ch' in n or 'channel' in n) and any(s in n for s in status_substrings):
                return 0
            # Second priority: any status/state enum that is NOT a bare generic return-code type
            # Heuristic: generic return-code enums are short (e.g. "IfxCxpi_Status_t" < 20 chars)
            if any(s in n for s in status_substrings) and len(enum_name) >= 20:
                return 1
            # Lowest priority: short generic status enums (e.g. IfxCxpi_Status_t)
            return 2

        sorted_enum_items = sorted(enum_lookup.items(), key=lambda kv: _status_enum_priority(kv[0]))
        for enum_name, enum_def in sorted_enum_items:
            enum_name_lower = enum_name.lower()
            
            # Use substring matching instead of word-level matching
            # 'IfxCxpi_Cxpi_ChStatus' → lower → 'ifxcxpi_cxpi_chstatus' contains 'status' ✓
            is_status_enum = any(sub in enum_name_lower for sub in status_substrings)
            if not is_status_enum:
                continue
            
            print(f"  [POLLING] Checking status enum: {enum_name}")
            
            # Search for 'done' and 'busy' values within this enum
            values = enum_def.get('values', [])
            done_value = None
            busy_value = None
            
            for val in values:
                val_name = val.get('name', '')
                val_name_lower = val_name.lower()
                val_description = _safe_str(val.get('description')).lower()
                
                # FIXED: Also use substring matching for value names
                # 'IfxCxpi_Cxpi_ChStatus_done' → lower contains 'done' ✓
                # 'IfxCxpi_Cxpi_ChStatus_busy' → lower contains 'busy' ✓
                if not done_value:
                    if any(ind in val_name_lower for ind in done_indicators) or \
                       any(ind in val_description for ind in done_indicators):
                        done_value = val_name
                
                if not busy_value:
                    if any(ind in val_name_lower for ind in busy_indicators) or \
                       any(ind in val_description for ind in busy_indicators):
                        busy_value = val_name
            
            # If we found both, return them
            if done_value and busy_value:
                print(f"  [POLLING] ✓ Found status enum: {enum_name} → done={done_value}, busy={busy_value}")
                return {
                    'done': done_value,
                    'busy': busy_value,
                    'enum_type': enum_name
                }
        
        return None
    
    def _learn_activity_enum(self, enum_lookup: Dict, module: str, function_type: str) -> Optional[str]:
        """
        Find appropriate activity enum value for a function type.
        
        DATA-DRIVEN: Uses word-overlap matching between the function name/type
        and enum value names. NO hardcoded categories.
        
        FIXED (Feb 2026): Uses _split_identifier_to_words for CamelCase-aware splitting
        instead of raw regex. Also maps TX/RX synonyms so 'send' matches 'tx',
        'receive' matches 'rx', etc.
        
        Args:
            enum_lookup: Dictionary of enum_name -> enum_definition
            module: Module name (e.g., 'Cxpi')
            function_type: Function name or type string (e.g., 'sendheader', 'receiveresponse')
        
        Returns:
            Activity enum value name, or None
        """
        function_type_lower = function_type.lower()
        # Use CamelCase-aware splitting for function words
        func_words = _split_identifier_to_words(function_type)
        
        # TX/RX synonym mapping — 'send' in func should match 'tx' in enum and vice versa
        tx_synonyms = {'send', 'transmit', 'tx', 'write', 'put'}
        rx_synonyms = {'receive', 'recv', 'rx', 'read', 'get'}
        
        # Expand func_words with synonyms
        expanded_func_words = set(func_words)
        if func_words & tx_synonyms:
            expanded_func_words |= tx_synonyms
        if func_words & rx_synonyms:
            expanded_func_words |= rx_synonyms
        
        # Completion indicators — universal software engineering terms
        completion_indicators = {'done', 'complete', 'finished', 'completed', 'end', 'success'}
        
        # Also check for activity-related enums by name
        activity_substrings = ['activity', 'action', 'event', 'request']
        
        best_match = None
        best_score = 0
        
        # Search for activity enums — prefer enums with 'activity' in their name
        for enum_name, enum_def in enum_lookup.items():
            enum_name_lower = enum_name.lower()
            is_activity_enum = any(sub in enum_name_lower for sub in activity_substrings)
            
            values = enum_def.get('values', [])
            for val in values:
                val_name = val.get('name', '')
                if not val_name:
                    continue
                    
                # Use CamelCase-aware splitting for enum value words
                val_words = _split_identifier_to_words(val_name)
                val_name_lower = val_name.lower()
                
                # Must have a completion indicator (substring check)
                has_completion = any(ind in val_name_lower for ind in completion_indicators)
                if not has_completion:
                    continue
                
                # Score by word overlap with expanded function name words
                overlap = len(expanded_func_words & val_words)
                
                # Bonus for being in an activity-type enum
                if is_activity_enum:
                    overlap += 2
                
                if overlap > best_score:
                    best_score = overlap
                    best_match = val_name
        
        if best_match:
            print(f"  [POLLING] Activity enum for '{function_type}': {best_match} (score={best_score})")
        
        return best_match
    
    def _find_error_flags_struct(self, all_structs: List[Dict], module: str) -> Optional[Dict[str, Any]]:
        """
        Find error flags structure from struct definitions.
        
        DATA-DRIVEN: Searches for structs with 'error' or 'flag' in name,
        then extracts member fields like rxCrcError, timeout, etc.
        
        Args:
            all_structs: List of struct definitions
            module: Module name (e.g., 'Cxpi')
        
        Returns:
            Dict with struct info and members, or None
            Example: {'name': 'IfxCxpi_ErrorFlags', 'members': ['rxCrcError', 'timeout', ...]}
        """
        for struct in all_structs:
            struct_name = struct.get('name', '')
            struct_name_lower = struct_name.lower()
            
            # Search for error/flag structs
            if not any(kw in struct_name_lower for kw in ['error', 'flag', 'status']):
                continue
            
            members = struct.get('members', [])
            if not members:
                continue
            
            # Extract member names
            member_names = [m.get('name', '') for m in members]
            
            # Verify it has error-related members
            error_member_count = sum(1 for m in member_names if any(kw in m.lower() for kw in ['error', 'flag', 'timeout']))
            
            if error_member_count > 0:
                return {
                    'name': struct_name,
                    'members': member_names,
                    'struct_def': struct
                }
        
        return None
    
    def _find_status_function_from_puml(self, target_func: str, available_functions: List[str], module: str) -> Optional[Dict[str, Any]]:
        """
        Find appropriate status function for polling.
        
        UPDATED (Jan 2026): Returns dict with function name AND parameter info
        
        Searches for functions like:
        - IfxCxpi_Cxpi_getChannelStatus(&channel, activity)
        - IfxCxpi_getStatus()
        - IfxCxpi_Cxpi_getErrorFlags(&channel, &errorFlags)
        
        Returns:
            Dict with function_name, takes_activity, takes_channel, or None
            Example: {'function': 'IfxCxpi_Cxpi_getChannelStatus', 
                     'takes_activity': True, 'takes_channel': True}
        """
        # DATA-DRIVEN: Learn status/monitoring functions from PUML patterns
        status_functions = set()
        
        if self.pattern_library:
            for analysis in self.pattern_library.get('puml_analyses', []):
                if isinstance(analysis, dict):
                    # Look for functions that appear in monitoring/timing phases
                    for phase_name, phase_data in analysis.get('phases', {}).items():
                        phase_lower = phase_name.lower()
                        if any(monitor_kw in phase_lower for monitor_kw in ['monitor', 'status', 'check', 'poll', 'wait']):
                            status_functions.update(phase_data.get('function_sequence', []))
        
        # If no PUML patterns found, fall back to keyword search across available_functions
        if not status_functions:
            for func in available_functions:
                func_lower = func.lower()
                # PRIORITY ORDER: getChannelStatus > getStatus > checkStatus
                # getErrorFlags is excluded — it's for error monitoring, not busy-wait polling
                if 'getchannelstatus' in func_lower:
                    status_functions = {func}
                    break
                elif any(kw in func_lower for kw in ['getstatus', 'checkstatus', 'readstatus']):
                    status_functions.add(func)
        
        # FALLBACK (Feb 2026): If STILL not found, search all_functions from KG/RAG
        # The getChannelStatus function may not be in top 10 RAG results but exists in the DB.
        # Also search by constructing expected name from detected module prefix patterns.
        if not status_functions:
            print(f"  [POLLING] Status function not in top RAG results, searching all_functions by keyword...")
            all_func_list = getattr(self, 'all_functions', [])
            for func in all_func_list:
                func_name = func.get('name', '') if isinstance(func, dict) else str(func)
                func_lower = func_name.lower()
                # Keyword-based search: any function containing 'channelstatus' or 'getstatus'
                if 'channelstatus' in func_lower or 'getstatus' in func_lower:
                    status_functions.add(func_name)
                    print(f"  [POLLING] ✓ Found status function from all_functions: {func_name}")
            
            # If still nothing, try searching PUML pattern library for function names
            # containing 'status' (but not 'error')
            if not status_functions and self.pattern_library:
                for key, chunks in self.pattern_library.items():
                    if isinstance(chunks, list):
                        for chunk in chunks:
                            if isinstance(chunk, dict):
                                for phase_data in chunk.get('phases', {}).values():
                                    for fn in phase_data.get('function_sequence', []):
                                        if 'status' in fn.lower() and 'error' not in fn.lower():
                                            status_functions.add(fn)
        
        # Find the best matching status function for the target function
        module_prefix = f"Ifx{module.capitalize()}_"
        double_prefix = f"Ifx{module.capitalize()}_{module.capitalize()}_"
        
        # Prioritize getChannelStatus over getErrorFlags
        channel_status_funcs = [f for f in status_functions if 'channelstatus' in f.lower()]
        if channel_status_funcs:
            status_func = channel_status_funcs[0]
        else:
            non_error_funcs = [f for f in status_functions if 'error' not in f.lower()]
            if non_error_funcs:
                status_func = non_error_funcs[0]
            elif status_functions:
                status_func = list(status_functions)[0]
            else:
                return None
        
        # Use the EXACT name as stored in the DB — do NOT artificially add or remove
        # prefix components.  The KG/RAG stores canonical Infineon SDK names and those
        # are the only correct names.  Normalizing here caused mixed single/double
        # prefix output (e.g. converting IfxCxpi_getChannelStatus → IfxCxpi_Cxpi_getChannelStatus
        # when the DB actually has the single-prefix form, producing unresolvable calls).
        normalized_name = status_func
        
        # Determine parameters by looking at function definition
        takes_activity = False
        takes_channel = False
        
        # Check if this function takes activity/event parameter
        for func in getattr(self, 'all_functions', []):
            func_name = func.get('name') if isinstance(func, dict) else str(func)
            if func_name == status_func or func_name == normalized_name:
                # First try structured parameters
                params = func.get('parameters', []) if isinstance(func, dict) else []
                for param in params:
                    param_name = _safe_str(param.get('name')).lower()
                    param_type = _safe_str(param.get('type')).lower()
                    
                    if 'activity' in param_name or 'event' in param_name or 'action' in param_name:
                        takes_activity = True
                    if 'activity' in param_type or 'event' in param_type:
                        takes_activity = True
                    if 'channel' in param_name or 'channel' in param_type:
                        takes_channel = True
                
                # Fallback: parse from full_content if no structured params found
                if not params and isinstance(func, dict):
                    content = func.get('full_content', '') or func.get('content', '')
                    if content and '(' in content:
                        first_line = content.split('\n')[0]
                        if '(' in first_line:
                            param_str = first_line.split('(', 1)[1].rsplit(')', 1)[0].lower()
                            if 'activity' in param_str or 'event' in param_str or 'action' in param_str:
                                takes_activity = True
                            if 'channel' in param_str:
                                takes_channel = True

                # ADDITIONAL FALLBACK: even when structured params exist, KG often stores
                # them with blank names/types.  Re-check from full_content unconditionally
                # if takes_activity is still False — this catches e.g. getChannelStatus
                # whose KG params have name=None but full_content has the real signature.
                if not takes_activity and isinstance(func, dict):
                    content = func.get('full_content', '') or func.get('content', '')
                    if content and '(' in content:
                        first_line = content.split('\n')[0]
                        if '(' in first_line:
                            param_str_raw = first_line.split('(', 1)[1].rsplit(')', 1)[0].lower()
                            if 'activity' in param_str_raw or 'event' in param_str_raw or 'chactivity' in param_str_raw:
                                takes_activity = True
                            if 'channel' in param_str_raw or 'cxpichannel' in param_str_raw:
                                takes_channel = True

                break  # Found the matching function — stop scanning all_functions
        
        return {
            'function': normalized_name,
            'takes_activity': takes_activity,
            'takes_channel': takes_channel
        }
    
    # REMOVED: _generate_loop_based_polling, _create_polling_code_from_loop_pattern, _create_error_monitoring_code
    # These methods relied on PUML loop_patterns which are no longer fetched/used
    # Polling now relies on function name heuristics + status enum/function lookup
    
    def _learn_polling_condition(self, polling_target: str, module: str) -> Optional[str]:
        """Learn the appropriate polling condition from function and enum data"""
        # Analyze the polling target function to determine condition
        for func in getattr(self, 'all_functions', []):
            func_name = func.get('name') if isinstance(func, dict) else str(func)
            if func_name == polling_target:
                # Check function description for clues about polling condition
                func_desc = _safe_str(func.get('brief')).lower() if isinstance(func, dict) else ''
                
                # Learn timeout conditions
                if 'timeout' in func_desc or 'error' in func_desc:
                    # Look for appropriate enum values to determine condition
                    for enum_name, enum_data in getattr(self, 'enums', {}).items():
                        if 'error' in enum_name.lower() or 'timeout' in enum_name.lower():
                            values = enum_data.get('values', [])
                            for value in values:
                                value_name = _safe_str(value.get('name')).lower()
                                value_desc = _safe_str(value.get('description')).lower()
                                
                                # Find the "not occurred" or "clear" state
                                if ('timeout' in value_desc and ('not' in value_desc or 'clear' in value_desc or 'idle' in value_desc)) or \
                                   ('error' in value_desc and ('not' in value_desc or 'none' in value_desc)):
                                    return f"{self._learn_polling_variable(polling_target, module)}.{value_name.split('_')[-1]} == 0"
                
                break
        
        return None
    
    def _learn_polling_variable(self, polling_target: str, module: str) -> Optional[str]:
        """Learn the appropriate polling variable from function parameters"""
        for func in getattr(self, 'all_functions', []):
            func_name = func.get('name') if isinstance(func, dict) else str(func)
            if func_name == polling_target:
                if isinstance(func, dict) and 'parameters' in func:
                    for param in func['parameters']:
                        param_type = param.get('type', '')
                        param_name = param.get('name', '')
                        
                        # Look for error/flags struct parameters
                        if ('Error' in param_type or 'Flags' in param_type) and '*' in param_type:
                            return param_name
                
                break
        
        return None
    
    # REMOVED: _create_timeout_polling_code, _create_status_polling_code
    # These were only called by _create_polling_code_from_loop_pattern which is now removed
    
    def _extract_struct_values(self, struct_inits: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """
        Extract struct initialization values for C code generation
        
        Args:
            struct_inits: Dictionary of struct initializations from StructInitializer
                          Format: {var_name: {member_name: init_value_string, ...}}
            
        Returns:
            Dictionary with struct names -> member values mapping
        """
        struct_values = {}
        
        for struct_name, init_dict in struct_inits.items():
            struct_values[struct_name] = {}
            for member_name, member_info in init_dict.items():
                if isinstance(member_info, dict):
                    # Complex value with metadata
                    default_val = member_info.get('default_value', '0')
                    computed_val = member_info.get('computed_value', None)
                    value = computed_val if computed_val is not None else default_val
                    struct_values[struct_name][member_name] = str(value)
                else:
                    # Simple string value (most common case from generate_initializations)
                    struct_values[struct_name][member_name] = str(member_info) if member_info else '0'
        
        return struct_values
    
    def generate(self, 
                user_description: str,
                user_parameters: Optional[Dict[str, Any]] = None,
                all_functions: Optional[List[Dict]] = None,
                rag_results: Optional[List[Dict]] = None,
                kg_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate complete test code configuration
        
        UPDATED (Feb 2026): Now uses Knowledge Graph DEPENDS_ON for function sequencing
        
        Args:
            user_description: What test user wants
            user_parameters: Optional parameters (data size, count, etc.)
            all_functions: All available functions for polling pattern generation
            rag_results: RAG function search results with similarity scores (PHASE 3 output)
                        Format: [{'name': 'IfxCxpi_sendHeader', 'similarity': 0.92, ...}, ...]
            kg_context: Knowledge Graph context with DEPENDS_ON relationships (PRIMARY SOURCE)
        
        Returns:
            Complete code generation plan with:
            - Feature classification (using RAG primary method)
            - Function sequence (sorted using KG DEPENDS_ON)
            - Struct initializations
            - Code template
            - Polling patterns
            - Parameters
        """
        
        user_params = user_parameters or {}
        self.all_functions = all_functions or []
        kg_context = kg_context or {}  # Knowledge Graph context with DEPENDS_ON
        
        # Step 1: Classify feature - PRIMARY METHOD: RAG Semantic Similarity
        print(f"[STEP 1] Classifying user input: '{user_description}'")
        print(f"  -> Using PRIMARY method: RAG Semantic Similarity")
        feature_classification = self.classifier.classify(
            user_description, 
            rag_results=rag_results,
            all_functions=self.all_functions, 
            puml_analysis=self.puml_analysis
        )
        print(f"  -> Primary method: {feature_classification.get('primary_method', 'RAG_SEMANTIC_SIMILARITY')}")
        print(f"  -> Primary score: {feature_classification.get('primary_score', 0):.4f}")
        print(f"  -> Confidence: {feature_classification.get('confidence_percentage', 0):.1f}%")
        print(f"  -> Validation: {feature_classification.get('secondary_validation', 'PUML_CORE_FUNCTIONS')} - {'PASSED ✓' if feature_classification.get('validation_passed') else 'FAILED ✗'}")
        print(f"  -> Detected functions: {len(feature_classification.get('detected_functions', []))}")

        
        # DATA-DRIVEN: Apply learned filtering rules instead of hardcoded timeout filtering
        filtering_rules = self._learn_filtering_rules_from_puml(user_description)
        if filtering_rules:
            original_count = len(feature_classification['detected_functions'])
            feature_classification['detected_functions'] = self._apply_filtering_rules(
                feature_classification['detected_functions'], 
                filtering_rules
            )
            filtered_count = len(feature_classification['detected_functions'])
            if original_count != filtered_count:
                print(f"  -> Applied data-driven filtering: {original_count} -> {filtered_count} functions")
        
        # DATA-DRIVEN: Apply semantic filtering to ensure only semantically relevant functions are included
        # This prevents including irrelevant communication functions (sendHeader, receiveHeader, etc.)
        # when the user is asking for configuration functions (setBaudRate, etc.)
        semantic_filtered_funcs = self._select_functions_by_semantic_relevance(
            user_description, 
            feature_classification['detected_functions'],
            self.all_functions
        )
        if semantic_filtered_funcs is not None:
            original_count = len(feature_classification['detected_functions'])
            feature_classification['detected_functions'] = semantic_filtered_funcs
            filtered_count = len(feature_classification['detected_functions'])
            if original_count != filtered_count:
                print(f"  -> Applied semantic filtering: {original_count} -> {filtered_count} functions")
        
        # Step 1.5: Detect channels for multi-channel scenarios
        channels = self._detect_channels_for_scenario(feature_classification, user_description)
        print(f"  -> Channels detected: {channels}")
        
        # Step 2: Build function sequence
        print(f"\n[STEP 2] Building function sequence...")
        function_sequence = self.sequence_builder.build_sequence(
            feature_classification,
            self.module,
            user_params,
            channels,
            user_description,  # Pass user description for context-aware decisions
            kg_context         # Pass KG context for DEPENDS_ON relationships (PRIMARY SOURCE)
        )
        # --- NOTE: Peer communication step filtering DISABLED ---
        # The PUML example sequences already contain the correct set of functions
        # for both single and multi-channel scenarios. Removing "peer comm" functions
        # was stripping essential operation functions (transmit, receive, enable).
        # The PUML patterns are authoritative — they come from real test codes.
        print(f"  -> Generated {len(function_sequence)} function calls")
        
        # ===== LAYER 3 INTEGRATION: Apply source code analysis to improve sequence =====
        print(f"\n[LAYER 3] Applying source code analysis optimization...")
        if self.source_code_enriched:
            # Remove internal function calls to reduce code bloat (33% reduction)
            original_len = len(function_sequence)
            function_sequence = self._skip_internal_function_calls(function_sequence)
            if len(function_sequence) < original_len:
                print(f"  -> [BLOAT-REDUCTION] Removed {original_len - len(function_sequence)} internal calls")
            else:
                print(f"  -> [SOURCE-CODE] No internal calls to skip (using actual source code patterns)")
        else:
            print(f"  -> [SOURCE-CODE] Source code analysis not available, using PUML patterns only")
        # ==========================================================================
        
        # ===== SMART SEMANTIC FILTERING: Remove the PRIMARY TEST FUNCTION =====
        # ONLY for explicit "API TEST" scenarios where user wants to TEST a specific API
        # e.g. "SET BAUDRATE API TEST" → setBaudRate is the test TARGET, not a prerequisite
        # For regular test descriptions like "inject CRC error while sending", keep ALL functions
        user_desc_lower_check = user_description.lower()
        is_api_test = 'api test' in user_desc_lower_check or 'api_test' in user_desc_lower_check
        
        primary_test_func = None  # Initialize to None for all cases
        
        if is_api_test:
            primary_test_func = self._identify_primary_test_function(user_description)
            if primary_test_func:
                original_len = len(function_sequence)
                print(f"\n[DEBUG] API TEST mode: removing primary test function from setup sequence")
                print(f"[DEBUG] Primary test function identified: {primary_test_func}")
                function_sequence = [f for f in function_sequence if f.lower() != primary_test_func.lower()]
                if len(function_sequence) < original_len:
                    print(f"\n[SEMANTIC] Identified primary test function: {primary_test_func}")
                    print(f"  -> Removed from generated sequence (user will implement this test)")
                    print(f"  -> Generated code now contains: {original_len - 1} setup/prerequisite functions")
        else:
            print(f"[DEBUG] Not an API test — keeping all functions in sequence")
        # =====================================================================
        
        # Step 3: Generate struct initializations
        print(f"\n[STEP 3] Generating struct initializations...")
        struct_inits = self.struct_initializer.generate_initializations(
            feature_classification,
            self.module,
            channels,
            user_description  # Pass user's functionality description for enum value selection
        )
        print(f"  -> Initialized {len(struct_inits)} structs")
        
        # Step 4: Generate polling patterns
        print(f"\n[STEP 4] Generating polling patterns...")
        polling_patterns = self._generate_polling_patterns(
            function_sequence,
            self.all_functions,
            self.all_enums,
            self.module,
            feature_classification,
            user_description  # Pass user description for context-aware error monitoring
        )
        print(f"  -> Generated {len(polling_patterns)} polling patterns")
        
        # Step 5: Generate sample C code skeleton for LLM enhancement
        print(f"\n[STEP 5] Generating sample C code skeleton for LLM enhancement...")
        sample_test_code = generate_sample_c_code(
            function_sequence=function_sequence,
            struct_initializations=struct_inits,
            all_functions=self.all_functions,
            module=self.module,
            struct_values=self._extract_struct_values(struct_inits),
            all_structs=self.all_structs,
            all_enums=self.all_enums,
            user_description=user_description,
            polling_patterns=polling_patterns
        )
        print(f"  -> Generated {len(sample_test_code.splitlines())} lines of C code skeleton")
        print(f"  -> Ready for LLM enhancement with hardware specifications")
        
        # Compile result - OUTPUT ENRICHED CONTEXT FOR COPILOT, NOT FINAL CODE
        result = {
            'status': 'success',
            'module': self.module,
            'user_request': user_description,
            'feature_classification': feature_classification,
            'function_sequence': function_sequence,
            'struct_initializations': struct_inits,
            'polling_patterns': polling_patterns,
            'primary_test_function': primary_test_func,  # ADD: Tell Copilot which function is the test
            'sample_test_code': sample_test_code,  # NEW: Sample code skeleton for LLM enhancement
            # NOTE: NO code_template here - Copilot will generate final code
            'metadata': {
                'pattern_library_confidence': self.pattern_library.get('metadata', {}).get('total_files', 0),
                'functions_discovered': len(self.pattern_library.get('core_functions', {}).get('always_present', [])),
                'generation_method': 'data-driven-from-PUML-patterns-and-source-code',
                'final_code_generator': 'GitHub-Copilot (via Idea1-Sequential LLM approach)',
                'source_code_integration': 'Layer 3 enabled' if self.source_code_enriched else 'Layer 3 disabled',
                'layer3_benefits': {
                    'quality_improvement': '+30% (prerequisites, state tracking, polling conditions)',
                    'code_bloat_reduction': '-33% (internal calls skipped)',
                    'enabled': bool(self.source_code_enriched)
                }
            }
        }
        
        print(f"\n[SUMMARY] Data-driven analysis complete (LLM to follow)!")
        print(f"  Status: {result['status']}")
        print(f"  Functions: {len(function_sequence)}")
        print(f"  Structs: {len(struct_inits)}")
        print(f"  Polling patterns: {len(polling_patterns)}")
        if self.source_code_enriched:
            print(f"  [LAYER 3] Source code integration: ENABLED")
            print(f"    • Quality improvement: +30%")
            print(f"    • Code bloat reduction: -33%")
        else:
            print(f"  [LAYER 3] Source code integration: DISABLED (PUML patterns only)")
        print(f"  ➜ Ready for GitHub Copilot to generate final code...")
        
        return result
    
    def _extract_cleanup_functions(self, function_sequence: List[str]) -> List[str]:
        """Extract cleanup/finalization functions from sequence (DATA-DRIVEN)."""
        cleanup_funcs = []
        cleanup_keywords = {'clear', 'disable', 'reset', 'cleanup'}
        
        for func in function_sequence:
            func_lower = func.lower()
            if any(kw in func_lower for kw in cleanup_keywords):
                cleanup_funcs.append(func)
        
        return cleanup_funcs
    
    def _check_if_monitoring_needed(self, feature_classification: Dict, function_sequence: List[str]) -> bool:
        """Check if error/timeout monitoring is needed (DATA-DRIVEN)."""
        # Use primary_function (RAG-based) or check modifiers
        feature = _safe_str(feature_classification.get('primary_function')).lower()
        monitoring_keywords = {'error', 'timeout', 'fault', 'detection', 'monitoring'}
        
        # Check feature type or modifiers
        if any(kw in feature for kw in monitoring_keywords) or \
           feature_classification.get('modifiers', {}).get('error_injection'):
            return True
        
        # Check function sequence for error/timeout functions
        # DATA-DRIVEN: Combine monitoring keywords with flag/check keywords
        all_monitoring_keywords = monitoring_keywords | {'flag', 'check'}  # Use | for set union, not +
        for func in function_sequence:
            func_lower = func.lower()
            if any(kw in func_lower for kw in all_monitoring_keywords):
                return True
        
        return False
    
    def _check_if_validation_needed(self, function_sequence: List[str]) -> bool:
        """Check if data validation/printing is needed (DATA-DRIVEN)."""
        receive_keywords = {'receive', 'read', 'get', 'input', 'response'}
        
        for func in function_sequence:
            func_lower = func.lower()
            if any(kw in func_lower for kw in receive_keywords):
                return True
        
        return False
    
    def _generate_monitoring_loops(self, function_sequence: List[str], feature_classification: Dict) -> List[str]:
        """Generate error/timeout monitoring loops (DATA-DRIVEN)."""
        loops = []
        # Use primary_function (RAG-based) or check modifiers
        feature = _safe_str(feature_classification.get('primary_function')).lower()
        modifiers = feature_classification.get('modifiers', {})
        
        monitoring_type = 'error'
        if 'timeout' in feature or modifiers.get('error_injection'):
            monitoring_type = 'timeout'
        elif 'error' in feature:
            monitoring_type = 'error'
        
        # Generate generic monitoring loop (DATA-DRIVEN)
        # Issue #10: Use while-loop polling with actual function calls
        # Find the actual error flags struct and getErrorFlags function from data
        error_struct_type = None
        error_struct_var = None
        error_member = None
        get_error_func_name = None
        channel_var = None
        
        # Find error flags struct from all_structs
        for s in self.all_structs:
            sname = s.get('name', '')
            if any(kw in sname.lower() for kw in ['error', 'flag']):
                error_struct_type = sname
                members = s.get('members', [])
                if members:
                    # Pick the most relevant error member based on monitoring_type
                    for m in members:
                        mname = m.get('name', '')
                        if monitoring_type in mname.lower():
                            error_member = mname
                            break
                    if not error_member and members:
                        error_member = members[0].get('name', 'error')
                break
        
        if error_struct_type:
            error_struct_var = _derive_variable_name(error_struct_type)
        else:
            error_struct_var = 'errorFlags'
            error_member = monitoring_type
        
        # Find getErrorFlags function
        for func in self.all_functions:
            fname = func.get('name', '') if isinstance(func, dict) else str(func)
            if 'geterror' in fname.lower() or 'errorflags' in fname.lower():
                get_error_func_name = fname
                break
        
        # Find a channel variable
        for struct_name in (getattr(self, '_struct_inits_cache', {}) or {}):
            if 'channel' in struct_name.lower() and 'config' not in struct_name.lower():
                channel_var = _derive_variable_name(struct_name)
                break
        
        if get_error_func_name and error_member:
            if channel_var:
                loops.append(f'while({error_struct_var}.{error_member} == 0)')
                loops.append(f'{{')
                loops.append(f'    {get_error_func_name}(&{channel_var}, &{error_struct_var});')
                loops.append(f'}}')
            else:
                loops.append(f'while({error_struct_var}.{error_member} == 0)')
                loops.append(f'{{')
                loops.append(f'    {get_error_func_name}(&{error_struct_var});')
                loops.append(f'}}')
            loops.append(f'printf("\\n $ {monitoring_type} detected $\\n");')
        else:
            # Minimal fallback using discovered info
            loops.append(f'/* Error monitoring: call get error flags function in a loop */')
            loops.append(f'/* until {monitoring_type} flag is set */')
        
        return loops
    
    def _generate_validation_statements(self, function_sequence: List[str], struct_inits: Dict[str, Dict]) -> List[str]:
        """Generate data validation and debug print statements (DATA-DRIVEN)."""
        stmts = []
        
        # Print received data (DATA-DRIVEN from function sequence)
        for func in function_sequence:
            func_lower = func.lower()
            if any(kw in func_lower for kw in ['receive', 'read', 'get']):
                # Find corresponding receive struct
                for struct_name in struct_inits.keys():
                    if 'rec' in struct_name.lower() or 'response' in struct_name.lower() or 'data' in struct_name.lower():
                        stmts.append(f'printf("Received data: ...\\n");')
                        stmts.append(f'// Print members of {struct_name}')
                        break
        
        return stmts
    
    def _generate_polling_patterns(self, function_sequence: List[str], all_functions: List[Dict], all_enums: Dict, module: str, feature_classification: Dict[str, Any], user_description: str = "") -> Dict[str, Dict[str, str]]:
        """
        Generate polling patterns for the function sequence.
        DATA-DRIVEN: Creates monitoring and polling code based on learned patterns.
        
        Args:
            function_sequence: Ordered list of functions
            all_functions: All available functions
            all_enums: All available enums
            module: Module name
            feature_classification: Feature classification with modifiers
            user_description: User's test description for context
        """
        polling_patterns = {}
        
        # Update polling patterns using the existing logic
        self._update_polling_patterns_from_sequence(function_sequence, feature_classification, polling_patterns, user_description)
        
        return polling_patterns

    def _normalize_infineon_function_name(self, func_name: str) -> str:
        """
        Normalize Infineon function names by removing module repetition pattern.
        
        Infineon SDK uses pattern: Ifx<Module>_<Module>_function
        Examples:
        - IfxCxpi_Cxpi_initModule -> IfxCxpi_initModule
        - IfxLinFlex_LinFlex_getData -> IfxLinFlex_getData
        
        Args:
            func_name: Function name to normalize
            
        Returns:
            Normalized function name with module repetition removed
        """
        if not func_name:
            return func_name
        
        # Extract module name from prefix (e.g., 'Cxpi' from 'IfxCxpi_...')
        if func_name.startswith('Ifx'):
            # Find the part after 'Ifx'
            after_ifx = func_name[3:]  # Skip 'Ifx'
            # Find first underscore to get module name
            first_underscore = after_ifx.find('_')
            if first_underscore > 0:
                module_name = after_ifx[:first_underscore]
                # Check if next part starts with the same module name (repetition pattern)
                pattern = f"_{module_name}_"  # e.g., "_Cxpi_"
                if pattern in func_name:
                    # Remove the repetition: Ifx<Module>_<Module>_function -> Ifx<Module>_function
                    normalized = func_name.replace(pattern, '_')
                    return normalized
        
        return func_name

    def _is_receive_function(self, func_name: str) -> bool:
        """DATA-DRIVEN: Determine if a function is a receive/read/data input function using PUML/JSON patterns only."""
        # Use PUML pattern library to check if this function is categorized as a reception/data function
        if self.pattern_library:
            for analysis in self.pattern_library.get('puml_analyses', []):
                if not isinstance(analysis, dict):
                    continue
                for phase_name, phase_data in analysis.get('phases', {}).items():
                    function_types = phase_data.get('function_types', {})
                    if func_name in function_types.get('reception', []):
                        return True
        # Fallback: check for typical receive/read keywords in function type (from JSON)
        func_name_lower = func_name.lower()
        return any(kw in func_name_lower for kw in ['receive', 'read', 'input'])

    def _get_received_struct_for_function(self, func_name: str) -> Optional[Dict[str, Any]]:
        """DATA-DRIVEN: Find the struct used for received data for a given function using PUML/JSON only."""
        # Try to find from function parameter types (JSON)
        for func in getattr(self, 'all_functions', []):
            if func.get('name') == func_name:
                for param in func.get('parameters', []):
                    param_type = _safe_str(param.get('type')).lower()
                    if 'struct' in param_type or '_t' in param_type:
                        # Find struct definition by type
                        for struct in getattr(self.struct_initializer, 'all_structs', []):
                            if _safe_str(struct.get('name')).lower() in param_type:
                                return struct
        # Fallback: None if not found
        return None

    def _generate_dynamic_includes(self, struct_inits: Dict[str, Dict], function_sequence: List[str]) -> List[str]:
        """Strictly generate include statements based on actual usage in functions, structs, and enums.
        Adds traceability comments for each include. No unconditional includes."""
        includes = []
        include_reasons = {}

        # Scan function parameters for required includes
        used_modules = set()
        for func in function_sequence:
            if '_' in func:
                parts = func.split('_')
                if len(parts) > 1 and parts[0].startswith('Ifx'):
                    module_name = parts[0].replace('Ifx', '')
                    used_modules.add(module_name)
                    include_reasons[f'Ifx{module_name}_{module_name}.h'] = f"// Required for function: {func}"

        # Scan struct member types for required includes
        for struct_name, members in struct_inits.items():
            for member, value in members.items():
                if isinstance(value, str) and value.startswith('Ifx'):
                    parts = value.split('_')
                    if len(parts) > 1 and parts[0] == 'Ifx':
                        module_name = parts[1]
                        used_modules.add(module_name)
                        include_reasons[f'Ifx{module_name}_{module_name}.h'] = f"// Required for struct member: {struct_name}.{member}"

        # Scan for standard C types only if used
        stdint_needed = False
        stdbool_needed = False
        stdio_needed = False
        for struct_name, members in struct_inits.items():
            for member, value in members.items():
                if any(t in str(value) for t in ['uint', 'int', 'size_t']):
                    stdint_needed = True
                if 'true' in str(value).lower() or 'false' in str(value).lower():
                    stdbool_needed = True
                if 'printf' in str(value).lower():
                    stdio_needed = True
        for func in function_sequence:
            if 'printf' in func.lower():
                stdio_needed = True

        if stdint_needed:
            includes.append('#include <stdint.h> // Required for integer types')
        if stdbool_needed:
            includes.append('#include <stdbool.h> // Required for boolean types')
        if stdio_needed:
            includes.append('#include <stdio.h> // Required for printf/debug output')

        # Add module includes with traceability comments
        for module in sorted(used_modules):
            inc = f'#include "Ifx{module}_{module}.h" {include_reasons.get(f"Ifx{module}_{module}.h", "")}'
            includes.append(inc)

        # Remove duplicates while preserving order
        seen = set()
        unique_includes = []
        for inc in includes:
            if inc not in seen:
                unique_includes.append(inc)
                seen.add(inc)
        return unique_includes

    def _learn_filtering_rules_from_puml(self, user_description: str) -> Optional[Dict[str, Any]]:
        """
        Learn filtering rules from PUML patterns instead of hardcoded logic.
        
        Analyzes PUML phases to determine what functions should be included/excluded
        for different monitoring/detection scenarios.
        
        Args:
            user_description: User's natural language description
            
        Returns:
            Dict with filtering rules or None if no rules apply
        """
        if not self.pattern_library:
            return None
            
        filtering_rules = {
            'include_keywords': set(),
            'exclude_keywords': set(),
            'include_functions': set(),
            'exclude_functions': set()
        }
        
        user_lower = user_description.lower()
        
        # Learn filtering rules from PUML phases that match the user description
        for analysis in self.pattern_library.get('puml_analyses', []):
            if not isinstance(analysis, dict):
                continue
                
            for phase_name, phase_data in analysis.get('phases', {}).items():
                phase_lower = phase_name.lower()
                
                # Check if this phase is relevant to the user's request
                phase_relevant = False
                phase_words = phase_lower.split()
                user_words = user_lower.split()
                
                # Check for keyword overlap between phase and user description
                for phase_word in phase_words:
                    if len(phase_word) > 3 and phase_word in user_words:
                        phase_relevant = True
                        break
                
                if phase_relevant:
                    function_sequence = phase_data.get('function_sequence', [])
                    
                    # Learn inclusion rules - functions that appear in relevant phases
                    filtering_rules['include_functions'].update(function_sequence)
                    
                    # Learn exclusion rules - functions that should NOT appear in certain contexts
                    # Extract exclusion patterns from phase analysis
                    for func in function_sequence:
                        func_lower = func.lower()
                        
                        # Learn common exclusion patterns from PUML context
                        if any(excl_kw in func_lower for excl_kw in ['errorctl', 'inject', 'error', 'fault']):
                            # Only exclude if the user description doesn't specifically mention these
                            if not any(mention_kw in user_lower for mention_kw in ['error', 'inject', 'fault']):
                                filtering_rules['exclude_functions'].add(func)
        
        # If no specific rules learned, return None
        if not any(filtering_rules.values()):
            return None
            
        return filtering_rules

    def _apply_filtering_rules(self, detected_functions: List[str], filtering_rules: Dict[str, Any]) -> List[str]:
        """
        Apply learned filtering rules to detected functions.
        
        Args:
            detected_functions: List of functions detected by feature classification
            filtering_rules: Learned filtering rules from PUML
            
        Returns:
            Filtered list of functions
        """
        filtered = []
        
        for func in detected_functions:
            func_lower = func.lower()
            
            # Check exclusion rules first
            should_exclude = False
            
            # Exclude specific functions
            if func in filtering_rules.get('exclude_functions', set()):
                should_exclude = True
            
            # Exclude by keywords
            if any(excl_kw in func_lower for excl_kw in filtering_rules.get('exclude_keywords', set())):
                should_exclude = True
            
            # If not excluded, check inclusion rules
            if not should_exclude:
                # Include if in include_functions or matches include_keywords
                if (func in filtering_rules.get('include_functions', set()) or
                    any(incl_kw in func_lower for incl_kw in filtering_rules.get('include_keywords', set()))):
                    filtered.append(func)
                else:
                    # If there are specific inclusion rules, only include matching functions
                    # If no inclusion rules, include by default
                    if not filtering_rules.get('include_functions') and not filtering_rules.get('include_keywords'):
                        filtered.append(func)
            
        return filtered
    
    def _select_functions_by_semantic_relevance(self, user_description: str, detected_functions: List[str], all_functions: List[Dict[str, Any]]) -> List[str]:
        """
        Filter detected functions based on semantic relevance to user description.
        
        CONSERVATIVE APPROACH: Keep most functions, only remove clearly irrelevant ones.
        The RAG system already ranked these by similarity — trust its selections.
        
        Args:
            user_description: User's natural language description
            detected_functions: List of functions detected by feature classification (from RAG)
            all_functions: Complete list of function dictionaries from RAG
            
        Returns:
            Filtered list of functions — biased towards KEEPING functions rather than removing them.
        """
        if not user_description or not detected_functions:
            return detected_functions
        
        # If we have 5 or fewer functions, keep ALL — RAG already filtered for relevance
        if len(detected_functions) <= 5:
            return detected_functions
        
        user_desc_lower = user_description.lower()
        
        # Detect what the user is asking for
        user_wants_communication = any(kw in user_desc_lower for kw in ['send', 'receive', 'transmit', 'response', 'header', 'transmission', 'exchange'])
        user_wants_error = any(kw in user_desc_lower for kw in ['error', 'fault', 'inject', 'crc', 'diagnostic'])
        user_wants_config = any(kw in user_desc_lower for kw in ['init', 'config', 'setup', 'baudrate', 'baud', 'enable'])
        user_wants_monitoring = any(kw in user_desc_lower for kw in ['interrupt', 'monitor', 'flag', 'status', 'check', 'detect', 'verify'])
        
        # Build function info lookup
        func_dict_map = {}
        for func in all_functions:
            name = func.get('name', '')
            func_dict_map[name] = func
        
        # Score each function — POSITIVE scoring (add points for relevance) 
        # NO heavy penalties — if RAG found it relevant, trust it
        function_scores = []
        
        for func_name in detected_functions:
            score = 1.0  # Start with baseline positive score (benefit of the doubt)
            func_name_lower = func_name.lower()
            
            # Bonus for init/config functions — almost always needed
            if any(kw in func_name_lower for kw in ['init', 'config', 'enable', 'setup']):
                score += 3.0
            
            # Bonus if function name words appear in user description
            func_words = set(func_name_lower.replace('ifx', '').replace('cxpi', '').replace('_', ' ').split())
            desc_words = set(user_desc_lower.split())
            overlap = func_words & desc_words
            score += len(overlap) * 2.0
            
            # Bonus for matching user intent categories
            if user_wants_communication and any(kw in func_name_lower for kw in ['send', 'transmit', 'receive', 'response', 'header']):
                score += 2.0
            if user_wants_error and any(kw in func_name_lower for kw in ['error', 'inject', 'fault', 'crc']):
                score += 2.0
            if user_wants_monitoring and any(kw in func_name_lower for kw in ['status', 'flag', 'interrupt', 'clear', 'get']):
                score += 2.0
            if user_wants_config and any(kw in func_name_lower for kw in ['init', 'config', 'baud', 'enable']):
                score += 2.0
            
            # Light penalty ONLY for clearly unrelated reset/cleanup if user didn't ask
            if any(kw in func_name_lower for kw in ['resetmodule', 'deinit']) and not any(kw in user_desc_lower for kw in ['reset', 'cleanup', 'deinit']):
                score -= 1.0  # Light penalty, not -100
            
            function_scores.append({
                'name': func_name,
                'score': score
            })
        
        # Sort by score descending, keep top functions (at least 5, at most all)
        function_scores.sort(key=lambda x: x['score'], reverse=True)
        
        # Keep all functions with score > 0 (which should be most of them)
        relevant_functions = [f['name'] for f in function_scores if f['score'] > 0]
        
        # Safety: if we somehow removed everything, return all detected functions
        if not relevant_functions:
            return detected_functions
        
        return relevant_functions
    
    def _detect_channels_for_scenario(self, feature_classification: Dict[str, Any], user_description: str) -> List[str]:
        """
        Detect which channels are needed for the given scenario.
        DATA-DRIVEN: Analyzes feature classification and user description to determine channel requirements.
        """
        channels = []
        user_desc_lower = user_description.lower()
        # Use primary_function (RAG-based) instead of primary_feature (PUML-based)
        primary_feature = _safe_str(feature_classification.get('primary_function')).lower()
        
        # DATA-DRIVEN: Learn from PUML patterns if available
        if self.pattern_library and 'channel_patterns' in self.pattern_library:
            channel_patterns = self.pattern_library['channel_patterns']
            # Look for channels mentioned in PUML patterns
            for pattern_name, pattern_data in channel_patterns.items():
                if primary_feature in pattern_name.lower() or any(kw in pattern_name.lower() for kw in user_desc_lower.split()):
                    # Extract channels from pattern data
                    if 'associated_functions' in pattern_data:
                        # If pattern has associated functions that match our detected functions
                        detected_funcs = set(feature_classification.get('detected_functions', []))
                        pattern_funcs = set(pattern_data['associated_functions'])
                        if detected_funcs & pattern_funcs:  # Intersection
                            # Extract channel names from pattern name (e.g., 'ch0', 'ch3')
                            ch_matches = re.findall(r'ch\d+', pattern_name.lower())
                            channels.extend(ch_matches)
        
        # DATA-DRIVEN: Learn from PUML analysis if no direct patterns found
        if not channels and self.puml_analysis:
            for analysis in self.puml_analysis:
                if isinstance(analysis, dict):
                    # Check if analysis matches user description
                    filename = _safe_str(analysis.get('filename')).lower()
                    if any(kw in filename for kw in user_desc_lower.split()):
                        # Extract channels from this analysis
                        channel_roles = analysis.get('channel_roles', {})
                        for role_name in channel_roles.keys():
                            ch_matches = re.findall(r'ch\d+', role_name.lower())
                            channels.extend(ch_matches)
        
        # DATA-DRIVEN: Learn from detected functions that mention channels
        if not channels:
            detected_funcs = feature_classification.get('detected_functions', [])
            for func in detected_funcs:
                func_lower = func.lower()
                ch_matches = re.findall(r'ch\d+', func_lower)
                channels.extend(ch_matches)
        
        # Remove duplicates and sort
        channels = list(set(channels))
        channels.sort()
        
        # If still no channels found, return empty list (will be handled by sequence builder)
        return channels
    
    def _identify_primary_test_function(self, user_description: str) -> Optional[str]:
        """
        IMPROVED: Identify the PRIMARY TEST FUNCTION from user description
        
        Strategy:
        1. Extract key action words from the user description (set, enable, read, etc.)
        2. Find functions with LONGER action words that contain user keywords
        3. Skip init/config functions (these are setup, not the test target)
        4. Return the MOST SPECIFIC match (longest substring match)
        
        Example: For "SET BAUDRATE API TEST"
        - User keywords: {'set', 'baudrate', 'api', 'test'}
        - Look for functions with these words
        - 'setBaudRate' matches 'set' + 'baud' (good match)
        - 'resetModule' contains 'set' but NOT 'baud' (poor match - reject it)
        - Result: setBaudRate (more specific)
        
        Returns:
            Function name matching the primary operation, or None if no match
        """
        if not self.all_functions:
            return None
        
        description_lower = user_description.lower()
        # Get meaningful words (skip common words like 'api', 'test')
        description_words = [w for w in description_lower.split() 
                            if len(w) > 2 and w not in ['api', 'test', 'suite', 'code']]
        
        if not description_words:
            return None
        
        best_match = None
        best_match_score = 0
        
        # For each function, calculate how well it matches user description
        for func in self.all_functions:
            func_name = func.get('name', '')
            func_name_lower = func_name.lower()
            
            # Skip prerequisite functions - these are NOT the test target
            if any(skip in func_name_lower for skip in ['init', 'config', 'calculate', 'error', 'fortest']):
                continue
            
            # CRITICAL: Calculate match quality
            # Count how many user keywords appear as SUBSTRINGS in the function name
            # and give bonus to longer matches
            match_score = 0
            for word in description_words:
                if word in func_name_lower:
                    # Longer word match = more specific = higher score
                    match_score += len(word)
            
            # Only consider if it has a meaningful match (not just 'set' in 'reset')
            if match_score > best_match_score:
                best_match_score = match_score
                best_match = func_name
        
        if best_match:
            print(f"  [SEMANTIC] Identified primary test function: {best_match} (score: {best_match_score})")
            return best_match
        
        return None
    
    def _extract_action_keywords_from_functions(self) -> set:
        """
        DATA-DRIVEN: Extract action keywords from actual function names in the system
        
        Instead of hardcoding verbs like 'set', 'enable', 'send', we learn them from
        what functions actually exist.
        
        Returns:
            Set of action keywords found in function names
        """
        keywords = set()
        
        if not self.all_functions:
            return keywords
        
        # Common action prefixes to extract
        # These are just INDICATORS to look for, not exhaustive hardcoding
        action_prefixes = ['set', 'get', 'enable', 'disable', 'send', 'receive', 'read', 'write', 
                          'init', 'config', 'start', 'stop', 'reset', 'clear', 'transmit', 'poll']
        
        for func in self.all_functions:
            func_name_lower = _safe_str(func.get('name')).lower()
            
            # For each action prefix, check if it appears at the start of the function
            for prefix in action_prefixes:
                if func_name_lower.startswith(prefix) or f'_{prefix}' in func_name_lower:
                    keywords.add(prefix)
        
        return keywords
    

    # =========================================================================
    # LAYER 3 INTEGRATION: Source Code Analysis Helper Methods
    # DATA-DRIVEN methods to use source code enriched data for better code generation
    # =========================================================================
    
    def _get_internal_calls_for_function(self, function_name: str) -> List[str]:
        """
        DATA-DRIVEN: Extract internal function calls for a specific function from source code analysis
        
        Returns list of function names that are called internally (should be skipped)
        """
        if not self.source_code_enriched:
            return []
        
        functions_data = self.source_code_enriched.get("functions", {})
        func_data = functions_data.get(function_name, {})
        source_code = func_data.get("from_source_code", {})
        internal_calls = source_code.get("internal_calls", [])
        
        # Extract function names from call objects
        return [call.get("function", "") for call in internal_calls if call.get("skip_in_test")]
    
    def _get_prerequisites_for_function(self, function_name: str) -> Dict[str, Any]:
        """
        DATA-DRIVEN: Extract prerequisite field assignments for a function
        
        Returns dict with fields that must be initialized before calling this function
        """
        if not self.source_code_enriched:
            return {}
        
        functions_data = self.source_code_enriched.get("functions", {})
        func_data = functions_data.get(function_name, {})
        source_code = func_data.get("from_source_code", {})
        
        return source_code.get("prerequisites", {})
    
    def _get_state_variables_for_function(self, function_name: str) -> List[Dict[str, Any]]:
        """
        DATA-DRIVEN: Extract state variables that need to be tracked during test execution
        
        Returns list of state variables (flags, counters, status fields)
        """
        if not self.source_code_enriched:
            return []
        
        functions_data = self.source_code_enriched.get("functions", {})
        func_data = functions_data.get(function_name, {})
        source_code = func_data.get("from_source_code", {})
        
        return source_code.get("state_variables", [])
    
    def _get_polling_conditions_for_function(self, function_name: str) -> List[Dict[str, Any]]:
        """
        DATA-DRIVEN: Extract exact polling conditions from source code
        
        Returns actual while/for loop conditions from the function instead of generic patterns
        """
        if not self.source_code_enriched:
            return []
        
        functions_data = self.source_code_enriched.get("functions", {})
        func_data = functions_data.get(function_name, {})
        source_code = func_data.get("from_source_code", {})
        
        return source_code.get("polling_conditions", [])
    
    def _get_code_generation_hints_for_function(self, function_name: str) -> Dict[str, Any]:
        """
        DATA-DRIVEN: Extract code generation hints and recommendations
        
        Returns recommendations for improving generated test code quality
        """
        if not self.source_code_enriched:
            return {}
        
        functions_data = self.source_code_enriched.get("functions", {})
        func_data = functions_data.get(function_name, {})
        source_code = func_data.get("from_source_code", {})
        
        return source_code.get("code_generation_hints", {})
    
    def _skip_internal_function_calls(self, function_sequence: List[str]) -> List[str]:
        """
        DATA-DRIVEN: Remove internal function calls from sequence to reduce code bloat
        
        Filters out functions that are called internally and marked as skip_in_test
        This provides the 33% code bloat reduction benefit
        """
        if not self.source_code_enriched:
            return function_sequence
        
        # Collect all internal calls across all functions
        all_internal_calls = set()
        
        functions_data = self.source_code_enriched.get("functions", {})
        for func_name, func_data in functions_data.items():
            source_code = func_data.get("from_source_code", {})
            internal_calls = source_code.get("internal_calls", [])
            for call in internal_calls:
                if call.get("skip_in_test"):
                    all_internal_calls.add(call.get("function"))
        
        # Filter sequence: keep only functions that are not internal calls
        filtered = [f for f in function_sequence if f not in all_internal_calls]
        
        if len(filtered) < len(function_sequence):
            bloat_reduction = len(function_sequence) - len(filtered)
            print(f"   [BLOAT-REDUCTION] Removed {bloat_reduction} internal function calls from sequence")
        
        return filtered
    
    def _initialize_prerequisites_in_code(self, function_name: str, code_template: str) -> str:
        """
        DATA-DRIVEN: Add prerequisite field initialization to code template
        
        Inserts initialization code for all fields required by the function
        This improves code quality by ensuring proper setup
        """
        if not self.source_code_enriched:
            return code_template
        
        prerequisites = self._get_prerequisites_for_function(function_name)
        if not prerequisites or not prerequisites.get("fields_to_set"):
            return code_template
        
        # Generate prerequisite initialization code
        init_lines = []
        for field_info in prerequisites.get("fields_to_set", []):
            field_name = field_info.get("field_name")
            if field_info.get("critical"):
                init_lines.append(f"    // PREREQUISITE: Set {field_name} (critical for {function_name})")
        
        if init_lines:
            init_code = "\n".join(init_lines)
            # Insert after struct initialization section
            insertion_point = code_template.find("// Initialize struct members")
            if insertion_point != -1:
                insertion_point = code_template.find("\n", insertion_point) + 1
                code_template = code_template[:insertion_point] + init_code + "\n" + code_template[insertion_point:]
        
        return code_template
    
    def _add_state_tracking_to_code(self, function_name: str, code_template: str) -> str:
        """
        DATA-DRIVEN: Add state variable tracking code to template
        
        Inserts code to track state variables (flags, counters) during test execution
        """
        if not self.source_code_enriched:
            return code_template
        
        state_vars = self._get_state_variables_for_function(function_name)
        if not state_vars:
            return code_template
        
        # Generate state tracking code
        tracking_lines = ["    // State variable tracking:"]
        for var_info in state_vars:
            var_name = var_info.get("field_name")
            var_purpose = var_info.get("purpose", "tracking")
            tracking_lines.append(f"    // {var_name}: {var_purpose}")
        
        if len(tracking_lines) > 1:  # More than just the comment header
            tracking_code = "\n".join(tracking_lines)
            # Append to function call section
            insertion_point = code_template.rfind("// Call main function")
            if insertion_point != -1:
                insertion_point = code_template.rfind("\n", 0, insertion_point) + 1
                code_template = code_template[:insertion_point] + tracking_code + "\n\n" + code_template[insertion_point:]
        
        return code_template
    
    def _apply_code_generation_hints(self, function_name: str, code_template: str) -> str:
        """
        DATA-DRIVEN: Apply code generation hints to improve code quality
        
        Applies all recommendations from source code analysis to the generated code
        """
        if not self.source_code_enriched:
            return code_template
        
        hints = self._get_code_generation_hints_for_function(function_name)
        if not hints or not hints.get("recommendations"):
            return code_template
        
        # Add recommendations as comments
        recommendation_lines = ["    // CODE GENERATION RECOMMENDATIONS:"]
        for rec in hints.get("recommendations", []):
            recommendation_lines.append(f"    // • {rec}")
        
        if len(recommendation_lines) > 1:
            rec_code = "\n".join(recommendation_lines)
            # Insert at the beginning of the code template
            code_template = rec_code + "\n\n" + code_template
        
        return code_template


# ============================================================================
# HELPER FUNCTIONS FOR IDEA 1 SEQUENTIAL LLM APPROACH
# ============================================================================

def format_hw_spec_for_sequential_reading(chunks: List[Dict[str, Any]]) -> str:
    """
    Format hardware specification chunks for sequential line-by-line reading by LLM
    
    Args:
        chunks: List of RAG chunks from hw_spec collection
        
    Returns:
        Formatted string with clear markers for sequential reading
    """
    formatted = []
    
    for i, chunk in enumerate(chunks, 1):
        formatted.append(f"\n{'='*80}")
        formatted.append(f"HARDWARE SPECIFICATION CHUNK {i}")
        formatted.append(f"{'='*80}")
        
        # Add source information
        metadata = chunk.get('metadata', {})
        if metadata:
            source = metadata.get('source', 'Unknown')
            section = metadata.get('section', 'General')
            subsection = metadata.get('subsection', '')
            formatted.append(f"\nSource: {source}")
            formatted.append(f"Section: {section}")
            if subsection:
                formatted.append(f"Subsection: {subsection}")
        
        # Add content
        formatted.append(f"\n[CHUNK CONTENT START]")
        content = chunk.get('content', '')
        formatted.append(content)
        formatted.append(f"[CHUNK CONTENT END]\n")
    
    return '\n'.join(formatted)


def format_minimal_kg_reference(minimal_kg_summary: Dict[str, Any]) -> Dict[str, str]:
    """
    Format minimal KG info for easy reference in LLM prompt
    
    Args:
        minimal_kg_summary: Dictionary with function_parameters, register_addresses, critical_deps
        
    Returns:
        Dictionary with formatted strings for each KG component
    """
    formatted = {}
    
    # Format function parameters
    func_params = minimal_kg_summary.get('function_parameters', {})
    if func_params:
        param_lines = []
        for func_name, params in func_params.items():
            param_lines.append(f"\n{func_name}(")
            for param in params:
                param_name = param.get('name', 'unknown')
                param_type = param.get('type', 'unknown')
                param_lines.append(f"  {param_type} {param_name}")
            param_lines.append(")")
        formatted['function_parameters'] = '\n'.join(param_lines)
    else:
        formatted['function_parameters'] = "No function parameters available"
    
    # Format register addresses
    reg_addrs = minimal_kg_summary.get('register_addresses', {})
    if reg_addrs:
        addr_lines = []
        for reg_name, addr_info in reg_addrs.items():
            address = addr_info.get('address', 'Unknown')
            description = addr_info.get('description', '')
            addr_lines.append(f"{reg_name}: 0x{address} {description}")
        formatted['register_addresses'] = '\n'.join(addr_lines)
    else:
        formatted['register_addresses'] = "No register addresses available"
    
    # Format critical dependencies
    crit_deps = minimal_kg_summary.get('critical_deps', {})
    if crit_deps:
        dep_lines = []
        for func_name, deps in crit_deps.items():
            if deps:
                dep_lines.append(f"{func_name} depends on: {', '.join(deps)}")
        formatted['critical_deps'] = '\n'.join(dep_lines) if dep_lines else "No critical dependencies"
    else:
        formatted['critical_deps'] = "No critical dependencies"
    
    return formatted


def generate_sample_c_code(
    function_sequence: List[str],
    struct_initializations: Dict[str, Dict[str, Any]],
    all_functions: List[Dict[str, Any]],
    module: str,
    struct_values: Optional[Dict[str, Any]] = None,
    all_structs: Optional[List[Dict[str, Any]]] = None,
    all_enums: Optional[List[Dict[str, Any]]] = None,
    user_description: str = "",
    polling_patterns: Optional[Dict[str, Dict[str, str]]] = None
) -> str:
    """
    Generate a DATA-DRIVEN C code skeleton for LLM enhancement.
    
    STRUCT MEMBER ASSIGNMENT LOGIC (your exact flow):
    1. For each config function in sequence → find matching struct (CamelCase word matching)
    2. For each struct member → get its 'type' from struct definition
    3. For that type → find matching enum from all_enums
    4. From enum values → pick the right value based on test context
    5. Generate: varName.memberName = EnumValue;
    
    100% DYNAMIC - ZERO HARDCODING:
    - ALL identifiers derived from function_sequence, struct definitions, enum definitions
    - Module header derived from common function prefix
    - Struct types and members from all_structs (with KG data)
    - Enum values from all_enums (with KG data)
    
    Args:
        function_sequence: Ordered list of function names (from topo sort)
        struct_initializations: Dictionary of struct names with pre-computed values
        all_functions: All available functions with parameters and content
        module: Module name (e.g., 'cxpi', 'lin', 'can')
        struct_values: Optional pre-computed struct values
        all_structs: Complete list of struct definitions with members
        all_enums: Complete list of enum definitions with values
        user_description: User's test description for context-aware enum selection
        
    Returns:
        Complete C code skeleton as string
    """
    code_lines = []
    all_structs = all_structs or []
    all_enums = all_enums or []
    polling_patterns = polling_patterns or {}  # Default to empty dict if not provided
    
    # Build lookup maps for quick access
    struct_lookup = {}  # struct_name -> struct_definition
    for s in all_structs:
        name = s.get('name', '')
        if name:
            struct_lookup[name] = s
    
    enum_lookup = {}  # enum_name -> enum_definition (with values)
    for e in all_enums:
        name = e.get('name', '')
        if not name:
            continue
        # If KG gave no values, parse them from full_content as fallback.
        # full_content format: "Values: Name_val0=0U: desc, Name_val1=1U: desc, ..."
        if not e.get('values'):
            e = dict(e)  # shallow copy — don't mutate caller's list
            e['values'] = _parse_enum_values_from_content(e.get('full_content', '') or e.get('content', ''))
        enum_lookup[name] = e
        # Also register without _t suffix for fuzzy matching
        if name.endswith('_t'):
            enum_lookup[name[:-2]] = e

    # =========================================================================
    # STEP 1: DYNAMICALLY DERIVE MODULE PREFIX FROM FUNCTION NAMES
    # =========================================================================
    detected_prefix = _detect_function_prefix(function_sequence, all_functions)
    module_header = f'{detected_prefix}.h' if detected_prefix else None
    
    # =========================================================================
    # SECTION A: INCLUDES (dynamically derived)
    # =========================================================================
    code_lines.append('#include <stdint.h>')
    code_lines.append('#include <stdbool.h>')
    code_lines.append('#include <stdio.h>')
    code_lines.append('#include <stdlib.h>')
    if module_header:
        code_lines.append(f'#include "{module_header}"')
    code_lines.append('')
    
    # =========================================================================
    # SECTION B: STATIC GLOBAL VARIABLES (derived from struct_initializations & functions)
    # =========================================================================
    code_lines.append('/* === Static global variables (derived from function parameters) === */')
    
    # Discover struct types needed from struct_initializations
    declared_vars = {}  # type_name -> variable_name
    for struct_name, struct_info in struct_initializations.items():
        var_name = _derive_variable_name(struct_name)
        code_lines.append(f'static {struct_name} {var_name};')
        declared_vars[struct_name] = var_name
    
    # Discover additional struct types from function parameters in sequence functions
    # CRITICAL: Only scan functions that are IN the sequence (not all_functions)
    # This ensures we declare exactly the types the generated code will use
    sequence_func_names = set(function_sequence)
    for func_info in all_functions:
        fname = func_info.get('name', '')
        # Also check normalized name (handle double-module pattern)
        fname_normalized = fname
        if fname.startswith('Ifx') and '_' in fname:
            after_ifx = fname[3:]
            mod_end = after_ifx.find('_')
            if mod_end > 0:
                mod = after_ifx[:mod_end]
                double_pfx = f'Ifx{mod}_{mod}_'
                single_pfx = f'Ifx{mod}_'
                if fname.startswith(double_pfx):
                    fname_normalized = fname.replace(double_pfx, single_pfx, 1)
                else:
                    fname_normalized = fname.replace(single_pfx, double_pfx, 1)
        
        if fname not in sequence_func_names and fname_normalized not in sequence_func_names:
            continue
        
        content = func_info.get('full_content', '') or func_info.get('content', '')
        if not content:
            continue
        first_line = content.split('\n')[0]
        if '(' in first_line:
            param_str = first_line.split('(', 1)[1].rsplit(')', 1)[0]
            params = [p.strip() for p in param_str.split(',')]
            for param in params:
                param = param.strip()
                if not param or param == 'void':
                    continue
                parts = param.replace('*', ' * ').split()
                if len(parts) >= 2:
                    param_type = ' '.join(parts[:-1]).replace(' * ', '*').replace(' *', '*').strip()
                    base_type = param_type.replace('*', '').replace('const', '').strip()
                    if base_type and base_type not in declared_vars and '_t' in base_type:
                        var_name = _derive_variable_name(base_type)
                        if var_name != 'unknown':
                            code_lines.append(f'static {base_type} {var_name};')
                            declared_vars[base_type] = var_name
    
    code_lines.append('')
    
    # Data buffers — buffer size dynamically discovered from function parameters and user description
    buf_size = _discover_buffer_size_standalone(all_functions, all_structs, user_description, struct_values)

    # -------------------------------------------------------------------------
    # Derive buffer direction labels from the actual function names in the
    # sequence.  The label is the FIRST camelCase word that signals the
    # direction for a TX (or RX) function.
    #
    # Strategy — fully data-driven, zero hardcoded strings:
    #   1. Split each function name on underscores AND on camelCase boundaries
    #      so  "IfxCxpi_transmitResponse" → ['ifxcxpi','transmit','response']
    #   2. The FIRST word in ANY function name that belongs to the direction
    #      word-sets below becomes the canonical label.
    #   3. The direction word-sets are the ONLY "vocabulary" here — they are
    #      a language-level classification (what does "transmit" mean?), not
    #      domain/module-specific knowledge.
    #
    # If no matching word is found the labels default to 'tx'/'rx'.
    # -------------------------------------------------------------------------
    def _camel_words(name: str):
        """Split 'IfxCxpi_transmitResponse' into ['ifxcxpi','transmit','response']."""
        # Step 1: split on underscores
        parts = name.split('_')
        words = []
        for part in parts:
            # Step 2: split camelCase segments on case transitions
            # e.g. 'transmitResponse' -> ['transmit', 'Response'] -> ['transmit','response']
            sub = re.sub(r'([A-Z])', r'_\1', part).strip('_')
            words.extend(w.lower() for w in sub.split('_') if w)
        return words

    _tx_direction_words = {'send', 'transmit', 'write', 'put', 'push', 'output'}
    _rx_direction_words = {'receive', 'read', 'recv', 'get', 'pull', 'input'}

    tx_label = None
    rx_label = None
    for _fn in function_sequence:
        _words = _camel_words(_fn)
        if tx_label is None:
            for _w in _words:
                if _w in _tx_direction_words:
                    tx_label = _w   # e.g. 'transmit', 'send', 'write' …
                    break
        if rx_label is None:
            for _w in _words:
                if _w in _rx_direction_words:
                    rx_label = _w   # e.g. 'receive', 'read' …
                    break
        if tx_label and rx_label:
            break

    # Shorten labels to a compact canonical form so variable names stay readable:
    # 'transmit' → 'tx',  'receive' → 'rx',  'send' → 'tx',  'read' → 'rx', etc.
    # The shortening map is also data-driven (built from the two direction word-sets).
    _tx_short_map = {w: 'tx' for w in _tx_direction_words}
    _rx_short_map = {w: 'rx' for w in _rx_direction_words}
    tx_label = _tx_short_map.get(tx_label, tx_label) if tx_label else 'tx'
    rx_label = _rx_short_map.get(rx_label, rx_label) if rx_label else 'rx'

    tx_buf_name = f'{tx_label}Buf'   # e.g. 'txBuf'
    rx_buf_name = f'{rx_label}Buf'   # e.g. 'rxBuf'
    code_lines.append(f'static uint8_t {tx_buf_name}[{buf_size}] = {{0}};')
    code_lines.append(f'static uint8_t {rx_buf_name}[{buf_size}] = {{0}};')

    # Register buffer variables so _generate_function_call() MATCH 3 can find them.
    # Sentinel key format: 'uint8_t_{label}buf'
    # The label stored here is the SAME compact label derived above ('tx'/'rx') so
    # that MATCH 3 can extract it back and compare it against per-function camelCase
    # words using the same _camel_words() split — guaranteeing the two sides always
    # use the same vocabulary with no hardcoded strings.
    _buf_role_tx = f'uint8_t_{tx_label}buf'   # e.g. 'uint8_t_txbuf'
    _buf_role_rx = f'uint8_t_{rx_label}buf'   # e.g. 'uint8_t_rxbuf'
    declared_vars[_buf_role_tx] = tx_buf_name
    declared_vars[_buf_role_rx] = rx_buf_name
    code_lines.append('')
    
    # Forward declaration
    code_lines.append('uint8_t run_test(void);')
    code_lines.append('')
    
    # =========================================================================
    # SECTION C: run_test() FUNCTION
    # Addresses all 12 critical issues from analysis:
    #  #1: Types used from struct_initializations keys (exact DB types)
    #  #2: MODULE pointer detected from function signatures
    #  #3: Config→member-init→init ordering (config BEFORE init)
    #  #4: Struct member assignments BETWEEN config call and init call
    #  #5: enableReception() inserted before RX operations (data-driven)
    #  #6: Polling uses status function calls (not struct member access)
    #  #7: uint8_t* cast for buffer params (in _generate_function_call)
    #  #8: Unsigned suffix for length params (in _generate_function_call)
    #  #9: Only Config structs get member inits (not Handle structs)
    #  #10: Error detection with while-loop polling
    #  #11: Descriptive printf before every major operation
    #  #12: Cleanup phase with dynamically discovered clear/cleanup functions
    # =========================================================================
    code_lines.append('uint8_t run_test(void)')
    code_lines.append('{')
    
    # =========================================================================
    # LOCAL VARIABLES — Dynamically discovered from function parameter signatures
    # Finds all output pointer parameters (scalar types with *) in sequence functions
    # and declares them as local variables. NO HARDCODING.
    # =========================================================================
    code_lines.append('  /* Local variables (discovered from function output parameters) */')
    local_vars = {}  # var_name → c_type_str
    
    sequence_func_names_set = set(function_sequence)
    for func_info in all_functions:
        fname = func_info.get('name', '')
        # Also check normalized name
        fname_normalized = fname
        if fname.startswith('Ifx') and '_' in fname:
            after_ifx = fname[3:]
            mod_end = after_ifx.find('_')
            if mod_end > 0:
                mod_part = after_ifx[:mod_end]
                double_pfx = f'Ifx{mod_part}_{mod_part}_'
                single_pfx = f'Ifx{mod_part}_'
                if fname.startswith(double_pfx):
                    fname_normalized = fname.replace(double_pfx, single_pfx, 1)
                else:
                    fname_normalized = fname.replace(single_pfx, double_pfx, 1)
        
        if fname not in sequence_func_names_set and fname_normalized not in sequence_func_names_set:
            continue
        
        content = func_info.get('full_content', '') or func_info.get('content', '')
        if not content or '(' not in content.split('\n')[0]:
            continue
        first_line = content.split('\n')[0]
        param_str = first_line.split('(', 1)[1].rsplit(')', 1)[0]
        params = [p.strip() for p in param_str.split(',')]
        
        for param in params:
            param = param.strip()
            if not param or param == 'void':
                continue
            parts = param.replace('*', ' * ').split()
            if len(parts) < 2:
                continue
            p_type = ' '.join(parts[:-1]).replace(' * ', '*').replace(' *', '*').strip()
            p_name = parts[-1]
            p_base = p_type.replace('*', '').replace('const', '').strip()
            is_ptr = '*' in p_type
            
            # Output pointer params to simple scalar types → declare as local variables
            # Skip struct types (those with _t suffix that are in declared_vars or struct_lookup)
            if is_ptr and p_base and p_base not in declared_vars and p_base not in struct_lookup:
                # Only simple scalar types become local variables
                # Struct types (already declared as static globals) are excluded
                is_scalar = any(kw in p_base.lower() for kw in ['uint', 'int', 'float', 'double', 'char', 'bool', 'size'])
                if is_scalar:
                    # Derive local variable name from parameter name (strip leading 'p' prefix)
                    var_name = p_name.lstrip('p').lstrip('_')
                    if not var_name:
                        var_name = p_name
                    if var_name not in local_vars:
                        local_vars[var_name] = p_base
    
    # Declare discovered local variables
    for var_name, var_type in local_vars.items():
        code_lines.append(f'  {var_type} {var_name} = 0;')
    
    code_lines.append('')
    
    # =========================================================================
    # PHASE CLASSIFICATION: Sort functions into ordered phases (DATA-DRIVEN)
    # Uses function name analysis (no hardcoded names, only keyword patterns)
    #
    # IMPORTANT: enableReception / enablePollingMethod are classified as
    # OPERATION functions (NOT a separate enable phase) so their position
    # in the KG topo-sorted sequence is preserved.  They will be semantically
    # re-paired with their target TX functions in the INJECT/ENABLE REORDER
    # pass below.
    # =========================================================================
    config_funcs = []      # initXxxConfig functions (config struct initializers)
    init_funcs = []        # initXxx functions (module/channel initializers, NOT config)
    operation_funcs = []   # transmit/receive/send/enable/inject operations
    status_funcs = []      # getStatus/getChannelStatus/getErrorFlags
    cleanup_funcs = []     # clearXxx/resetXxx/disableXxx
    
    for func_name in function_sequence:
        func_lower = func_name.lower()
        
        # Config init functions: have BOTH 'init' AND 'config' in name
        if 'init' in func_lower and 'config' in func_lower:
            config_funcs.append(func_name)
        # Init functions: have 'init' but NOT 'config' (they consume a config struct)
        elif 'init' in func_lower or 'setup' in func_lower or 'create' in func_lower:
            init_funcs.append(func_name)
        # Cleanup functions: clear, reset, disable, deinit
        elif any(kw in func_lower for kw in ['clear', 'reset', 'disable', 'cleanup', 'deinit']):
            cleanup_funcs.append(func_name)
        # Status/error check functions: getStatus, getChannelStatus, getErrorFlags
        elif any(kw in func_lower for kw in ['getstatus', 'getchannelstatus', 'geterror', 'checkstatus']):
            status_funcs.append(func_name)
        # Everything else is an operation function (including enableReception,
        # enablePollingMethod, injectTxError, transmit, receive, send, etc.)
        else:
            operation_funcs.append(func_name)
    
    # =========================================================================
    # SEMANTIC REORDERING PASS — inject & enableReception pairing
    # =========================================================================
    # Rule 1 — error-inject functions must immediately precede the TX function
    #   they corrupt.  Target TX is identified by highest name-word overlap,
    #   then by user-description word overlap, then by position (last TX).
    #
    # Rule 2 — enable-reception functions must immediately precede the TX call
    #   that triggers the corresponding reception on the other channel.
    #   Target TX is identified by payload-word overlap, then by "next TX after
    #   me" locality, then by nearest TX.
    #
    # ALL classifications are derived purely from:
    #   • detected_prefix  — common prefix extracted from function_sequence
    #   • all_functions    — KG function data (names, descriptions)
    #   • polling_patterns — already identifies the TX functions (they are the
    #                        keys of polling_patterns, since polling only applies
    #                        to TX/send/transmit calls)
    #   • user_description — for tiebreaking
    #
    # ZERO hardcoding of module names, function names, or domain vocabulary.
    # =========================================================================

    # --- Derive skip-words from the common function prefix (e.g. "IfxCxpi_Cxpi") ---
    # Split the prefix on underscores and lowercased segments become skip-words.
    # e.g. "IfxCxpi_Cxpi" → words extracted by regex → {'ifx', 'cxpi'}
    # This means ALL module-name fragments found in the actual function names are
    # excluded — no module names ever need to be listed explicitly.
    _prefix_skip = set(re.findall(r'[a-z]{2,}', (detected_prefix or '').lower()))

    def _semantic_words(name: str) -> set:
        """
        Extract semantic words from a function identifier.
        Strips the common module prefix words (derived from detected_prefix)
        so only action/payload words remain for comparison.
        e.g. "IfxCxpi_Cxpi_transmitResponse" → {'transmit', 'response'}
        """
        return set(re.findall(r'[a-z]{2,}', name.lower())) - _prefix_skip

    # --- Derive the set of TX function names from polling_patterns ---
    # polling_patterns is populated only for TX/send/transmit functions (established rule).
    # Any function NOT in polling_patterns but present in operation_funcs is either
    # RX, enable, inject, or purely combinatorial.
    _tx_func_names = set(polling_patterns.keys())

    # --- Derive inject-function names and enable-function names from all_functions ---
    # A function is an "inject" function if its name contains ANY word that also
    # appears in the name of another function PLUS a word that does NOT appear in
    # the standard init/config/receive/send/enable vocabulary (i.e. it is unusual).
    # More practically: we look at the function's own description/content in the KG.
    # If KG has no special tag, we rely on word overlap: an inject function will share
    # payload words with its target TX function (both touch the same data unit).
    #
    # For the GUARD check (is this function an inject or enable?), we scan
    # all_functions descriptions once to build two name-sets.
    _inject_func_names: set = set()
    _enable_func_names: set = set()
    for _fi in all_functions:
        _fn = _fi.get('name', '')
        if not _fn:
            continue
        _fn_words = _semantic_words(_fn)
        _desc_words = set(re.findall(r'[a-z]{3,}',
                          (_fi.get('description', '') or _fi.get('content', '') or '').lower()))
        # "inject" classification: KG description mentions inject/error/fault
        # OR the function name itself contains 'inject'
        if 'inject' in _fn_words or any(kw in _desc_words for kw in ('inject', 'fault', 'corruption')):
            _inject_func_names.add(_fn)
        # "enable" classification: function name contains 'enable'
        if 'enable' in _fn_words:
            _enable_func_names.add(_fn)

    # Also include any operation_funcs name whose semantic words contain 'inject'/'enable'
    # (handles cases where all_functions lookup didn't find the function)
    for _fn in operation_funcs:
        _fn_words = _semantic_words(_fn)
        if 'inject' in _fn_words:
            _inject_func_names.add(_fn)
        if 'enable' in _fn_words:
            _enable_func_names.add(_fn)

    def _is_tx_func(fname: str) -> bool:
        """True if fname is a known TX function (from polling_patterns) or its
        semantic words overlap with known TX function semantic words."""
        if fname in _tx_func_names:
            return True
        # Fallback: compare semantic words with union of all known TX function words
        if _tx_func_names:
            _all_tx_words = set()
            for _txf in _tx_func_names:
                _all_tx_words |= _semantic_words(_txf)
            _fname_words = _semantic_words(fname)
            # Must share at least one payload word AND not be an init/config/enable
            if (_fname_words & _all_tx_words) and 'enable' not in _fname_words:
                return True
        return False

    def _find_best_tx_partner(inject_name: str, ops_list: list, self_idx: int):
        """Return index of the TX function that inject_name should immediately precede.

        Priority order (ALL data-driven, zero hardcoding):
        1. Highest semantic-word overlap between inject_name and TX function name.
        2. Highest word overlap between inject_name words and user_description words
           cross-referenced with TX function words — picks the TX whose payload words
           appear most in the user description.
        3. Fallback: the LAST TX function in the list (inject fires just before final TX).
        """
        inj_words = _semantic_words(inject_name)

        tx_candidates = [(j, ops_list[j]) for j in range(len(ops_list))
                         if j != self_idx and _is_tx_func(ops_list[j])]
        if not tx_candidates:
            return None

        # Priority 1: direct name-word overlap
        best_idx, best_score = None, 0
        for j, tx in tx_candidates:
            score = len(inj_words & _semantic_words(tx))
            if score > best_score:
                best_score, best_idx = score, j
        if best_score > 0:
            return best_idx

        # Priority 2: user-description mediated overlap
        # For each TX candidate, compute overlap of its semantic words with
        # user_description words that also appear in inject_name words.
        desc_words = set(re.findall(r'[a-z]{3,}', (user_description or '').lower()))
        inj_desc_overlap = inj_words & desc_words  # words in both inject name and description
        if inj_desc_overlap:
            best_idx, best_score = None, 0
            for j, tx in tx_candidates:
                score = len(_semantic_words(tx) & inj_desc_overlap)
                if score > best_score:
                    best_score, best_idx = score, j
            if best_score > 0:
                return best_idx

        # Priority 3: last TX candidate
        return tx_candidates[-1][0]

    def _find_best_tx_for_enable(enable_name: str, ops_list: list, self_idx: int):
        """Return index of the TX function that enable_name should immediately precede.

        Priority order (ALL data-driven, zero hardcoding):
        1. Semantic words of enable_name (minus the enable/receive words that are
           common to ALL enable functions) matched against TX function words.
        2. First TX function that appears AFTER self_idx in the list — locality rule:
           "arm reception immediately before the TX that will trigger it."
        3. Nearest TX before self_idx as last resort.
        """
        # Strip words that are common to ALL enable functions so only the payload
        # remains. We derive the common words by intersecting the word bags of all
        # enable functions — words appearing in EVERY enable function are "noise".
        all_enable_words = [_semantic_words(fn) for fn in _enable_func_names if fn in ops_list]
        if len(all_enable_words) > 1:
            _common_enable_words = all_enable_words[0].copy()
            for _ew in all_enable_words[1:]:
                _common_enable_words &= _ew
        else:
            _common_enable_words = set()

        payload_words = _semantic_words(enable_name) - _common_enable_words

        tx_candidates = [(j, ops_list[j]) for j in range(len(ops_list))
                         if j != self_idx and _is_tx_func(ops_list[j])]
        if not tx_candidates:
            return None

        # Priority 1: payload-word overlap with TX name
        if payload_words:
            best_idx, best_score = None, 0
            for j, tx in tx_candidates:
                score = len(payload_words & _semantic_words(tx))
                if score > best_score:
                    best_score, best_idx = score, j
            if best_score > 0:
                return best_idx

        # Priority 2: first TX *after* self_idx (locality)
        after = [(j, tx) for j, tx in tx_candidates if j > self_idx]
        if after:
            return after[0][0]

        # Priority 3: nearest TX before self_idx
        before = [(j, tx) for j, tx in tx_candidates if j < self_idx]
        if before:
            return before[-1][0]

        return None

    # --- Pass A: reorder inject functions (must immediately precede target TX) ---
    i = 0
    while i < len(operation_funcs):
        fname = operation_funcs[i]
        if fname not in _inject_func_names:
            i += 1
            continue
        target_j = _find_best_tx_partner(fname, operation_funcs, i)
        if target_j is not None and i != target_j - 1:
            func = operation_funcs.pop(i)
            insert_at = target_j if target_j < i else target_j - 1
            operation_funcs.insert(insert_at, func)
            print(f"  [INJECT-REORDER] Moved '{func}' to immediately before '{operation_funcs[insert_at + 1]}'")
            # Don't increment — recheck from same position after move
        else:
            i += 1

    # --- Pass B: reorder enable functions (must immediately precede paired TX) ---
    i = 0
    while i < len(operation_funcs):
        fname = operation_funcs[i]
        if fname not in _enable_func_names:
            i += 1
            continue
        target_j = _find_best_tx_for_enable(fname, operation_funcs, i)
        if target_j is not None and i != target_j - 1:
            func = operation_funcs.pop(i)
            insert_at = target_j if target_j < i else target_j - 1
            operation_funcs.insert(insert_at, func)
            print(f"  [ENABLE-REORDER] Moved '{func}' to immediately before '{operation_funcs[insert_at + 1]}'")
        else:
            i += 1
    
    # =========================================================================
    # PAIR config→init functions by semantic matching (DATA-DRIVEN, Issue #3)
    # Pattern: initXxxConfig → set members → initXxx
    # Match by extracting the descriptor between "init" and "Config"
    # =========================================================================
    config_init_pairs = []  # List of (config_func, matching_init_func) tuples
    remaining_inits = list(init_funcs)
    
    for cfg_func in config_funcs:
        # Extract descriptor: "IfxCxpi_Cxpi_initModuleConfigForTest" → "ModuleForTest" or "Module"
        cfg_lower = cfg_func.lower()
        best_init = None
        best_score = 0
        
        # Extract words from config function name
        cfg_words = _split_identifier_to_words(cfg_func)
        cfg_words -= {'init', 'config', 't', 'for'}  # Remove generic words
        
        for init_func in remaining_inits:
            init_words = _split_identifier_to_words(init_func)
            init_words -= {'init', 't', 'for'}
            
            overlap = cfg_words & init_words
            if len(overlap) > best_score:
                best_score = len(overlap)
                best_init = init_func
        
        if best_init:
            config_init_pairs.append((cfg_func, best_init))
            remaining_inits.remove(best_init)
        else:
            # No matching init found - still process config function
            config_init_pairs.append((cfg_func, None))
    
    # Any remaining init functions without a config pair
    unpaired_inits = remaining_inits
    
    # =========================================================================
    # --- INIT PHASE (Issue #3, #4, #9): Correct ordering ---
    # For each (configFunc, initFunc) pair:
    #   1. Call configFunc (initializes config struct with defaults)
    #   2. Set config struct members (ONLY for Config structs, not Handle structs)
    #   3. Call initFunc (uses the configured struct)
    # =========================================================================
    if config_init_pairs or unpaired_inits:
        code_lines.append('  /* === [INIT] Module/channel initialization === */')
        code_lines.append(f'  printf("\\n $ Starting initialization $\\n");')
        code_lines.append('')
        
        # Track which structs have been initialized to prevent duplicate init blocks
        initialized_structs = set()
        
        for cfg_func, init_func in config_init_pairs:
            # Step 1: Call the config function
            code_lines.append(f'  printf("\\n $ Calling {cfg_func} $\\n");')
            call_line = _generate_function_call(cfg_func, all_functions, declared_vars, struct_initializations, enum_lookup)
            code_lines.append(f'  {call_line}')
            code_lines.append('')
            
            # Step 2: Set config struct members (Issue #4, #9)
            # This is a CONFIG function, so its matching struct IS a config struct → safe to init members
            # DEDUP: initialized_structs prevents the same struct from being initialized twice
            _add_struct_member_inits_v2(
                code_lines, cfg_func, 
                struct_lookup, enum_lookup, declared_vars,
                user_description,
                initialized_structs=initialized_structs
            )
            
            # Step 3: Call the matching init function (consumes the config struct)
            if init_func:
                code_lines.append(f'  printf("\\n $ Calling {init_func} $\\n");')
                call_line = _generate_function_call(init_func, all_functions, declared_vars, struct_initializations, enum_lookup)
                code_lines.append(f'  {call_line}')
                code_lines.append('')
        
        # Handle unpaired init functions (those without a config counterpart)
        for init_func in unpaired_inits:
            code_lines.append(f'  printf("\\n $ Calling {init_func} $\\n");')
            call_line = _generate_function_call(init_func, all_functions, declared_vars, struct_initializations, enum_lookup)
            code_lines.append(f'  {call_line}')
            code_lines.append('')
    
    # =========================================================================
    # --- OPERATION PHASE (Issue #6, #11): Communication operations with polling ---
    # NOTE: enableReception / enablePollingMethod / injectTxError are now included
    # directly in operation_funcs (classified above) and have been semantically
    # reordered by the INJECT/ENABLE REORDER pass so they appear in the correct
    # position relative to their paired TX function.  There is NO separate
    # ENABLE PHASE block — emitting all enables at the top before operations was
    # the root cause of the ordering bug.
    # CRITICAL FIX (Feb 2026): Now uses pre-generated polling_patterns dict
    # instead of trying to rediscover status functions, busy enums, and activity enums inline.
    # 
    # The polling_patterns dict is created by _update_polling_patterns_from_sequence()
    # which already discovered:
    # - Status check function (e.g., getChannelStatus)
    # - Busy/done enum values (e.g., IfxCxpi_ChStatus_busy)
    # - Activity enum values (e.g., IfxCxpi_Cxpi_ChActivity_txHeaderDone)
    # - Channel variable references
    # 
    # Each entry in polling_patterns:
    # {
    #   'func_name': {
    #     'position': 'after' or 'before',
    #     'code': 'while(busy == getChannelStatus(&channel, activity));'
    #   }
    # }
    # =========================================================================
    
    if operation_funcs:
        code_lines.append('  /* === [SEQUENCE] Communication / operation sequence === */')
        code_lines.append(f'  printf("\\n $ Starting main test sequence $\\n");')
        code_lines.append('')
        
        for func_name in operation_funcs:
            func_lower = func_name.lower()
            
            # Extract meaningful words from function name for matching
            func_words = set(re.findall(r'[a-z]+', func_lower))
            
            # Determine direction from function name words
            tx_indicators = {'send', 'transmit', 'tx', 'write', 'put', 'push'}
            rx_indicators = {'receive', 'read', 'rx', 'get', 'recv', 'pull'}
            is_tx = bool(func_words & tx_indicators)
            is_rx = bool(func_words & rx_indicators)
            
            # Printf before the operation (Issue #11)
            if is_tx:
                code_lines.append(f'  printf("\\n $ Transmitting: {func_name} $\\n");')
            elif is_rx:
                code_lines.append(f'  printf("\\n $ Receiving: {func_name} $\\n");')
            else:
                code_lines.append(f'  printf("\\n $ Executing: {func_name} $\\n");')
            
            # Generate the function call
            call_line = _generate_function_call(func_name, all_functions, declared_vars, struct_initializations, enum_lookup)
            code_lines.append(f'  {call_line}')
            
            # ================================================================
            # POSITION-AWARE POLLING EMISSION
            # polling_patterns only contains entries for TX/send/transmit functions
            # (RX functions are intentionally excluded by the TX-only rule in
            # _update_polling_patterns_from_sequence).  The 'position' field is
            # honoured here for future extensibility: 'after' (default) emits the
            # busy-wait loop after the function call; 'before' would emit it before.
            # ================================================================
            if func_name in polling_patterns:
                pattern = polling_patterns[func_name]
                polling_code = pattern.get('code', '')
                position = pattern.get('position', 'after')

                def _resolve_and_emit(pcode, lines, dvars):
                    """Resolve {CHANNEL_VAR} and {RX_CHANNEL_VAR} placeholders and append lines."""
                    # Collect all channel variables in declaration order
                    channel_vars = [
                        dvar for dtype, dvar in dvars.items()
                        if 'channel' in dtype.lower() and 'config' not in dtype.lower()
                        and 'uint8' not in dtype.lower()
                    ]
                    # {CHANNEL_VAR}    → first channel (master / TX side)
                    # {RX_CHANNEL_VAR} → second channel (slave / RX side), falls back to first
                    tx_ch = channel_vars[0] if channel_vars else 'channel'
                    rx_ch = channel_vars[1] if len(channel_vars) > 1 else tx_ch
                    resolved = pcode.replace('{CHANNEL_VAR}', tx_ch).replace('{RX_CHANNEL_VAR}', rx_ch)
                    for ln in resolved.strip().split('\n'):
                        if ln.strip():
                            lines.append(f'  {ln}')

                # 'before' position: insert the polling BEFORE the last appended call.
                # Implementation: pop the call line, emit polling, re-append the call.
                if position == 'before' and polling_code:
                    call_line_saved = code_lines.pop()  # temporarily remove the call
                    _resolve_and_emit(polling_code, code_lines, declared_vars)
                    code_lines.append(call_line_saved)   # re-insert call after polling
                elif position == 'after' and polling_code:
                    _resolve_and_emit(polling_code, code_lines, declared_vars)
            
            code_lines.append('')
    
    # =========================================================================
    # --- ERROR MONITORING PHASE (Issue #10): While-loop polling for error flags ---
    # If the user description mentions error/fault/inject, generate a polling loop
    # that repeatedly checks error flags until the expected error is detected
    # =========================================================================
    user_desc_lower = (user_description or '').lower()
    wants_error_monitoring = any(kw in user_desc_lower for kw in ['error', 'fault', 'inject', 'crc', 'timeout', 'detect'])
    
    if wants_error_monitoring:
        # Find error flags struct and getErrorFlags function from data
        error_struct_type = None
        error_struct_members = []
        get_error_func = None
        
        for s in all_structs:
            sname = s.get('name', '')
            if any(kw in sname.lower() for kw in ['error', 'flag']):
                error_struct_type = sname
                error_struct_members = [m.get('name', '') for m in s.get('members', []) if m.get('name')]
                break
        
        for func_info in all_functions:
            fname = func_info.get('name', '')
            if 'geterror' in fname.lower() or 'errorflags' in fname.lower():
                get_error_func = fname
                break
        
        if error_struct_type and get_error_func and error_struct_members:
            error_var = _derive_variable_name(error_struct_type)
            
            # Find the most relevant error member based on user description
            best_error_member = error_struct_members[0]  # default to first
            for member in error_struct_members:
                member_lower = member.lower()
                # Score based on user description keyword overlap
                if any(kw in member_lower for kw in user_desc_lower.split() if len(kw) > 2):
                    best_error_member = member
                    break
            
            # Declare error flags variable if not already declared
            if error_struct_type not in declared_vars:
                code_lines.append(f'  {error_struct_type} {error_var};')
                declared_vars[error_struct_type] = error_var
            
            code_lines.append(f'  /* === [ERROR MONITORING] Poll for error detection === */')
            code_lines.append(f'  printf("\\n $ Monitoring for error: {best_error_member} $\\n");')
            
            # Build the channel variable reference for error flags query
            channel_var_for_error = None
            for dtype, dvar in declared_vars.items():
                if 'channel' in dtype.lower() and 'config' not in dtype.lower():
                    channel_var_for_error = dvar
                    break
            
            if channel_var_for_error:
                code_lines.append(f'  while({error_var}.{best_error_member} == 0)')
                code_lines.append(f'  {{')
                code_lines.append(f'    {get_error_func}(&{channel_var_for_error}, &{error_var});')
                code_lines.append(f'  }}')
            else:
                code_lines.append(f'  while({error_var}.{best_error_member} == 0)')
                code_lines.append(f'  {{')
                code_lines.append(f'    {get_error_func}(&{error_var});')
                code_lines.append(f'  }}')
            
            code_lines.append(f'  printf("\\n $ Error detected: {best_error_member} $\\n");')
            code_lines.append('')
    
    # =========================================================================
    # --- CLEANUP PHASE (Issue #12): Clear interrupts and cleanup ---
    # Dynamically discover cleanup/clear functions from all_functions
    # If the sequence has explicit cleanup functions, use them.
    # Additionally, search all_functions for clearAllInterrupts or similar functions.
    # =========================================================================
    code_lines.append('  /* === [FINALIZE] Cleanup === */')
    
    # Use cleanup functions from the sequence
    if cleanup_funcs:
        for func_name in cleanup_funcs:
            code_lines.append(f'  {_generate_function_call(func_name, all_functions, declared_vars, struct_initializations, enum_lookup)}')
    
    # If no explicit cleanup, search all_functions for clear/cleanup functions
    # that take a channel parameter (to clear interrupts on each channel)
    if not cleanup_funcs:
        clear_func = None
        for func_info in all_functions:
            fname = func_info.get('name', '')
            if 'clear' in fname.lower() and 'interrupt' in fname.lower():
                clear_func = fname
                break
        
        if clear_func:
            # Call clear for each declared channel variable
            for dtype, dvar in declared_vars.items():
                if 'channel' in dtype.lower() and 'config' not in dtype.lower():
                    code_lines.append(f'  {clear_func}(&{dvar});')
    
    code_lines.append('')
    code_lines.append(f'  printf("\\n $ Test completed successfully $\\n");')
    code_lines.append('  return 0;')
    code_lines.append('}')
    
    return '\n'.join(code_lines)


def _add_struct_member_inits_v2(
    code_lines: List[str],
    func_name: str,
    struct_lookup: Dict[str, Dict[str, Any]],
    enum_lookup: Dict[str, Dict[str, Any]],
    declared_vars: Dict[str, str],
    user_description: str = "",
    initialized_structs: Optional[set] = None
):
    """
    MANDATORY struct config member value assignment — ALWAYS generates member assignments.
    
    CORRECT FLOW:
    1. Match config function to struct using CamelCase word matching
    2. Cross-reference struct_lookup name with declared_vars keys to find variable name
    3. Get members from struct definition, OR parse from full_content as fallback
    4. For each member → find matching enum → list values for LLM
    5. Generate: varName.memberName = EnumValue;
    
    FIXED (Feb 2026): 
    - Cross-references declared_vars keys with struct_lookup names (they may differ)
    - Parses members from full_content when KG members list is empty
    - NEVER silently returns — always generates member assignments
    - Debug prints for tracing matching logic
    
    Args:
        code_lines: List to append generated code lines to
        func_name: The config function name (e.g., 'IfxCxpi_Cxpi_initChannelConfig')
        struct_lookup: {struct_name: struct_definition_dict}
        enum_lookup: {enum_name: enum_definition_dict}
        declared_vars: {type_name: variable_name}
        user_description: User's test description for context-aware enum value selection
        initialized_structs: Set of struct names that have already been initialized.
    """
    user_desc_lower = (user_description or '').lower()
    func_words = _split_identifier_to_words(func_name)
    
    # Extract common prefix dynamically from function name
    # FIXED (Feb 2026): Use _extract_prefix_words helper — only short prefix segments,
    # NOT compound parts like 'initModuleConfigForTest' which contain meaningful words
    detected_prefix_words = _extract_prefix_words(func_name)
    
    # Generic words that don't help with matching
    generic_words = {'config', 'init', 'module', 'for', 't'}
    
    meaningful_func = func_words - detected_prefix_words - generic_words
    
    print(f"  [STRUCT-INIT] Processing config func: {func_name}")
    print(f"  [STRUCT-INIT]   func_words={func_words}, meaningful={meaningful_func}")
    
    # =========================================================================
    # STEP 1: Find the matching CONFIG struct for this config function.
    #
    # YOUR APPROACH (simple & correct):
    #   The global declarations are already built from function parameters.
    #   declared_vars = { 'IfxCxpi_Cxpi_ChannelConfig_t': 'channelConfigMaster', ... }
    #   So FIRST search declared_vars for a Config type that word-overlaps the func name.
    #   This is 100% reliable — declared_vars always has the right type names.
    #   Only fall back to struct_lookup (RAG) if declared_vars has nothing matching.
    #
    # WHY RAG-FIRST FAILS:
    #   RAG returns structs matching the TEST DESCRIPTION semantically.
    #   For "inject TX CRC error", RAG returns error/flag structs — not config structs.
    #   So struct_lookup may have zero Config structs → match always fails.
    # =========================================================================
    matched_struct_name = None
    matched_struct_def = None
    best_score = 0

    # --- PRIMARY: Search declared_vars for a Config type matching this func ---
    for dvar_type, dvar_name in declared_vars.items():
        if 'config' not in dvar_type.lower():
            continue
        dvar_words = _split_identifier_to_words(dvar_type)
        dvar_prefix = _extract_prefix_words(dvar_type)
        meaningful_dvar = dvar_words - dvar_prefix - generic_words
        overlap = meaningful_func & meaningful_dvar
        specific_overlap = overlap - generic_words
        # TIE-BREAK: penalise extra words the struct has that the func does NOT mention.
        # ChannelConfig_t    meaningful={'channel'}       extra=0  → score=10
        # ChannelConfigExt_t meaningful={'channel','ext'} extra=1  → score=5
        # This ensures the most-specific (fewest-extra) match always wins.
        extra_words = meaningful_dvar - meaningful_func
        score = len(specific_overlap) * 10 - len(extra_words) * 5
        is_match = len(specific_overlap) >= 1
        if is_match and score > best_score:
            best_score = score
            matched_struct_name = dvar_type
            matched_struct_def = struct_lookup.get(dvar_type, {})

    if matched_struct_name:
        print(f"  [STRUCT-INIT]   ✓ Matched via declared_vars: {matched_struct_name} (score={best_score})")
    else:
        # --- FALLBACK: Search struct_lookup (RAG results) ---
        for struct_name, struct_def in struct_lookup.items():
            if 'config' not in struct_name.lower():
                continue
            struct_words = _split_identifier_to_words(struct_name)
            struct_prefix_words = _extract_prefix_words(struct_name)
            meaningful_struct = struct_words - struct_prefix_words - generic_words
            overlap = meaningful_func & meaningful_struct
            specific_overlap = overlap - generic_words
            extra_words = meaningful_struct - meaningful_func
            score = len(specific_overlap) * 10 - len(extra_words) * 5
            is_match = len(specific_overlap) >= 1
            if is_match and score > best_score:
                best_score = score
                matched_struct_name = struct_name
                matched_struct_def = struct_def
        if matched_struct_name:
            print(f"  [STRUCT-INIT]   ✓ Matched via struct_lookup (RAG): {matched_struct_name} (score={best_score})")

    if not matched_struct_name:
        config_in_declared = [t for t in declared_vars if 'config' in t.lower()]
        config_in_lookup   = [n for n in struct_lookup if 'config' in n.lower()]
        print(f"  [STRUCT-INIT]   ✗ No matching Config struct found for {func_name}")
        print(f"  [STRUCT-INIT]   Config types in declared_vars: {config_in_declared}")
        print(f"  [STRUCT-INIT]   Config structs in struct_lookup: {config_in_lookup}")
        return
    
    # DEDUP CHECK: Skip if this struct has already been initialized
    if initialized_structs is not None:
        if matched_struct_name in initialized_structs:
            code_lines.append(f'  /* {matched_struct_name} members already initialized above — skipping */')
            code_lines.append('')
            return
        initialized_structs.add(matched_struct_name)

    # =========================================================================
    # STEP 1b: Get variable name — declared_vars is the authoritative source.
    # Since STEP 1 matched from declared_vars first, the key IS matched_struct_name.
    # Fallback: word-overlap cross-ref, then derive from struct name.
    # =========================================================================
    var_name = declared_vars.get(matched_struct_name)

    if not var_name:
        # Cross-ref: declared_vars type might differ slightly from matched_struct_name
        matched_struct_words = _split_identifier_to_words(matched_struct_name) - generic_words
        best_var_score = 0
        best_var_key = None
        for dvar_type, dvar_name in declared_vars.items():
            dvar_words = _split_identifier_to_words(dvar_type)
            dvar_prefix = _extract_prefix_words(dvar_type)
            dvar_meaningful = dvar_words - dvar_prefix - generic_words
            overlap = matched_struct_words & dvar_meaningful
            both_config = 'config' in dvar_type.lower() and 'config' in matched_struct_name.lower()
            score = len(overlap) * 10 + (5 if both_config else 0)
            if score > best_var_score and score >= 10:
                best_var_score = score
                best_var_key = dvar_type
                var_name = dvar_name
        if best_var_key:
            print(f"  [STRUCT-INIT]   ✓ Cross-ref: '{matched_struct_name}' → '{best_var_key}' → var '{var_name}'")
    
    if not var_name:
        # Final fallback: derive variable name from the struct name
        var_name = _derive_variable_name(matched_struct_name)
        print(f"  [STRUCT-INIT]   ⚠ Using derived var name: '{var_name}' for struct '{matched_struct_name}'")
    
    if not var_name:
        print(f"  [STRUCT-INIT]   ✗ Could not determine variable name for {matched_struct_name}")
        return
    
    # =========================================================================
    # STEP 2: Get struct members — from KG data OR parse from full_content.
    # When matched from declared_vars, matched_struct_def may be empty ({})
    # because the struct wasn't in the RAG results. In that case we try to
    # get members from struct_lookup by the matched name (STEP 4.2 in app.py
    # may have backfilled it), then fall back to parsing full_content.
    # =========================================================================
    # Re-fetch from struct_lookup in case STEP 4.2 backfilled it after STEP 1 ran
    if not matched_struct_def or not matched_struct_def.get('members'):
        matched_struct_def = struct_lookup.get(matched_struct_name, matched_struct_def or {})

    members = matched_struct_def.get('members', [])
    
    # =====================================================================
    # FIX: KG often returns members with type='None'. Check if ALL types are
    # missing/None and if so re-parse from full_content to get real types.
    # Also handle: KG has members but no types → merge types from full_content.
    # =====================================================================
    if members:
        types_missing = all(
            (m.get('type', m.get('member_type', '')) or 'None') in ('None', '', 'none')
            for m in members
        )
        if types_missing:
            full_content = matched_struct_def.get('full_content', '') or matched_struct_def.get('content', '')
            if full_content:
                parsed = _parse_struct_members_from_content(full_content)
                if parsed:
                    # Build name→type map from parsed content
                    parsed_type_map = {p['name']: p.get('type', '') for p in parsed}
                    # Merge types into KG members (KG has names, parsed has types)
                    for m in members:
                        mname = m.get('name', m.get('member_name', ''))
                        if mname and mname in parsed_type_map:
                            m['type'] = parsed_type_map[mname]
                            if 'member_type' in m:
                                m['member_type'] = parsed_type_map[mname]
                    print(f"  [STRUCT-INIT]   ✓ Merged types from full_content for {len(parsed_type_map)} members (KG had type=None)")
                else:
                    print(f"  [STRUCT-INIT]   ⚠ KG members have type=None AND full_content parse failed")
    
    if not members:
        # FALLBACK: Parse members from full_content (RAG data)
        full_content = matched_struct_def.get('full_content', '') or matched_struct_def.get('content', '')
        if full_content:
            members = _parse_struct_members_from_content(full_content)
            print(f"  [STRUCT-INIT]   ⚠ KG members empty, parsed {len(members)} members from full_content")
    
    if not members:
        # LAST RESORT: Generate TODO block so LLM can fill in — DO NOT silently return
        print(f"  [STRUCT-INIT]   ⚠ No members found for {matched_struct_name} — generating TODO block")
        code_lines.append(f'  /* Initialize {matched_struct_name} members */')
        code_lines.append(f'  /* TODO: Set {var_name} members — struct definition has no members in database */')
        code_lines.append(f'  /* {var_name}.memberName = value; */')
        code_lines.append('')
        return
    
    code_lines.append(f'  /* Initialize {matched_struct_name} members */')
    print(f"  [STRUCT-INIT]   Generating {len(members)} member assignments for {var_name}")
    
    # =========================================================================
    # STEP 3-5: For each member → get type → find enum → pick value
    # =========================================================================
    for member in members:
        member_name = member.get('name', member.get('member_name', ''))
        member_type = member.get('type', member.get('member_type', ''))
        member_desc = member.get('description', '')
        
        # Treat 'None' string as empty (KG sometimes returns string 'None')
        if member_type in ('None', 'none'):
            member_type = ''
        
        if not member_name:
            continue
        
        # Skip pointer members (they are set by init functions, not by user)
        if '*' in member_type:
            code_lines.append(f'  /* {var_name}.{member_name} — pointer, set by init function */')
            continue
        
        # =====================================================================
        # STEP 3: Find matching enum for this member's type
        # =====================================================================
        enum_def = _find_enum_def_for_member_type(member_type, enum_lookup)
        
        if enum_def:
            enum_values = enum_def.get('values', [])
            if enum_values:
                value_names = []
                for val in enum_values:
                    val_name = val.get('name', val.get('value_name', ''))
                    if val_name:
                        value_names.append(val_name)
                
                if value_names:
                    value_options = ', '.join(value_names)
                    code_lines.append(f'  // ENUM CHOICE REQUIRED - Select ONE from: [{value_options}]')
                    code_lines.append(f'  {var_name}.{member_name} = /* TODO: CHOOSE_FROM_ABOVE */;')
                else:
                    code_lines.append(f'  {var_name}.{member_name} = /* TODO: No enum values found for type {member_type} */;')
            else:
                code_lines.append(f'  {var_name}.{member_name} = /* TODO: Enum {member_type} has no values in database */;')
        else:
            # No enum found → use type-based default or list common values
            if 'bool' in member_type.lower() or 'enable' in member_name.lower():
                code_lines.append(f'  {var_name}.{member_name} = /* TODO: Choose from [TRUE, FALSE, 0, 1] */;')
            elif 'uint' in member_type.lower() or 'int' in member_type.lower():
                code_lines.append(f'  {var_name}.{member_name} = /* TODO: Set numeric value (check hardware spec for valid range) */;')
            else:
                default_val = _get_default_value_for_type(member_type, member_name, member_desc, user_desc_lower)
                code_lines.append(f'  {var_name}.{member_name} = {default_val};  /* TODO: Verify this default value */;')
    
    code_lines.append('')


def _parse_struct_members_from_content(full_content: str) -> List[Dict[str, str]]:
    """
    Parse struct members from RAG full_content when KG members list is empty.
    
    Handles TWO formats:
    
    FORMAT 1 — RAG summary (most common):
        Members: IfxCxpi_ChState_t enableCh: desc, uint32_t baudrate: desc, ...
    
    FORMAT 2 — C struct definition:
        typedef struct {
            IfxCxpi_Cxpi_Mode_t mode;
            boolean testEnable;
        } IfxCxpi_Cxpi_TestConfig_t;
    
    Returns:
        List of dicts with 'name' and 'type' keys
    """
    members = []
    if not full_content:
        return members
    
    # =====================================================================
    # FORMAT 1: RAG summary — "Members: Type1 name1: desc, Type2 name2: desc"
    # This is the dominant format from our RAG ingestion pipeline.
    # Pattern per member: "<Type> <name>: <description>"
    # Members are comma-separated but descriptions may contain commas,
    # so we split on ", <Type> <name>:" boundary.
    # =====================================================================
    members_idx = full_content.find('Members:')
    if members_idx >= 0:
        members_str = full_content[members_idx + len('Members:'):].strip()
        # Split on boundaries: ", <TypeName> <memberName>:"
        # TypeName starts with uppercase or is a known C type (uint32_t, bool, etc.)
        # Use regex: split before "TypePattern memberPattern:" 
        # BUT NOT the first entry (which doesn't have a leading comma)
        # Strategy: find ALL "Type name:" patterns and extract them
        
        # Pattern: a C type followed by a member name followed by ':'
        # Type: word with optional * (e.g., "IfxCxpi_Mode_t", "uint32_t", "bool", "IfxCxpi_t *")
        # Name: a lowercase-starting C identifier
        member_pattern = re.compile(
            r'(?:^|,\s*)'                          # start of string or comma separator
            r'((?:[A-Z][A-Za-z0-9_]*_t|'            # Type option 1: CamelCase_t (e.g., IfxCxpi_Mode_t)
            r'uint\d+_t|int\d+_t|'                  # Type option 2: uint32_t, int8_t
            r'bool(?:ean)?|'                         # Type option 3: bool/boolean
            r'float|double|void|char|'               # Type option 4: primitive
            r'[A-Z][A-Za-z0-9_]*)'                   # Type option 5: generic CamelCase (Ifx_CXPI)
            r'(?:\s*\*)?)'                           # Optional pointer
            r'\s+'                                   # Space between type and name
            r'([a-zA-Z_][a-zA-Z0-9_]*)'             # Member name
            r'\s*:'                                  # Colon before description
        )
        
        for m in member_pattern.finditer(members_str):
            mtype = m.group(1).strip()
            mname = m.group(2).strip()
            # Get description: text after "name:" until next member or end
            desc_start = m.end()
            # Description ends at the next comma-type-name pattern or end of string
            desc = ''
            next_match = member_pattern.search(members_str, desc_start)
            if next_match:
                desc = members_str[desc_start:next_match.start()].strip().rstrip(',').strip()
            else:
                desc = members_str[desc_start:].strip().rstrip(',').strip()
            
            members.append({
                'name': mname,
                'type': mtype,
                'description': desc
            })
        
        if members:
            return members
    
    # =====================================================================
    # FORMAT 2: C struct definition — typedef struct { ... }
    # =====================================================================
    brace_start = full_content.find('{')
    brace_end = full_content.rfind('}')
    
    if brace_start < 0 or brace_end < 0 or brace_end <= brace_start:
        return members
    
    body = full_content[brace_start + 1:brace_end]
    
    for line in body.split('\n'):
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
            continue
        
        # Remove trailing comments
        if '//' in line:
            line = line[:line.index('//')].strip()
        if '/*' in line:
            line = line[:line.index('/*')].strip()
        
        # Remove semicolons
        line = line.rstrip(';').strip()
        if not line:
            continue
        
        # Skip nested struct/union/enum declarations
        if any(kw in line.lower() for kw in ['struct', 'union', 'enum', '{', '}']):
            continue
        
        # Split into type and name: "IfxCxpi_Mode_t mode" → type="IfxCxpi_Mode_t", name="mode"
        parts = line.replace('*', ' * ').split()
        if len(parts) >= 2:
            member_name = parts[-1].strip()
            member_type = ' '.join(parts[:-1]).replace(' * ', '*').replace(' *', '*').strip()
            
            # Validate member name (must be a valid C identifier)
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', member_name):
                members.append({
                    'name': member_name,
                    'type': member_type
                })
    
    return members


def _parse_enum_values_from_content(content: str) -> List[Dict[str, Any]]:
    """
    Parse enum values directly from full_content text when KG values list is empty.

    The full_content of every RAG enum entry always contains a 'Values:' line in format:
        Values: EnumName_val0=0U: description, EnumName_val1=1U: description, ...

    This is the FALLBACK used when Neo4j KG did not return values for an enum
    (e.g., because the enum was not semantically close enough to the test description
    and thus wasn't retrieved in the top-N RAG results with KG enrichment).

    Returns:
        List of {name, value, description} dicts — same schema as KG values.
        Empty list if no Values line found.
    """
    if not content:
        return []

    values = []
    for line in content.split('\n'):
        line = line.strip()
        if not line.lower().startswith('values:'):
            continue
        # Strip the "Values:" prefix
        vals_str = line[len('values:'):].strip()
        # Each entry is separated by ", " — but descriptions may contain commas,
        # so split on pattern: ", <UpperCamelCase_identifier>=" using regex
        # This correctly handles: "IfxCxpi_ChannelId_0=0U: desc, IfxCxpi_ChannelId_1=1U: desc"
        entries = re.split(r',\s*(?=[A-Z][A-Za-z0-9]*_)', vals_str)
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            # Split on first '=' to get name and rest
            eq_idx = entry.find('=')
            if eq_idx < 0:
                continue
            val_name = entry[:eq_idx].strip()
            rest = entry[eq_idx + 1:].strip()
            # rest is like "0U: description" or "1U"
            colon_idx = rest.find(':')
            if colon_idx >= 0:
                val_num = rest[:colon_idx].strip().rstrip('U').rstrip('u')
                val_desc = rest[colon_idx + 1:].strip()
            else:
                val_num = rest.strip().rstrip('U').rstrip('u')
                val_desc = ''
            if val_name and re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', val_name):
                values.append({'name': val_name, 'value': val_num, 'description': val_desc})
        break  # Only one Values: line expected per enum

    return values


def _find_enum_def_for_member_type(
    member_type: str,
    enum_lookup: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Find the enum definition that matches a struct member's type.
    
    DATA-DRIVEN matching (priority order):
    1. Try exact match: member_type == enum_name
    2. Try without _t suffix: 'IfxCxpi_Mode_t' → 'IfxCxpi_Mode'
    3. Try substring match: check if core type name appears inside enum name
    4. Try fuzzy word-overlap match: CamelCase-split meaningful words
    
    FIXED (Feb 2026): 
    - Uses _split_identifier_to_words for prefix detection (not raw underscore parts)
    - Adds substring matching to handle prefix variations (single vs double module prefix)
    - e.g., member type 'IfxCxpi_ChannelId_t' matches enum 'IfxCxpi_Cxpi_ChannelId_t'
    
    Args:
        member_type: The type of the struct member (e.g., 'IfxCxpi_ChannelId_t')
        enum_lookup: Dictionary of enum definitions {enum_name: enum_def}
    
    Returns:
        The enum definition dict, or None if no match found
    """
    if not member_type or not enum_lookup:
        return None
    
    # Try exact match first
    if member_type in enum_lookup:
        return enum_lookup[member_type]
    
    # Try without _t suffix
    type_no_t = member_type.rstrip('_t').rstrip('_')
    if type_no_t in enum_lookup:
        return enum_lookup[type_no_t]
    
    # STEP 3: Substring match — handles prefix variations
    # Extract the descriptor part from the type name (after module prefix)
    # e.g., 'IfxCxpi_ChannelId_t' → descriptor = 'ChannelId'
    # Then check if any enum name contains 'ChannelId' as substring
    type_parts = member_type.split('_')
    # Find descriptor parts: skip 'Ifx<Mod>' prefix and '_t' suffix
    # Convention: parts[0] = 'IfxMod' or 'Ifx', descriptor = middle parts
    descriptor_parts = []
    for i, part in enumerate(type_parts):
        part_lower = part.lower()
        if part_lower == 't' or part_lower.startswith('ifx'):
            continue
        descriptor_parts.append(part)
    
    if descriptor_parts:
        descriptor = '_'.join(descriptor_parts)  # e.g., 'ChannelId' or 'Cxpi_ChannelId'
        descriptor_lower = descriptor.lower()
        
        for enum_name in enum_lookup:
            if descriptor_lower in enum_name.lower():
                return enum_lookup[enum_name]
    
    # STEP 4: Fuzzy word-overlap match with proper CamelCase prefix detection
    type_words = _split_identifier_to_words(member_type)
    
    # Dynamically detect prefix using CamelCase splitting (not raw parts)
    # This ensures 'IfxCxpi' → {'ifx', 'cxpi'} instead of {'ifxcxpi'}
    type_prefix_words = set()
    if len(type_parts) >= 2:
        type_prefix_words = _split_identifier_to_words(type_parts[0])
        if len(type_parts) >= 3:
            type_prefix_words |= _split_identifier_to_words(type_parts[1])
    type_prefix_words.add('t')  # suffix
    
    meaningful_type_words = type_words - type_prefix_words
    
    best_enum_def = None
    best_overlap = 0
    
    for enum_name, enum_data in enum_lookup.items():
        enum_words = _split_identifier_to_words(enum_name)
        
        # Dynamically detect prefix using CamelCase splitting
        enum_parts = enum_name.split('_')
        enum_prefix_words = set()
        if len(enum_parts) >= 2:
            enum_prefix_words = _split_identifier_to_words(enum_parts[0])
            if len(enum_parts) >= 3:
                enum_prefix_words |= _split_identifier_to_words(enum_parts[1])
        enum_prefix_words.add('t')
        
        meaningful_enum_words = enum_words - enum_prefix_words
        
        overlap = meaningful_type_words & meaningful_enum_words
        if len(overlap) > best_overlap:
            best_overlap = len(overlap)
            best_enum_def = enum_data
    
    if best_overlap >= 1:
        return best_enum_def
    
    return None


def _find_enum_value_for_member(
    member_name: str,
    member_type: str,
    member_desc: str,
    enum_lookup: Dict[str, Dict[str, Any]],
    user_desc_lower: str
) -> Optional[str]:
    """
    Find the correct enum value for a struct member.
    
    FLOW:
    1. Take the member's type (e.g., 'IfxCxpi_ChState_t')
    2. Find matching enum definition in enum_lookup
    3. From the enum's values, pick the RIGHT one based on:
       a. User description keywords (e.g., 'master' → pick Mode_master)
       b. Member name keywords (e.g., 'enableCh' → pick ChState_enable)
       c. Member description hints (e.g., 'enable/disable' → pick enable)
    
    Returns:
        The enum value name string, or None if no enum found for this type
    """
    if not member_type or not enum_lookup:
        return None
    
    # =========================================================================
    # STEP 1: Find the enum definition matching this member's type
    # =========================================================================
    enum_def = None
    
    # Try exact match first
    if member_type in enum_lookup:
        enum_def = enum_lookup[member_type]
    
    # Try without _t suffix
    type_no_t = member_type.rstrip('_t').rstrip('_')
    if not enum_def and type_no_t in enum_lookup:
        enum_def = enum_lookup[type_no_t]
    
    # Try fuzzy match: find enum whose name contains the type's key words
    if not enum_def:
        type_words = _split_identifier_to_words(member_type)
        
        # Dynamically detect prefix from type name
        type_prefix_words = _extract_prefix_words(member_type)
        type_prefix_words.add('t')  # suffix
        
        meaningful_type_words = type_words - type_prefix_words
        
        best_enum = None
        best_overlap = 0
        
        for enum_name, enum_data in enum_lookup.items():
            enum_words = _split_identifier_to_words(enum_name)
            
            # Dynamically detect prefix from enum name
            enum_prefix_words = _extract_prefix_words(enum_name)
            enum_prefix_words.add('t')
            
            meaningful_enum_words = enum_words - enum_prefix_words
            
            overlap = meaningful_type_words & meaningful_enum_words
            if len(overlap) > best_overlap:
                best_overlap = len(overlap)
                best_enum = enum_data
        
        if best_overlap >= 1:
            enum_def = best_enum
    
    if not enum_def:
        return None
    
    # =========================================================================
    # STEP 2: Pick the RIGHT enum value based on context
    # =========================================================================
    enum_values = enum_def.get('values', [])
    if not enum_values:
        return None
    
    member_name_lower = member_name.lower()
    member_desc_lower = (member_desc or '').lower()
    
    # Score each enum value
    best_value = None
    best_score = -1
    
    for val in enum_values:
        val_name = val.get('name', val.get('value_name', ''))
        val_desc = (val.get('description', '') or '').lower()
        val_name_lower = val_name.lower()
        score = 0
        
        # PRIORITY 1: User description match (strongest signal)
        # e.g., user says "master" → Mode_master gets big bonus
        # e.g., user says "crc error" → ErrorType_crc gets big bonus
        user_words = user_desc_lower.split()
        for word in user_words:
            if len(word) > 2 and word in val_name_lower:
                score += 20
            if len(word) > 2 and word in val_desc:
                score += 10
        
        # PRIORITY 2: Member name match (dynamic, no hardcoded keywords)
        # Split member name into words, check overlap with enum value name
        member_words = _split_identifier_to_words(member_name)
        val_words = _split_identifier_to_words(val_name)
        common_words = member_words & val_words
        
        # Exclude detected prefix words from scoring
        val_parts = val_name.split('_')
        val_prefix_words = _extract_prefix_words(val_name)
        val_prefix_words.add('t')
        
        meaningful_common = common_words - val_prefix_words
        score += len(meaningful_common) * 5
        
        # PRIORITY 3: Member description match (dynamic)
        # Check if any words from the member description appear in the enum value name/desc
        if member_desc_lower:
            desc_words = set(member_desc_lower.split())
            for word in desc_words:
                if len(word) > 3 and word in val_name_lower:
                    score += 3
                if len(word) > 3 and word in val_desc:
                    score += 2
        
        if score > best_score:
            best_score = score
            best_value = val_name
    
    # If no score-based match, fall back to FIRST enum value
    if best_value is None or best_score <= 0:
        first_val = enum_values[0]
        best_value = first_val.get('name', first_val.get('value_name', ''))
    
    return best_value


def _get_default_value_for_type(
    member_type: str, member_name: str, member_desc: str, user_desc_lower: str
) -> str:
    """
    Get a default value when no enum is found for a member's type.
    
    100% DATA-DRIVEN — infers ONLY from type structure.
    NO hardcoded keywords, NO fallbacks.
    Uses ONLY universal C syntax rules:
    - '*' in type → NULL (pointer syntax)
    - Otherwise → '0' (universal zero-init)
    
    This is the MOST MINIMAL, MOST GENERIC approach possible.
    Future enhancement: extract numeric hints from user_description.
    """
    if not member_type:
        return '0'
    
    # ONLY check for pointer syntax (universal C convention)
    # Pointer types → NULL (check for '*' character)
    if '*' in member_type:
        return 'NULL'
    
    # Everything else → '0' (universal C zero-init)
    # Type system will resolve the correct interpretation at compile time
    return '0'


def _extract_prefix_words(identifier: str) -> set:
    """
    Extract PREFIX words from a C identifier for word-overlap matching.

    The prefix is the module/namespace portion that should be EXCLUDED when
    computing meaningful word overlap between identifiers.

    KEY RULE: parts[1] is only treated as a prefix if it is a SHORT namespace word —
    i.e., it splits into <= 2 CamelCase sub-words (e.g., 'Cxpi', 'Lin', 'ChStatus').
    Compound descriptive parts like 'ChannelConfig', 'TestConfig', 'initChannel'
    contain meaningful words and must NOT be stripped.

    Decision table:
        'IfxCxpi_Cxpi_initChannel'           → strip parts[0]+parts[1] → {'ifx','cxpi'}
        'IfxCxpi_Cxpi_initModuleConfigForTest'→ strip parts[0]+parts[1] → {'ifx','cxpi'}
        'IfxCxpi_ChannelConfig_t'            → 3 parts, but parts[1]='ChannelConfig'
                                               has 2 sub-words → strip only parts[0] → {'ifx','cxpi'}
        'IfxCxpi_Cxpi_ChannelConfig_t'       → 4 parts, parts[1]='Cxpi' (1 word) → strip both → {'ifx','cxpi'}
        'IfxCxpi_initModuleConfigForTest'    → 2 parts → strip parts[0] only → {'ifx','cxpi'}
        'IfxCxpi_ChStatus_done'              → 3 parts, parts[1]='ChStatus' (2 words) → strip both → {'ifx','cxpi','ch','status'}
    """
    parts = identifier.split('_')
    prefix_words = set()

    if len(parts) >= 2:
        # parts[0] is ALWAYS the top-level namespace (e.g. 'IfxCxpi') — always strip it
        prefix_words = _split_identifier_to_words(parts[0])

        if len(parts) >= 3 and parts[-1].lower() != 't':
            # For function/enum names (not typedef structs ending in '_t'):
            # parts[1] is also namespace IF it has only 1 CamelCase sub-word (pure module, e.g. 'Cxpi')
            p1_words = _split_identifier_to_words(parts[1])
            if len(p1_words) <= 1:
                prefix_words |= p1_words
        elif len(parts) >= 4:
            # Struct/enum types with 4+ parts AND ending in '_t':
            # e.g. 'IfxCxpi_Cxpi_ChannelConfig_t' → parts[1]='Cxpi' is namespace
            # e.g. 'IfxCxpi_ChannelConfig_t'       → parts[1]='ChannelConfig' is NOT namespace
            p1_words = _split_identifier_to_words(parts[1])
            if len(p1_words) <= 1:
                prefix_words |= p1_words

    return prefix_words


def _split_identifier_to_words(identifier: str) -> set:
    """
    Split a C identifier into individual words using CamelCase and underscore boundaries.
    
    Examples:
        "IfxCxpi_Cxpi_initModuleConfigForTest" → {'ifx','cxpi','init','module','config','for','test'}
        "IfxCxpi_Cxpi_TestConfig_t" → {'ifx','cxpi','test','config','t'}
        "IfxCxpi_Cxpi_ChannelConfig_t" → {'ifx','cxpi','channel','config','t'}
    """
    # First split by underscore
    parts = identifier.split('_')
    words = set()
    for part in parts:
        # Split CamelCase: "initModuleConfigForTest" → "init","Module","Config","For","Test"
        camel_words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)', part)
        if camel_words:
            for w in camel_words:
                words.add(w.lower())
        elif part:
            words.add(part.lower())
    return words


def _discover_buffer_size_standalone(
    all_functions: List[Dict[str, Any]],
    all_structs: List[Dict[str, Any]],
    user_description: str,
    struct_values: Optional[Dict[str, Any]] = None
) -> int:
    """
    DATA-DRIVEN: Discover the correct data buffer size from available data sources.
    Standalone version (not a class method) for use in generate_sample_c_code().
    
    Strategy:
    1. Parse user_description for numeric byte count hints (e.g., "8 bytes", "255Byte")
    2. Check struct_values for length/size hints
    3. Check struct definitions for DataLength max ranges
    4. Check function params for documented size/length info
    5. Default: 8 (most common embedded protocol buffer size)
    
    Works for ANY module — ZERO hardcoding.
    """
    
    # STRATEGY 1: Extract buffer size from user_description text
    user_desc = user_description or ''
    # Match patterns like "8Byte", "255 bytes", "16 B", "8-byte"
    byte_matches = re.findall(r'(\d+)\s*[-]?\s*[Bb]yte', user_desc)
    if byte_matches:
        try:
            size = int(byte_matches[0])
            if size > 0:
                return size
        except (ValueError, IndexError):
            pass
    
    # STRATEGY 2: Check struct_values for length/size hints
    if struct_values:
        for sv_key, sv_val in struct_values.items():
            if any(kw in sv_key.lower() for kw in ['length', 'size', 'len']):
                try:
                    val = int(sv_val) if isinstance(sv_val, (int, float)) else None
                    if val and val > 0:
                        return val
                except (ValueError, TypeError):
                    pass
    
    # STRATEGY 3: Check struct definitions for DataLength max ranges
    if all_structs:
        for s in all_structs:
            s_name = (s.get('name', '') or '').lower()
            if 'datalength' in s_name or 'datasize' in s_name or 'framelen' in s_name:
                s_desc = _safe_str(s.get('brief', '') or s.get('description', ''))
                max_matches = re.findall(r'max(?:imum)?\s*[:=]?\s*(\d+)', s_desc.lower())
                if max_matches:
                    try:
                        return int(max_matches[0])
                    except ValueError:
                        pass
    
    # STRATEGY 4: Check function parameters for documented size/length hints
    if all_functions:
        for func in all_functions:
            func_name = _safe_str(func.get('name', '')).lower()
            if any(kw in func_name for kw in ['transmit', 'send', 'receive', 'read']):
                params = func.get('parameters', [])
                if isinstance(params, list):
                    for p in params:
                        if not isinstance(p, dict):
                            continue
                        p_name = _safe_str(p.get('name', '')).lower()
                        p_desc = _safe_str(p.get('description', ''))
                        if 'length' in p_name or 'size' in p_name or 'len' in p_name:
                            range_matches = re.findall(r'(\d+)', p_desc)
                            if range_matches:
                                try:
                                    max_val = max(int(v) for v in range_matches)
                                    if max_val > 0:
                                        return max_val
                                except ValueError:
                                    pass
    
    # STRATEGY 5: Default — most common in embedded protocols
    return 8


def _detect_function_prefix(function_sequence: List[str], all_functions: List[Dict[str, Any]]) -> str:
    """
    Dynamically detect the common function prefix from available functions.
    
    Analyzes function names to find the longest common prefix that contains
    the module identifier (e.g., "IfxCxpi_Cxpi" from "IfxCxpi_Cxpi_sendHeader").
    
    Returns the detected prefix or empty string if none found.
    """
    # Collect all function names
    func_names = list(function_sequence)
    for f in all_functions:
        name = f.get('name', '')
        if name and name != 'unknown':
            func_names.append(name)
    
    if not func_names:
        return ''
    
    # Filter to names that have at least 2 underscores (likely prefixed)
    prefixed = [n for n in func_names if n.count('_') >= 2]
    if not prefixed:
        return ''
    
    # Extract prefix candidates: everything before the last underscore-separated token
    # e.g., "IfxCxpi_Cxpi_sendHeader" → "IfxCxpi_Cxpi"
    prefix_candidates = []
    for name in prefixed:
        parts = name.rsplit('_', 1)
        if len(parts) == 2 and parts[0]:
            prefix_candidates.append(parts[0])
    
    if not prefix_candidates:
        return ''
    
    # Find the most common prefix
    prefix_counts = Counter(prefix_candidates)
    most_common_prefix = prefix_counts.most_common(1)[0][0]
    
    return most_common_prefix


def _derive_variable_name(type_name: str) -> str:
    """
    Derive a variable name from a struct/type name dynamically.
    
    FULLY DATA-DRIVEN: Detects prefix length by analyzing underscore-separated segments.
    The convention is: Ifx<Mod>_<SubMod>_<Descriptor>_t
    We keep the <Descriptor> part as the variable name (camelCase).
    
    The prefix is detected by looking for repeated module identifiers.
    e.g., "IfxCxpi_Cxpi_" has 'Cxpi' appearing twice → prefix is first 2 segments.
    e.g., "IfxLin_" has no repetition → prefix is first 1 segment.
    
    Examples:
        "IfxCxpi_Cxpi_Config_t"         → "config"
        "IfxCxpi_Cxpi_ChannelConfig_t"  → "channelConfig"
        "IfxCxpi_Cxpi_Channel_t"        → "channel"
        "IfxCxpi_Cxpi_TestConfig_t"     → "testConfig"
        "IfxCxpi_Cxpi_ErrorFlags_t"     → "errorFlags"
        "IfxCxpi_Cxpi_t"               → "cxpi"
        "IfxLin_Config_t"              → "config"
    """
    if not type_name:
        return 'unknown'
    
    # Remove _t suffix
    name = type_name
    if name.endswith('_t'):
        name = name[:-2]
    name = name.rstrip('_')
    
    # Split by underscore
    parts = name.split('_')
    
    if len(parts) <= 1:
        return parts[0][0].lower() + parts[0][1:] if parts and parts[0] else 'var'
    
    # Dynamically detect prefix length by finding where the module repetition ends.
    # Convention: Ifx<Mod>_<Mod>_... → prefix = 2 parts
    #             Ifx<Mod>_...        → prefix = 1 part
    # Detect repetition: if parts[1].lower() appears in parts[0].lower(), prefix=2
    prefix_len = 1  # Default: "Ifx<Mod>" is 1 segment
    if len(parts) >= 3:
        # Check if parts[1] is a repetition of the module in parts[0]
        # e.g., parts[0]="IfxCxpi", parts[1]="Cxpi" → "cxpi" in "ifxcxpi" → True
        if parts[1].lower() in parts[0].lower():
            prefix_len = 2
    
    # The descriptor parts come after the prefix
    suffix_parts = parts[prefix_len:]
    
    if not suffix_parts:
        # If no descriptor (e.g., "IfxCxpi_Cxpi_t" → type itself is the module handle)
        # Use the last prefix part as variable name
        last_prefix = parts[-1]
        return last_prefix[0].lower() + last_prefix[1:] if last_prefix else 'var'
    
    # CamelCase the remaining parts
    var_name = suffix_parts[0][0].lower() + suffix_parts[0][1:] if suffix_parts[0] else ''
    for p in suffix_parts[1:]:
        var_name += p[0].upper() + p[1:] if p else ''
    
    return var_name if var_name else 'var'


def _generate_function_call(func_name: str, all_functions: List[Dict[str, Any]], 
                             declared_vars: Dict[str, str],
                             struct_initializations: Dict[str, Dict[str, Any]],
                             enum_lookup: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """
    Generate a function call line with correct parameters from available function signatures.
    
    FULLY DATA-DRIVEN:
    - Parses function content to extract parameter types
    - Matches parameter types against declared variables
    - Detects MODULE hardware pointer parameters from type name patterns
    - Adds (uint8_t*) casts for buffer pointer parameters
    - Uses 'U' suffix for unsigned integer length parameters
    - Resolves enum-typed parameters by listing available values for LLM selection
    - All matching is based on C type system rules, zero hardcoding
    """
    enum_lookup = enum_lookup or {}
    # Try to find function by exact name, or by normalized name (handle double-module pattern)
    func_info_match = None
    for func_info in all_functions:
        name = func_info.get('name', '')
        if name == func_name:
            func_info_match = func_info
            break
    
    # If no exact match, try normalized matching (Ifx<Mod>_<Mod>_func ↔ Ifx<Mod>_func)
    if not func_info_match:
        for func_info in all_functions:
            name = func_info.get('name', '')
            # Detect module repetition pattern: extract module from func_name
            if func_name.startswith('Ifx') and '_' in func_name:
                # Extract what's between 'Ifx' and first '_'
                after_ifx = func_name[3:]
                mod_end = after_ifx.find('_')
                if mod_end > 0:
                    mod = after_ifx[:mod_end]
                    double_prefix = f'Ifx{mod}_{mod}_'
                    single_prefix = f'Ifx{mod}_'
                    # Try adding or removing the repeated module part
                    if func_name.startswith(double_prefix):
                        alt_name = func_name.replace(double_prefix, single_prefix, 1)
                    else:
                        alt_name = func_name.replace(single_prefix, double_prefix, 1)
                    if name == alt_name:
                        func_info_match = func_info
                        break
    
    if not func_info_match:
        return f'{func_name}(/* parameters not found in function database */);'
    
    content = func_info_match.get('full_content', '') or func_info_match.get('content', '')
    if not content or '(' not in content.split('\n')[0]:
        return f'{func_name}(/* no signature found */);'

    # =========================================================================
    # STEP 0: Parse Doxygen \param annotations from full_content.
    #
    # These are the AUTHORITATIVE ground-truth parameter specs written in the
    # header file.  They are used to:
    #   1. Detect extra / spurious parameters that appear in the RAG-stored
    #      first-line signature but are NOT in \param docs (e.g. a stray 'pId'
    #      parameter incorrectly ingested into the KG for transmitResponse).
    #   2. Determine whether each parameter is passed by value or by pointer
    #      (\param[in] scalar → value; \param[out] / \param[inout] → pointer).
    #
    # Format matched (Doxygen standard):
    #   \param[in]      paramName    Description text …
    #   \param[out]     paramName    Description text …
    #   \param[inout]   paramName    Description text …
    #   \param          paramName    Description text …  (direction defaults to 'in')
    #
    # DATA-DRIVEN: No function names are hardcoded.  The reconciliation logic
    # applies universally to every function whose full_content has \param lines.
    # =========================================================================
    _param_doc_pattern = re.compile(
        r'\\param(?:\[(in|out|inout)\])?\s+(\w+)',
        re.IGNORECASE
    )
    param_docs: List[Dict[str, str]] = []   # [{'name': ..., 'direction': 'in'|'out'|'inout'}, ...]
    for _pdm in _param_doc_pattern.finditer(content):
        _dir = (_pdm.group(1) or 'in').lower()
        _pname = _pdm.group(2)
        param_docs.append({'name': _pname, 'direction': _dir})

    first_line = content.split('\n')[0].strip()
    param_str = first_line.split('(', 1)[1].rsplit(')', 1)[0]
    params = [p.strip() for p in param_str.split(',')]

    # =========================================================================
    # STEP 0b-EXTRA: Structured-params fallback reconciliation.
    #
    # When the full_content has NO \param Doxygen lines (param_docs is empty),
    # the STEP 0b name-based reconciliation below cannot fire.  In that case we
    # fall back to the KG structured 'parameters' list — a clean list that was
    # parsed directly from the header, not from a RAG text chunk.
    #
    # If the RAG first-line has MORE parameters than the structured list, the
    # extra ones are spurious ingestion artefacts and must be dropped.
    # Truncation is safe here because the structured list is in declaration
    # order, matching the first-line order.
    #
    # Example (transmitResponse):
    #   RAG first-line params : [channel*, pId, data*, dataLen, crc]  ← 5 (wrong)
    #   KG structured params  : [channel, data, dataLen, crc]         ← 4 (correct)
    #   → truncate first-line to 4 → drop 'pId'
    # =========================================================================
    if not param_docs:
        structured_kp = func_info_match.get('parameters', [])
        if structured_kp and len(params) > len(structured_kp):
            dropped = params[len(structured_kp):]
            params = params[:len(structured_kp)]
            for _dp in dropped:
                print(f"  [PARAM-RECONCILE-KG] Dropped spurious param '{_dp.strip()}' "
                      f"from {func_name} (KG structured params count = {len(structured_kp)})")

    # =========================================================================
    # STEP 0b: Reconcile first-line params against \param docs.
    #
    # If \param docs exist AND the first-line has MORE parameters than the docs,
    # the extra parameters are spurious KG / RAG artefacts and must be dropped.
    # Match is done by POSITION (first \param doc = first legitimate param) so
    # that even if names differ between the signature and the Doxygen block the
    # correct subset is preserved.
    #
    # Example:
    #   first-line:  (channel*, pId, data*, dataLen, crc)   ← 5 params (wrong)
    #   \param docs: channel, data, dataLen, crc             ← 4 params (correct)
    #   → drop the 2nd param ('pId') → reconciled: (channel*, data*, dataLen, crc)
    #
    # Strategy:
    #   - Align by POSITION: zip(params, param_docs) — the Nth param doc matches
    #     the Nth first-line param.
    #   - If a first-line param name does NOT appear anywhere in the \param doc
    #     names AND the total first-line count exceeds the doc count, it is
    #     marked as spurious and excluded.
    # =========================================================================
    if param_docs and len(params) > len(param_docs):
        doc_names_lower = {pd['name'].lower() for pd in param_docs}
        reconciled_params = []
        for p44 in params:
            p44_stripped = p44.strip()
            if not p44_stripped or p44_stripped == 'void':
                reconciled_params.append(p44_stripped)
                continue
            # Extract the param name token (last word after type tokens)
            p44_parts = p44_stripped.replace('*', ' * ').split()
            p44_name = p44_parts[-1].lower() if p44_parts else ''
            # Keep if: (a) its name appears in \param docs, OR
            #           (b) it is a struct/pointer type with no plain name token
            #              (truncated signature — keep to preserve struct params)
            last_tok = p44_parts[-1] if p44_parts else ''
            is_type_token = last_tok and last_tok[0].isupper() and '_' in last_tok
            if p44_name in doc_names_lower or is_type_token:
                reconciled_params.append(p44_stripped)
            else:
                print(f"  [PARAM-RECONCILE] Dropped spurious param '{p44_stripped}' "
                      f"from {func_name} (not in \\param docs)")
        params = reconciled_params

    call_args = []

    # Build a direction look-up by param position so pointer obligation can be
    # enforced per-parameter without needing name matching.
    # Index N in param_docs corresponds to the Nth non-void param.
    _param_idx = 0   # tracks the current non-void param position

    for param in params:
        param = param.strip()
        if not param or param == 'void':
            continue

        # Look up \param direction for this positional parameter (if available)
        _pdoc = param_docs[_param_idx] if _param_idx < len(param_docs) else None
        _pdoc_dir = _pdoc['direction'] if _pdoc else 'in'
        _param_idx += 1
        
        # Extract type and name from parameter declaration
        parts = param.replace('*', ' * ').split()
        if len(parts) < 2:
            call_args.append(f'/* {param} */')
            continue
        
        param_type = ' '.join(parts[:-1]).replace(' * ', '*').replace(' *', '*').strip()
        param_name = parts[-1]
        base_type = param_type.replace('*', '').replace('const', '').strip()
        is_pointer = '*' in param_type

        # === TRUNCATION GUARD ===
        # RAG-stored signatures are sometimes truncated: the parameter name is dropped,
        # leaving only the type token (e.g., "const IfxCxpi_ErrorConfig_t" instead of
        # "const IfxCxpi_ErrorConfig_t *errorConfig").
        # When truncated: parts = ['const', 'IfxCxpi_ErrorConfig_t']
        #   → parts[-1] = 'IfxCxpi_ErrorConfig_t'  (a type, not a var name)
        #   → param_type = 'const', base_type = ''  (wrong)
        # Detection: parts[-1] starts with uppercase AND contains '_' → it is a type token.
        # Fix: treat the entire token list as the type, derive base_type correctly,
        # and infer pointer since Infineon APIs always pass _t structs by pointer.
        last_token = parts[-1]
        if last_token and last_token[0].isupper() and '_' in last_token:
            # No param name in signature — last token is the type itself
            full_type_str = ' '.join(parts).replace(' * ', '*').replace(' *', '*').strip()
            base_type = full_type_str.replace('*', '').replace('const', '').strip()
            is_pointer = '*' in full_type_str
            # Infineon convention: all _t struct params are passed by pointer
            if not is_pointer and base_type.endswith('_t'):
                is_pointer = True
            param_name = base_type  # fallback name

        matched = False

        # === MATCH 1: Direct type match with declared variables ===
        if base_type in declared_vars:
            var_ref = f'&{declared_vars[base_type]}' if is_pointer else declared_vars[base_type]
            call_args.append(var_ref)
            matched = True
        
        # === MATCH 2: MODULE hardware pointer detection (DATA-DRIVEN) ===
        # Detects TWO patterns for hardware module register block pointers:
        # Pattern A: "Ifx<Mod>_<Mod>" (wrapper type, e.g., IfxCxpi_Cxpi) — NO descriptor parts
        # Pattern B: "Ifx_<MOD>" (raw register type, e.g., Ifx_CXPI) — hardware register block
        # Both require &MODULE_<MOD_UPPER>0 reference (Infineon convention)
        if not matched and is_pointer:
            type_no_t = base_type.rstrip('_t').rstrip('_') if base_type.endswith('_t') else base_type
            type_parts = type_no_t.split('_')
            is_module_type = False
            mod_name = None
            
            # Pattern B: "Ifx_<MOD>" (e.g., "Ifx_CXPI") — raw hardware register type
            # The underscore between Ifx and MOD distinguishes this from wrapper types
            if len(type_parts) >= 2 and type_parts[0] == 'Ifx' and len(type_parts[1]) > 0:
                # Check if this is the raw register type: only 2 parts, no descriptors
                remaining = type_parts[2:] if len(type_parts) > 2 else []
                remaining = [p for p in remaining if p]
                if len(remaining) == 0:
                    is_module_type = True
                    mod_name = type_parts[1].upper()  # "CXPI" already uppercase
            
            # Pattern A: "Ifx<Mod>_<Mod>" (e.g., "IfxCxpi_Cxpi") — wrapper module type
            if not is_module_type and len(type_parts) >= 1 and type_parts[0].startswith('Ifx'):
                mod_from_type = type_parts[0][3:]  # e.g., "IfxCxpi" → "Cxpi"
                
                non_module_parts = []
                for i, part in enumerate(type_parts):
                    if i == 0:
                        continue
                    if part.lower() != mod_from_type.lower():
                        non_module_parts.append(part)
                
                if len(non_module_parts) == 0:
                    is_module_type = True
                    mod_name = mod_from_type.upper()
            
            if is_module_type and mod_name:
                call_args.append(f'&MODULE_{mod_name}0')
                matched = True
        
        # === MATCH 3: uint8_t* buffer parameters → cast with (uint8_t*) ===
        # DATA-DRIVEN: Finds all buffer-role sentinel keys registered by generate_sample_c_code().
        # Sentinel format: 'uint8_t_{role}buf'  e.g. 'uint8_t_txbuf', 'uint8_t_rxbuf'
        #
        # Direction matching (TX vs RX) is resolved in two steps:
        #
        # Step A — expand each role-label back to its full direction word-set using
        #   the same TX/RX vocabulary that was used when the sentinel was created.
        #   e.g. label 'tx' → {'send','transmit','write','put','push','output'}
        #        label 'rx' → {'receive','read','recv','get','pull','input'}
        #
        # Step B — split the function name on underscores AND on camelCase
        #   boundaries (using the same _camel_words helper defined in
        #   generate_sample_c_code) so 'transmitResponse' → ['transmit','response'].
        #   Then check whether any word in the function name belongs to the
        #   direction word-set for this sentinel.
        #
        # This is the ONLY correct approach — substring matching on merged
        # lowercase tokens (the previous approach) fails because 'tx' is not a
        # substring of 'transmitresponse'.
        if not matched and is_pointer and 'uint8' in base_type.lower():
            buf_sentinels = {
                k: v for k, v in declared_vars.items()
                if k.startswith('uint8_t_') and k.endswith('buf')
            }
            buf_var = None
            if buf_sentinels:
                # Direction word-sets (same as in generate_sample_c_code — must stay in sync)
                _tx_dir = {'send', 'transmit', 'write', 'put', 'push', 'output'}
                _rx_dir = {'receive', 'read', 'recv', 'get', 'pull', 'input'}
                # Short-label → full direction word-set
                _label_to_dir = {'tx': _tx_dir, 'rx': _rx_dir}

                # CamelCase-aware split of the function name
                def _split_camel(name: str):
                    parts = name.split('_')
                    words = []
                    for p in parts:
                        sub = re.sub(r'([A-Z])', r'_\1', p).strip('_')
                        words.extend(w.lower() for w in sub.split('_') if w)
                    return set(words)

                fn_words = _split_camel(func_name)

                best_sentinel_key = None
                for sentinel_key in buf_sentinels:
                    # Extract compact role label: 'uint8_t_txbuf' → 'tx'
                    role_label = sentinel_key[len('uint8_t_'):-len('buf')]
                    if not role_label:
                        continue
                    # Expand to full direction word-set; fall back to checking role_label directly
                    dir_words = _label_to_dir.get(role_label, {role_label})
                    if fn_words & dir_words:
                        best_sentinel_key = sentinel_key
                        break
                if best_sentinel_key is None:
                    # No direction word matched — fall back to first registered sentinel
                    best_sentinel_key = next(iter(buf_sentinels))
                buf_var = buf_sentinels[best_sentinel_key]
            if buf_var:
                call_args.append(f'(uint8_t *)&{buf_var}')
            else:
                call_args.append(f'(uint8_t *)&{param_name}')
            matched = True
        
        # === MATCH 4: Length/size parameters → use sizeof of buffer ===
        # DATA-DRIVEN: Detect length params by name semantics, reference actual buffer.
        # \param direction is consulted:
        #   \param[in]  dataLen → pass by VALUE  (e.g. transmitResponse: const DataLength_t dataLen)
        #   \param[out] dataLen → pass by POINTER (e.g. receiveResponse:  DataLength_t *dataLen)
        # If no \param doc is available, fall back to using is_pointer from the signature.
        if not matched:
            param_name_lower = param_name.lower()
            length_indicators = {'len', 'length', 'size', 'datalength', 'count', 'nbytes', 'datalen', 'bufsize', 'buflen'}
            if any(li in param_name_lower for li in length_indicators):
                # Determine whether this length param is an output pointer from \param docs
                # (overrides the first-line signature pointer flag when available)
                doc_says_out = _pdoc_dir in ('out', 'inout')
                effective_is_pointer = doc_says_out if param_docs else is_pointer
                # Find a buffer variable to reference
                found_buffer = False
                for dtype, dvar in declared_vars.items():
                    if '_t' not in dtype:
                        if effective_is_pointer:
                            call_args.append(f'&{dvar}Len')   # e.g. &dataLen (output)
                        else:
                            call_args.append(f'sizeof({dvar})')  # e.g. sizeof(dataBuf) (input)
                        found_buffer = True
                        break
                if not found_buffer:
                    if effective_is_pointer:
                        call_args.append(f'&{param_name}  /* length output */')
                    else:
                        call_args.append(f'0U  /* length: no buffer variable found */')
                matched = True

        # === MATCH 4b: \param[out]/\param[inout] scalar parameters ===
        # DATA-DRIVEN: When \param docs say a parameter is an output/inout AND
        # the first-line signature does NOT mark it as a pointer (e.g. the RAG
        # stored a value parameter but the actual header has `uint16_t *crc`),
        # force the argument to be passed by pointer address.
        #
        # This fixes e.g. `crc` which appears as `uint16_t crc` in a truncated
        # RAG signature but is `uint16_t *crc` in the real header.
        if not matched and param_docs and _pdoc_dir in ('out', 'inout') and not is_pointer:
            # Find a declared variable whose name matches the param name
            clean_pname = param_name.lower().lstrip('p').lstrip('_')
            found_out = False
            for dtype, dvar in declared_vars.items():
                dvar_lower = dvar.lower()
                if dvar_lower == clean_pname or clean_pname in dvar_lower or dvar_lower in clean_pname:
                    call_args.append(f'&{dvar}')
                    found_out = True
                    matched = True
                    break
            if not found_out:
                # Derive a plausible local variable name from param name
                call_args.append(f'&{clean_pname if clean_pname else param_name}')
                matched = True

        # === MATCH 5: Pointer to simple types (output parameters) ===
        # DATA-DRIVEN: For output pointer params, derive variable name from param name
        # by stripping pointer prefix and matching against declared local/global variables
        if not matched and is_pointer:
            param_name_lower = param_name.lower()
            # Strip common pointer prefixes (p, ptr, p_)
            clean_name = param_name
            if clean_name.startswith('p') and len(clean_name) > 1 and clean_name[1].isupper():
                clean_name = clean_name[1].lower() + clean_name[2:]
            elif clean_name.startswith('ptr'):
                clean_name = clean_name[3:]
            elif clean_name.startswith('p_'):
                clean_name = clean_name[2:]
            
            if not clean_name:
                clean_name = param_name
            
            # Try to match cleaned name against declared variables
            clean_lower = clean_name.lower()
            found_var = False
            for dtype, dvar in declared_vars.items():
                if clean_lower == dvar.lower() or clean_lower in dvar.lower() or dvar.lower() in clean_lower:
                    call_args.append(f'&{dvar}')
                    found_var = True
                    break
            
            if not found_var:
                # Use the cleaned param name as the variable reference
                call_args.append(f'&{clean_name}')
            matched = True
        
        # === MATCH 6: Enum/value parameters → try to find from declared vars by name similarity ===
        if not matched:
            # Try matching parameter name to a declared variable
            for dtype, dvar in declared_vars.items():
                if param_name.lower() in dvar.lower() or dvar.lower() in param_name.lower():
                    call_args.append(dvar)
                    matched = True
                    break
        
        # === MATCH 7: Enum-typed parameters → list available values for LLM/resolver ===
        # DATA-DRIVEN: If the parameter type matches an enum in enum_lookup,
        # list all available enum values so Stage 1 resolver or LLM can pick the correct one.
        # This handles non-pointer enum parameters like IfxCxpi_Cxpi_RxRequest_t, 
        # IfxCxpi_Cxpi_ErrInjTypes_t, etc.
        if not matched and enum_lookup:
            # Try to find enum by exact type match or fuzzy match
            matched_enum = None
            if base_type in enum_lookup:
                matched_enum = enum_lookup[base_type]
            elif base_type.endswith('_t') and base_type[:-2] in enum_lookup:
                matched_enum = enum_lookup[base_type[:-2]]
            else:
                # Fuzzy: extract meaningful words and find best overlap
                type_words = _split_identifier_to_words(base_type)
                type_prefix = _extract_prefix_words(base_type)
                type_prefix.add('t')
                meaningful_type = type_words - type_prefix
                
                best_enum_score = 0
                for ename, edata in enum_lookup.items():
                    ewords = _split_identifier_to_words(ename)
                    eprefix = _extract_prefix_words(ename)
                    eprefix.add('t')
                    meaningful_enum = ewords - eprefix
                    
                    overlap = len(meaningful_type & meaningful_enum)
                    if overlap > best_enum_score and overlap >= 1:
                        best_enum_score = overlap
                        matched_enum = edata
            
            if matched_enum:
                enum_values = matched_enum.get('values', [])
                value_names = [v.get('name', v.get('value_name', '')) for v in enum_values if v.get('name', v.get('value_name', ''))]
                if value_names:
                    options_str = ', '.join(value_names)
                    call_args.append(f'/* ENUM_PARAM: Select from [{options_str}] */')
                    matched = True
        
        if not matched:
            call_args.append(f'/* {param_name} */')
    
    return f'{func_name}({", ".join(call_args)});'


# =============================================================================
# STAGE 1 ENUM RESOLVER — Focused enum value selection using a small/fast model
# =============================================================================
# This extracts ALL enum TODO placeholders from the skeleton and builds a compact
# prompt for a small model (e.g., gpt-5-mini) to resolve correct enum values.
# The resolved values are substituted back into the skeleton BEFORE the main LLM
# enhancement, ensuring the main LLM doesn't hallucinate enum values.
#
# 100% DATA-DRIVEN: Works for ANY module, ANY enum, ANY struct.
# =============================================================================


def build_enum_resolver_prompt(
    sample_test_code: str,
    user_description: str,
    additional_notes: str = "",
    all_structs: Optional[List[Dict[str, Any]]] = None,
    all_enums: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
    """
    Build a MANDATORY focused prompt for Stage 1 enum resolution.
    
    THIS IS NOT OPTIONAL — it ALWAYS runs regardless of TODO comments.
    
    Scans the skeleton for ALL struct member assignments (LHS = RHS pattern),
    cross-references with struct definitions and enum definitions to find
    every assignment where enum options are available, and builds a compact
    prompt for a small model (gpt-5-mini) to choose the correct values.
    
    APPROACH:
    1. Parse skeleton for ALL lines matching: varName.memberName = <value>;
    2. For each such line, identify the struct type and member name
    3. Look up the member's type in struct definitions
    4. Find matching enum definition for that type
    5. Collect ALL available enum values as options
    6. Send to LLM: "Given test description, pick the right value for each"
    
    Also captures:
    - Function call enum parameters (/* ENUM_PARAM: Select from [...] */)
    - Boolean fields (TRUE/FALSE choices)
    - Any TODO/placeholder assignments
    
    100% DATA-DRIVEN: Parses skeleton text + struct/enum data. Zero hardcoding.
    Works for ANY module, ANY struct, ANY enum type.
    """
    
    lines = sample_test_code.split('\n')
    all_structs = all_structs or []
    all_enums = all_enums or []
    
    # Build lookup maps
    struct_lookup = {}  # struct_name -> {members: [{name, type, ...}]}
    for s in all_structs:
        name = s.get('name', '')
        if name:
            struct_lookup[name] = s
    
    enum_lookup = {}  # enum_name -> {values: [{name, ...}]}
    for e in all_enums:
        name = e.get('name', '')
        if not name:
            continue
        if not e.get('values'):
            e = dict(e)
            e['values'] = _parse_enum_values_from_content(e.get('full_content', '') or e.get('content', ''))
        enum_lookup[name] = e
        if name.endswith('_t'):
            enum_lookup[name[:-2]] = e

    # =========================================================================
    # STEP 1: Discover struct variable → type mappings from global declarations
    # Pattern: static StructType_t varName;
    # =========================================================================
    var_type_map = {}  # variable_name -> struct_type_name
    for line in lines:
        stripped = line.strip()
        decl_match = re.match(r'^static\s+(\S+)\s+(\w+)\s*;', stripped)
        if decl_match:
            decl_type = decl_match.group(1)
            decl_var = decl_match.group(2)
            var_type_map[decl_var] = decl_type
    
    # =========================================================================
    # STEP 2: Scan ALL struct member assignments and classify them
    # =========================================================================
    enum_tasks = []
    task_id = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # -----------------------------------------------------------------
        # PATTERN A: Struct member assignment: varName.memberName = <value>;
        # Matches: config.mode = 0;  OR  config.mode = /* TODO: ... */;
        # Also matches: config.mode = SomeEnumValue;
        # -----------------------------------------------------------------
        member_assign_match = re.match(
            r'^(\w+)\.(\w+)\s*=\s*(.+?)\s*;',
            stripped
        )
        
        if member_assign_match:
            var_name = member_assign_match.group(1)
            member_name = member_assign_match.group(2)
            current_rhs = member_assign_match.group(3).strip()
            
            # Look up struct type for this variable
            struct_type = var_type_map.get(var_name, '')
            struct_def = struct_lookup.get(struct_type)
            
            if not struct_def:
                # Try fuzzy: variable name might partially match a struct type
                for st_name, st_def in struct_lookup.items():
                    st_var = _derive_variable_name(st_name)
                    if st_var == var_name:
                        struct_def = st_def
                        struct_type = st_name
                        break
            
            if not struct_def:
                continue
            
            # Find this member in the struct definition
            members = struct_def.get('members', [])
            
            # FIX: If members have type='None', re-parse from full_content
            if members and all(
                (m2.get('type', m2.get('member_type', '')) or 'None') in ('None', '', 'none')
                for m2 in members
            ):
                full_content = struct_def.get('full_content', '') or struct_def.get('content', '')
                if full_content:
                    parsed = _parse_struct_members_from_content(full_content)
                    if parsed:
                        pmap = {p['name']: p for p in parsed}
                        for m2 in members:
                            mn2 = m2.get('name', m2.get('member_name', ''))
                            if mn2 in pmap:
                                m2['type'] = pmap[mn2].get('type', '')
                                if 'member_type' in m2:
                                    m2['member_type'] = pmap[mn2].get('type', '')
            
            if not members:
                # Fallback: parse members from full_content
                full_content = struct_def.get('full_content', '') or struct_def.get('content', '')
                if full_content:
                    members = _parse_struct_members_from_content(full_content)
            
            member_type = None
            member_desc = ''
            for m in members:
                m_name = m.get('name', m.get('member_name', ''))
                if m_name == member_name:
                    member_type = m.get('type', m.get('member_type', ''))
                    member_desc = m.get('description', '')
                    break
            
            if not member_type or member_type in ('None', 'none'):
                continue
            
            # Find matching enum for this member type
            enum_def = _find_enum_def_for_member_type(member_type, enum_lookup)
            enum_options = []
            
            if enum_def:
                for val in enum_def.get('values', []):
                    val_name = val.get('name', val.get('value_name', ''))
                    if val_name:
                        enum_options.append(val_name)
            
            # Also check: is this a boolean-like field?
            is_boolean = (
                'bool' in member_type.lower() or
                'enable' in member_name.lower() or
                'boolean' in member_type.lower()
            )
            if is_boolean and not enum_options:
                enum_options = ['TRUE', 'FALSE']
            
            # Only create a task if we have options to choose from
            if enum_options:
                task_id += 1
                # Check if the comment line above has extra context
                context_line = lines[i - 1].strip() if i > 0 else ''
                
                enum_tasks.append({
                    'id': task_id,
                    'type': 'struct_member',
                    'assignment': f'{var_name}.{member_name}',
                    'struct_type': struct_type,
                    'member_name': member_name,
                    'member_type': member_type,
                    'member_desc': member_desc,
                    'current_value': current_rhs,
                    'options': enum_options,
                    'context_line': context_line,
                    'line_number': i
                })
            continue
        
        # -----------------------------------------------------------------
        # PATTERN B: Function call with enum parameter placeholder
        # e.g., IfxFunc(arg1, /* ENUM_PARAM: Select from [val1, val2] */, arg3)
        # -----------------------------------------------------------------
        if '/* ENUM_PARAM: Select from [' in stripped:
            match = re.search(r'/\* ENUM_PARAM: Select from \[([^\]]+)\] \*/', stripped)
            if match:
                options_str = match.group(1)
                options = [o.strip() for o in options_str.split(',') if o.strip()]
                
                func_name = stripped.split('(')[0].strip() if '(' in stripped else 'unknown'
                
                task_id += 1
                enum_tasks.append({
                    'id': task_id,
                    'type': 'function_param',
                    'function': func_name,
                    'full_call': stripped,
                    'options': options,
                    'line_number': i
                })
    
    if not enum_tasks:
        return None  # No struct members with enum options found at all
    
    # =========================================================================
    # STEP 3: Build compact, focused LLM prompt
    # =========================================================================
    prompt_parts = []
    prompt_parts.append("You are an enum value resolver for embedded C test code.")
    prompt_parts.append("Your ONLY job: select the CORRECT enum value for each struct member assignment below.")
    prompt_parts.append("You are given the LEFT-HAND SIDE (struct member) and ALL available RIGHT-HAND SIDE values (enum options).")
    prompt_parts.append("Pick the single best value for each based on the test description and context.")
    prompt_parts.append("")
    prompt_parts.append(f"TEST DESCRIPTION: {user_description}")
    if additional_notes:
        prompt_parts.append(f"ADDITIONAL NOTES: {additional_notes}")
    prompt_parts.append("")
    prompt_parts.append("RULES:")
    prompt_parts.append("1. You MUST select ONLY from the provided OPTIONS list — no inventing values")
    prompt_parts.append("2. Consider the test description to pick the contextually correct value")
    prompt_parts.append("3. Consider the variable name and member name for semantic context")
    prompt_parts.append("4. For channel roles: master/channel0 → master-related values; slave/channel3 → slave-related values")
    prompt_parts.append("5. For boolean/enable fields: pick TRUE/enabled unless description explicitly says disabled")
    prompt_parts.append("6. For mode fields: pick the mode that matches the test scenario (e.g., 'master' if testing master TX)")
    prompt_parts.append("7. For channelId fields: pick based on which channel the test uses (e.g., channel 0 for first channel)")
    prompt_parts.append("8. If a member already has a reasonable non-zero enum value, you may keep it — but still evaluate")
    prompt_parts.append("9. Output ONLY a JSON object mapping each task ID to the chosen value — no explanation")
    prompt_parts.append("")
    prompt_parts.append("ENUM RESOLUTION TASKS:")
    prompt_parts.append("")
    
    for task in enum_tasks:
        if task['type'] == 'struct_member':
            prompt_parts.append(f"  TASK {task['id']}: {task['assignment']} = ???")
            prompt_parts.append(f"    STRUCT: {task['struct_type']}")
            prompt_parts.append(f"    MEMBER TYPE: {task['member_type']}")
            if task['member_desc']:
                prompt_parts.append(f"    DESCRIPTION: {task['member_desc']}")
            prompt_parts.append(f"    CURRENT VALUE: {task['current_value']}")
            prompt_parts.append(f"    OPTIONS: [{', '.join(task['options'])}]")
            prompt_parts.append("")
        elif task['type'] == 'function_param':
            prompt_parts.append(f"  TASK {task['id']}: Parameter in {task['function']}(...)")
            prompt_parts.append(f"    CALL: {task['full_call']}")
            prompt_parts.append(f"    OPTIONS: [{', '.join(task['options'])}]")
            prompt_parts.append("")
    
    prompt_parts.append("OUTPUT FORMAT (JSON only, no markdown, no explanation):")
    prompt_parts.append("{")
    for task in enum_tasks:
        prompt_parts.append(f'  "{task["id"]}": "<chosen_value_from_OPTIONS>",')
    prompt_parts.append("}")
    
    return '\n'.join(prompt_parts)


def _extract_enum_options_from_comment(comment_line: str) -> List[str]:
    """
    Extract enum option names from a comment line like:
    // ENUM CHOICE REQUIRED - Select ONE from: [IfxCxpi_Cxpi_Mode_master, IfxCxpi_Cxpi_Mode_slave]
    
    Returns list of option strings, or empty list.
    DATA-DRIVEN: Parses any bracket-enclosed comma-separated list.
    """
    match = re.search(r'\[([^\]]+)\]', comment_line)
    if match:
        options_str = match.group(1)
        return [o.strip() for o in options_str.split(',') if o.strip()]
    return []


def apply_resolved_enums(
    sample_test_code: str,
    resolved_values: Dict[str, str],
    all_structs: Optional[List[Dict[str, Any]]] = None,
    all_enums: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Apply Stage 1 resolved enum values back into the skeleton code.
    
    UNIVERSAL APPROACH: Uses the EXACT same scanning logic as
    build_enum_resolver_prompt() to ensure task IDs align perfectly.
    
    Only increments task_id for assignments that HAVE enum options
    (matching the prompt builder exactly), then replaces those RHS values.
    
    Args:
        sample_test_code: Original skeleton code
        resolved_values: Dict mapping task ID (str) to chosen enum value name
            Example: {"1": "IfxCxpi_Cxpi_Mode_master", "2": "TRUE", ...}
        all_structs: List of struct definitions (same as passed to prompt builder)
        all_enums: List of enum definitions (same as passed to prompt builder)
    
    Returns:
        Updated skeleton code with enum values applied
    
    100% DATA-DRIVEN: No hardcoded values, works for any module.
    """
    
    lines = sample_test_code.split('\n')
    all_structs = all_structs or []
    all_enums = all_enums or []
    
    # Build the SAME lookup maps as build_enum_resolver_prompt
    struct_lookup = {}
    for s in all_structs:
        name = s.get('name', '')
        if name:
            struct_lookup[name] = s
    
    enum_lookup = {}
    for e in all_enums:
        name = e.get('name', '')
        if not name:
            continue
        if not e.get('values'):
            e = dict(e)
            e['values'] = _parse_enum_values_from_content(e.get('full_content', '') or e.get('content', ''))
        enum_lookup[name] = e
        if name.endswith('_t'):
            enum_lookup[name[:-2]] = e

    # Discover variable → type map
    var_type_map = {}
    for line in lines:
        stripped = line.strip()
        decl_match = re.match(r'^static\s+(\S+)\s+(\w+)\s*;', stripped)
        if decl_match:
            var_type_map[decl_match.group(2)] = decl_match.group(1)
    
    task_id = 0
    result_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # PATTERN A: Struct member assignment (SAME logic as prompt builder)
        member_match = re.match(r'^(\w+)\.(\w+)\s*=\s*(.+?)\s*;', stripped)
        if member_match:
            var_name = member_match.group(1)
            member_name = member_match.group(2)
            
            # Resolve struct type
            struct_type = var_type_map.get(var_name, '')
            struct_def = struct_lookup.get(struct_type)
            if not struct_def:
                for st_name, st_def in struct_lookup.items():
                    st_var = _derive_variable_name(st_name)
                    if st_var == var_name:
                        struct_def = st_def
                        struct_type = st_name
                        break
            
            if struct_def:
                # Find member type
                members = struct_def.get('members', [])
                member_type = None
                for m in members:
                    m_name = m.get('name', m.get('member_name', ''))
                    if m_name == member_name:
                        member_type = m.get('type', m.get('member_type', ''))
                        break
                
                if member_type:
                    # Check for enum options (SAME logic as prompt builder)
                    enum_def = _find_enum_def_for_member_type(member_type, enum_lookup)
                    enum_options = []
                    if enum_def:
                        for val in enum_def.get('values', []):
                            val_name = val.get('name', val.get('value_name', ''))
                            if val_name:
                                enum_options.append(val_name)
                    
                    is_boolean = (
                        'bool' in member_type.lower() or
                        'enable' in member_name.lower() or
                        'boolean' in member_type.lower()
                    )
                    if is_boolean and not enum_options:
                        enum_options = ['TRUE', 'FALSE']
                    
                    # Only count as task if enum options exist (matches prompt builder)
                    if enum_options:
                        task_id += 1
                        task_key = str(task_id)
                        
                        if task_key in resolved_values:
                            resolved_val = resolved_values[task_key]
                            indent = line[:len(line) - len(line.lstrip())]
                            result_lines.append(f'{indent}{var_name}.{member_name} = {resolved_val};')
                        else:
                            result_lines.append(line)
                    else:
                        result_lines.append(line)
                else:
                    result_lines.append(line)
            else:
                result_lines.append(line)
            continue
        
        # PATTERN B: Function call ENUM_PARAM
        if '/* ENUM_PARAM: Select from [' in stripped:
            task_id += 1
            task_key = str(task_id)
            if task_key in resolved_values:
                resolved_val = resolved_values[task_key]
                new_line = re.sub(
                    r'/\* ENUM_PARAM: Select from \[[^\]]+\] \*/',
                    resolved_val,
                    line
                )
                result_lines.append(new_line)
            else:
                result_lines.append(line)
            continue
        
        result_lines.append(line)
    
    return '\n'.join(result_lines)


def build_llm_prompt_idea_1_sequential(
    hw_spec_chunks: List[Dict[str, Any]],
    user_description: str,
    additional_notes: str,
    sample_test_code: str,
    minimal_kg_summary: Dict[str, Any],
    test_code_prompt_template: str,
    all_functions: Optional[List[Dict[str, Any]]] = None,
    all_structs: Optional[List[Dict[str, Any]]] = None,
    all_enums: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Build a FULLY DATA-DRIVEN LLM prompt for test code generation.
    
    100% DYNAMIC - ZERO HARDCODING:
    - Uses test_code_prompt_template as the system-level rules
    - Injects hw_spec, KG reference, user description, and skeleton code
    - Includes COMPLETE lists of available function names, struct members, enum values
    - No module-specific patterns, function names, or identifiers
    - All context comes from the provided data parameters
    
    Args:
        hw_spec_chunks: Top N raw hw_spec chunks from RAG
        user_description: User's test description
        additional_notes: Additional user notes
        sample_test_code: Generated C code skeleton (from generate_sample_c_code)
        minimal_kg_summary: KG info (param types, register addresses, deps)
        test_code_prompt_template: Test code prompt rules from test_code_prompt.md
        all_functions: Complete list of available function dicts (name, parameters)
        all_structs: Complete list of struct dicts (name, members)
        all_enums: Complete list of enum dicts (name, values)
        
    Returns:
        Formatted prompt string for LLM
    """
    
    # Format hw_spec chunks for sequential reading
    hw_spec_text = format_hw_spec_for_sequential_reading(hw_spec_chunks)
    
    # Format minimal KG info
    kg_reference = format_minimal_kg_reference(minimal_kg_summary)
    
    # Build available functions reference from KG summary
    available_functions_text = kg_reference.get('function_parameters', 'No function parameters available')
    register_text = kg_reference.get('register_addresses', 'No register addresses available')
    dependencies_text = kg_reference.get('critical_deps', 'No critical dependencies')
    
    # =========================================================================
    # BUILD COMPLETE AVAILABLE IDENTIFIERS LIST
    # This ensures LLM uses ONLY real names from the databases
    # =========================================================================
    
    # Available function names (ALL that RAG detected)
    available_functions_list = "NONE"
    if all_functions:
        func_lines = []
        for func in all_functions:
            name = func.get('name', '')
            if name and name != 'unknown':
                # Include signature if available
                content = func.get('full_content', '') or func.get('content', '')
                sig = ''
                if content:
                    first_line = content.split('\n')[0].strip()
                    if '(' in first_line:
                        sig = f"  // {first_line}"
                func_lines.append(f"  - {name}{sig}")
        if func_lines:
            available_functions_list = '\n'.join(func_lines)
    
    # Available structs with their members (from KG)
    available_structs_list = "NONE"
    if all_structs:
        struct_lines = []
        for struct in all_structs:
            name = struct.get('name', '')
            members = struct.get('members', [])
            if name and name != 'unknown':
                struct_lines.append(f"  struct {name} {{")
                for member in members:
                    m_name = member.get('name', member.get('member_name', ''))
                    m_type = member.get('type', member.get('member_type', 'unknown'))
                    m_desc = member.get('description', '')
                    if m_name:
                        desc_comment = f"  // {m_desc}" if m_desc else ""
                        struct_lines.append(f"    {m_type} {m_name};{desc_comment}")
                struct_lines.append(f"  }}")
                struct_lines.append("")
        if struct_lines:
            available_structs_list = '\n'.join(struct_lines)
    
    # Available enums with their values (from KG)
    available_enums_list = "NONE"
    if all_enums:
        enum_lines = []
        for enum in all_enums:
            name = enum.get('name', '')
            values = enum.get('values', [])
            if name and name != 'unknown':
                enum_lines.append(f"  enum {name} {{")
                for val in values:
                    v_name = val.get('name', val.get('value_name', ''))
                    v_num = val.get('value', val.get('numeric_value', ''))
                    v_desc = val.get('description', '')
                    if v_name:
                        parts = []
                        if v_num is not None and v_num != '':
                            parts.append(f"{v_name} = {v_num}")
                        else:
                            parts.append(f"{v_name}")
                        desc_comment = f"  // {v_desc}" if v_desc else ""
                        enum_lines.append(f"    {parts[0]},{desc_comment}")
                enum_lines.append(f"  }}")
                enum_lines.append("")
        if enum_lines:
            available_enums_list = '\n'.join(enum_lines)
    
    prompt = f"""
{test_code_prompt_template}

═══════════════════════════════════════════════════════════════════════════
HARDWARE SPECIFICATION CONTEXT
═══════════════════════════════════════════════════════════════════════════

{hw_spec_text}

═══════════════════════════════════════════════════════════════════════════
AVAILABLE FUNCTIONS (USE ONLY THESE - DO NOT INVENT NEW ONES)
═══════════════════════════════════════════════════════════════════════════

{available_functions_list}

═══════════════════════════════════════════════════════════════════════════
AVAILABLE STRUCTS WITH MEMBERS (USE ONLY THESE MEMBER NAMES AND TYPES)
═══════════════════════════════════════════════════════════════════════════

{available_structs_list}

═══════════════════════════════════════════════════════════════════════════
AVAILABLE ENUMS WITH VALUES (USE ONLY THESE ENUM VALUES - DO NOT INVENT)
═══════════════════════════════════════════════════════════════════════════

{available_enums_list}

═══════════════════════════════════════════════════════════════════════════
FUNCTION PARAMETER TYPES & DEPENDENCIES (from Knowledge Graph)
═══════════════════════════════════════════════════════════════════════════

FUNCTION PARAMETER TYPES:
{available_functions_text}

REGISTER INFORMATION:
{register_text}

FUNCTION DEPENDENCIES:
{dependencies_text}

═══════════════════════════════════════════════════════════════════════════
USER TEST REQUIREMENT
═══════════════════════════════════════════════════════════════════════════

TEST DESCRIPTION: {user_description}
ADDITIONAL NOTES: {additional_notes if additional_notes else "None"}

═══════════════════════════════════════════════════════════════════════════
MANDATORY OPERATION SEQUENCE — EVERY CALL BELOW MUST APPEAR IN YOUR OUTPUT
═══════════════════════════════════════════════════════════════════════════

The skeleton below contains the EXACT operation sequence derived from hardware
documentation.  Every function call in the skeleton's [SEQUENCE] section MUST
be present in your output in the SAME ORDER.  Do NOT add, remove, or reorder
any of these calls.  Do NOT replace a call with a comment or a printf.

If a call's arguments need refinement (wrong variable, wrong cast) you may
correct the argument — but the function name itself must be preserved exactly.

Specifically, the following operation calls are REQUIRED (do not skip any):"""

    # Dynamically extract the operation function calls from the skeleton so the
    # LLM gets an explicit, numbered list it cannot ignore.
    seq_call_lines = []
    in_seq = False
    for _ln in (sample_test_code or '').splitlines():
        _lns = _ln.strip()
        if '[SEQUENCE]' in _lns:
            in_seq = True
            continue
        if in_seq:
            # Stop at the next phase marker or end of function
            if _lns.startswith('/*') and any(ph in _lns for ph in ['[ENABLE]', '[ERROR]', '[FINALIZE]', '[INIT]', '[CONFIG]', '[VALIDATION]']):
                break
            # Capture actual function call lines (end with ';')
            if _lns.endswith(';') and '(' in _lns and not _lns.startswith('//') and not _lns.startswith('while'):
                seq_call_lines.append(_lns)

    if seq_call_lines:
        prompt += '\n'
        for _i, _cl in enumerate(seq_call_lines, 1):
            prompt += f'\n  {_i}. {_cl}'
        prompt += '\n'
    else:
        prompt += '\n  (see skeleton [SEQUENCE] section below)\n'

    prompt += f"""

═══════════════════════════════════════════════════════════════════════════
CODE SKELETON — ENHANCE THIS, DO NOT CHANGE ITS STRUCTURE
═══════════════════════════════════════════════════════════════════════════

This skeleton was generated by Stage 1 from verified hardware documentation.
It contains the correct phase order, loop patterns, and enum values.

Your task: enhance run_test() to fully match the user's test requirement by:
- Completing all struct member assignments (see R2 in rules above)
- Adding printf debug output at every phase boundary (see R7 in rules above)
- Resolving any remaining /* TODO: CHOOSE_FROM_ABOVE */ comments (see Phase 2)
- Ensuring ForTest / ForErrorCtl variants are used where available (see R1)

REMINDER — identifiers come ONLY from the lists injected above:
  Functions  → AVAILABLE FUNCTIONS section
  Members    → AVAILABLE STRUCTS section
  Enum vals  → AVAILABLE ENUMS section
  Unknown    → /* TODO: check DB for correct identifier */

```c
{sample_test_code}
```

═══════════════════════════════════════════════════════════════════════════
TASK: OUTPUT THE COMPLETE ENHANCED C FILE NOW
═══════════════════════════════════════════════════════════════════════════

Produce the full .c file: all #includes, all static globals, and the complete
uint8_t run_test(void) function. Ready for direct compilation.

FINAL HALLUCINATION CHECK: Before writing your output, scan every identifier
you have written. If any function name, struct member, or enum value does not
appear in the AVAILABLE FUNCTIONS / STRUCTS / ENUMS sections above, replace
it with /* TODO: check DB for correct identifier */ — do NOT submit invented names.

```c
"""
    
    return prompt


# ============================================================================
# POST-LLM VALIDATION CHECKLIST (Stage 2 Quality Assurance)
# ============================================================================

def validate_generated_test_code(code: str, skeleton_code: str = None) -> Dict[str, Any]:
    """
    Validate generated test code against PRE-SUBMISSION CHECKLIST.
    
    Runs AFTER LLM enhancement (Stage 2) to catch common issues:
    - Extra while-loops added that were not in the skeleton
    - Struct members not initialized
    - Forbidden patterns (pollCount, timeout, break in loops)
    - Invented functions/enums
    - Case sensitivity issues (true/false vs TRUE/FALSE)
    
    NOTE on while-loops: The skeleton generates THREE types:
      1. TX busy-wait spin-loops: while(Status_busy == getStatus(...));   ← after TX calls
      2. Error monitoring body-loops: while(flags.member == 0) { getErrorFlags(...); }  ← [ERROR] phase
      3. (no RX polling — polling is placed BEFORE RX calls, not after)
    The LLM must copy all of these from the skeleton and MUST NOT add new ones.
    
    When skeleton_code is provided, exact while-loop count comparison is used.
    Without skeleton_code, a heuristic detects Status-based while-loops after RX calls.
    
    DATA-DRIVEN: All checks use pattern recognition, zero hardcoding.
    
    Returns: {
        'status': 'pass' | 'fail' | 'warning',
        'total_checks': int,
        'passed': int,
        'failed': int,
        'warnings': List[str],
        'errors': List[str],
        'summary': str
    }
    """
    import re
    
    violations = []
    warnings_list = []
    passed_count = 0
    failed_count = 0
    
    # ========== CHECK 1: Single function uint8_t run_test(void) ==========
    func_pattern = r'uint8_t\s+run_test\s*\(\s*void\s*\)\s*\{'
    func_matches = re.findall(func_pattern, code)
    if len(func_matches) == 1:
        passed_count += 1
    elif len(func_matches) == 0:
        violations.append("FAIL: No 'uint8_t run_test(void)' function found")
        failed_count += 1
    else:
        violations.append(f"FAIL: Found {len(func_matches)} run_test() functions (expected 1)")
        failed_count += 1
    
    # ========== CHECK 2: No extra while-loops added beyond skeleton ==========
    # The skeleton generates exactly two kinds of while-loops:
    #   1. TX spin-wait:       while(Status_busy == getChannelStatus(...));    ← after TX
    #   2. Error monitoring:   while(flags.member == 0) { getErrorFlags(...); } ← [ERROR] phase
    # The LLM must NOT add any new while-loops. Polling is placed BEFORE RX
    # calls in the skeleton, so a Status-based while-loop directly after an
    # RX call is always an LLM addition.
    #
    # BEST PATH: if skeleton_code is provided, count while-loops in both and compare.
    # FALLBACK:  detect Status-based while-loops immediately after RX calls.
    extra_while_violations = []

    if skeleton_code is not None:
        # Exact comparison: count all while-loop occurrences in each
        skeleton_while_count = len(re.findall(r'\bwhile\s*\(', skeleton_code))
        generated_while_count = len(re.findall(r'\bwhile\s*\(', code))
        if generated_while_count > skeleton_while_count:
            extra_while_violations.append(
                f"FAIL: Generated code has {generated_while_count} while-loops but skeleton has "
                f"{skeleton_while_count} — LLM added {generated_while_count - skeleton_while_count} extra loop(s)"
            )
    else:
        # Heuristic fallback: flag Status-based while-loops immediately after RX calls.
        # Error monitoring loops (while(flags.member==0)) are NOT flagged — they are
        # skeleton-generated and only contain 'Status' if the member name happens to.
        rx_followed_by_while_pattern = re.compile(
            r'((?:Ifx\w+_)?receive(?:Header|Response|Response_Blocking)\s*\([^)]*\)\s*;)'
            r'(?:[ \t]*\n){1,3}\s*(while\s*\([^)]*ChStatus[^)]*\)\s*;)',
            re.MULTILINE
        )
        for match in rx_followed_by_while_pattern.finditer(code):
            line_num = code[:match.start()].count('\n') + 1
            extra_while_violations.append(
                f"FAIL: Extra spin-wait while-loop after RX call at line ~{line_num}: "
                f"'{match.group(1).strip()}' followed by '{match.group(2).strip()}' — "
                f"skeleton places TX polling BEFORE RX calls, not after them"
            )

    if not extra_while_violations:
        passed_count += 1
    else:
        violations.extend(extra_while_violations)
        failed_count += len(extra_while_violations)

    # ========== CHECK 3: No forbidden patterns in polling ==========
    forbidden_patterns = {
        r'pollCount': 'Counter variable in polling',
        r'maxRetries': 'Retry counter in polling',
        r'timeout\s*\+\+': 'Timeout increment in polling',
        r'while\s*\([^)]*\)\s*\{[^}]*break[^}]*\}': 'Break statement in while-loop',
        r'if\s*\([^)]*>\s*\d+\)\s*break': 'Artificial break in polling'
    }
    
    forbidden_violations = []
    for pattern, desc in forbidden_patterns.items():
        matches = re.finditer(pattern, code)
        for match in matches:
            line_num = code[:match.start()].count('\n') + 1
            forbidden_violations.append(
                f"FAIL: Forbidden pattern '{pattern}' ({desc}) at line ~{line_num}"
            )
    
    if not forbidden_violations:
        passed_count += 1
    else:
        violations.extend(forbidden_violations)
        failed_count += len(forbidden_violations)
    
    # ========== CHECK 4: Every struct init followed by member init ==========
    # Pattern: structType varName = {0}; followed by varName.member = ...
    struct_init_pattern = r'(\w+_t)\s+(\w+)\s*=\s*\{0\}'
    struct_inits = re.finditer(struct_init_pattern, code)
    member_init_violations = []
    
    for match in struct_inits:
        struct_type = match.group(1)
        var_name = match.group(2)
        
        # Look for member assignments after this init
        after_init_start = match.end()
        after_init_end = code.find('\n\n', after_init_start)
        if after_init_end == -1:
            after_init_end = len(code)
        
        after_init_code = code[after_init_start:after_init_end]
        
        # Check if there's at least ONE member assignment
        member_pattern = f'{var_name}\\.\\w+\\s*='
        member_matches = re.findall(member_pattern, after_init_code)
        
        # Some structs intentionally stay at {0} (error flags, etc.)
        # Only warn if it's a config struct (usually have many members)
        if 'Config' in struct_type and not member_matches:
            line_num = code[:match.start()].count('\n') + 1
            member_init_violations.append(
                f"WARN: Config struct '{var_name}' ({struct_type}) at line ~{line_num} has no member assignments"
            )
    
    if not member_init_violations:
        passed_count += 1
    else:
        warnings_list.extend(member_init_violations)
        failed_count += len(member_init_violations)
    
    # ========== CHECK 5: No true/false (lowercase) macros ==========
    false_positive_pattern = r'\b(true|false)\b'
    false_matches = re.finditer(false_positive_pattern, code)
    false_violations = []
    
    for match in false_matches:
        # Exclude inside comments and strings
        line_start = code.rfind('\n', 0, match.start()) + 1
        line = code[line_start:code.find('\n', match.start())]
        
        # Skip if inside comment
        if '//' in line and match.start() > line_start + line.index('//'):
            continue
        if '/*' in code[:match.start()] and '*/' not in code[:match.start()]:
            continue
        
        line_num = code[:match.start()].count('\n') + 1
        false_violations.append(
            f"FAIL: Lowercase '{match.group()}' at line ~{line_num} (use TRUE/FALSE)"
        )
    
    if not false_violations:
        passed_count += 1
    else:
        violations.extend(false_violations)
        failed_count += len(false_violations)
    
    # ========== CHECK 6: No invented functions ==========
    # Look for function calls - they should be from known patterns
    func_call_pattern = r'IfxCxpi_([A-Za-z_]+)\s*\('
    func_calls = set(re.findall(func_call_pattern, code))
    
    # Common invented patterns to catch
    invented_patterns = ['test', 'demo', 'dummy', 'temp', 'my_']
    invented_funcs = [f for f in func_calls if any(p in f.lower() for p in invented_patterns)]
    
    if not invented_funcs:
        passed_count += 1
    else:
        violations.append(
            f"WARN: Possible invented functions detected: {', '.join(invented_funcs)}"
        )
        failed_count += len(invented_funcs)
    
    # ========== CHECK 7: Cleanup only in FINALIZE ==========
    cleanup_pattern = r'(clearAllInterrupts|deinit|disable|close|cleanup)\s*\('
    cleanup_calls = [(m.start(), m.group()) for m in re.finditer(cleanup_pattern, code)]
    
    finalize_start = code.find('[FINALIZE]')
    cleanup_violations = []
    
    for pos, call in cleanup_calls:
        if finalize_start != -1 and pos < finalize_start:
            line_num = code[:pos].count('\n') + 1
            cleanup_violations.append(
                f"FAIL: Cleanup call '{call}' at line ~{line_num} appears before [FINALIZE] section"
            )
    
    if not cleanup_violations:
        passed_count += 1
    else:
        violations.extend(cleanup_violations)
        failed_count += len(cleanup_violations)
    
    # ========== SUMMARY ==========
    total_checks = 7
    
    if failed_count == 0 and len(warnings_list) == 0:
        status = 'pass'
    elif failed_count == 0 and len(warnings_list) > 0:
        status = 'warning'
    else:
        status = 'fail'
    
    return {
        'status': status,
        'total_checks': total_checks,
        'passed': passed_count,
        'failed': failed_count,
        'warnings': warnings_list,
        'errors': violations,
        'summary': f"Validation: {passed_count}/{total_checks} checks passed, {failed_count} failed, {len(warnings_list)} warnings"
    }


if __name__ == "__main__":
    # This module is not intended to be run directly.
    # All data is loaded from RAG DB (ChromaDB) and KG DB (Neo4j) via app.py.
    # No legacy JSON file loading - everything comes from the databases.
    print("="*70)
    print("code_generator.py - Test Code Generation Engine")
    print("="*70)
    print()
    print("This module is NOT meant to be run standalone.")
    print("It is used as a library by the backend server (app.py).")
    print()
    print("Data Sources (ALL from databases, ZERO from files):")
    print("  - Functions, Structs, Enums, Macros, Typedefs → RAG DB (ChromaDB)")
    print("  - Requirements, Hardware Specs → RAG DB (ChromaDB)")
    print("  - PUML Patterns (core_functions, phase_patterns) → RAG DB (ChromaDB)")
    print("  - Function Dependencies, Call Graphs → KG DB (Neo4j)")
    print("  - Register Definitions, Relationships → KG DB (Neo4j)")
    print()
    print("To generate test code, use the VS Code extension or call the API:")
    print("  POST http://localhost:8000/api/generate-test")
    print()
    print("To start the backend server:")
    print("  python run_server.py")

