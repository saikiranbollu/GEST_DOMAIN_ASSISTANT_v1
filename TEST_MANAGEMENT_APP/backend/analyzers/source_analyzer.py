#!/usr/bin/env python3
"""
Source Code Analyzer - Extracts INTERNAL CALL RELATIONSHIPS from KG database

FOCUSED PURPOSE (v2.0 - OPTIMIZED):
This analyzer has ONE job: Extract function call relationships to prevent duplicate calls in tests.

PRIMARY GOAL:
- If function A internally calls function B, don't call B again in test code
- Extract CALLS_INTERNALLY relationships (which function calls which, with order & line number)
- Extract HAS_CASE relationships (dispatcher functions with switch cases)

WHAT THIS DOES:
1. Query KG for CALLS_INTERNALLY edges (function call graph with order/line metadata)
2. Query KG for HAS_CASE + case-specific CALLS_INTERNALLY (dispatcher analysis)
3. Query KG for DEPENDS_ON relationships (optional dependency info)

WHAT THIS DOES NOT DO (fetched elsewhere in pipeline):
❌ Query RAG for function signatures (fetched in main flow via top-10 RAG queries)
❌ Query RAG for structs/enums/typedefs (fetched in main flow via top-10 RAG queries)
❌ Parse source files directly (all data pre-extracted during ingestion)
❌ Assess complexity or extract parameters (not needed for call analysis)

RATIONALE:
- Avoid duplication: Functions/structs/enums already fetched by RAG in main test generation flow
- Focus on core purpose: Only extract what's needed to prevent duplicate internal calls
- Performance: Minimal KG queries (2-3 Cypher queries vs 6+ RAG+KG queries before)
"""

from typing import Dict, Any, List, Optional
from collections import defaultdict


class SourceCodeAnalyzer:
    """
    Lightweight analyzer focused on extracting internal call relationships
    
    PURPOSE: Prevent duplicate function calls in generated test code
    
    This analyzer queries KG for:
    1. CALLS_INTERNALLY: Which functions call which internally (order, line number)
    2. HAS_CASE: Dispatcher functions with switch cases and their case-specific calls
    3. DEPENDS_ON: Function dependencies (optional)
    
    This analyzer does NOT query RAG for functions/structs/enums
    (those are fetched separately in the main test generation flow).
    """
    
    def __init__(self, kg_client, cache=None):
        """Initialize analyzer with KG client only
        
        Args:
            kg_client: KGClient instance (Neo4j connection) - REQUIRED
            cache: Optional HybridCache for caching call graph analysis
        
        Note: rag_client removed - not needed for call relationship extraction
        
        Example:
            analyzer = SourceCodeAnalyzer(kg_client, cache)
            call_graph = analyzer.analyze_module("cxpi")
        """
        self.kg_client = kg_client
        self.cache = cache
        self.module = None
        
    def analyze_module(self, module: str) -> Dict[str, Any]:
        """Extract ONLY call graph and dependencies for a module
        
        OPTIMIZED & FOCUSED: Returns only what's needed to prevent duplicate internal calls
        
        Args:
            module: Module name (e.g., 'cxpi', 'lin', 'can')
            
        Returns:
            {
                'module': 'cxpi',
                'function_calls': {
                    'func1': [
                        {'function': 'internal_func', 'order': 0, 'line': 326},
                        {'function': 'another_func', 'order': 1, 'line': 450}
                    ],
                    ...
                },
                'dependencies': {
                    'func1': ['dep1', 'dep2'],
                    ...
                }
            }
            
        Note: Functions/structs/enums are NOT included here.
              They are fetched separately via RAG top-10 queries in the main flow.
        """
        self.module = module
        
        # Check cache
        cache_key = f"call_graph_{module}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                print(f"[SOURCE-ANALYZER] ✓ Loaded call graph from cache for module '{module}'")
                return cached
        
        try:
            analysis = {
                'module': module,
                'function_calls': self._analyze_function_calls(),   # CALLS_INTERNALLY from KG
                'dependencies': self._analyze_dependencies(),       # DEPENDS_ON from KG
            }
            
            print(f"[SOURCE-ANALYZER] ✓ Call graph analysis complete for module '{module}'")
            print(f"                  Functions with internal calls: {len(analysis['function_calls'])}")
            print(f"                  Functions with dependencies: {len(analysis['dependencies'])}")
            
            # Cache the result
            if self.cache:
                self.cache.set(cache_key, analysis)
            
            return analysis
            
        except Exception as e:
            print(f"[SOURCE-ANALYZER] Error analyzing module {module}: {e}")
            return self._empty_analysis(module)
    
    def analyze_selected_functions(self, function_names: List[str]) -> Dict[str, Any]:
        """Analyze ONLY the selected functions' internal calls (OPTIMIZED FOR POST-SELECTION PHASE)
        
        CRITICAL FOR PIPELINE OPTIMIZATION:
        This method is called AFTER function selection (post-RAG/KG queries) to analyze
        only the relevant functions, avoiding the waste of analyzing 1000+ functions upfront.
        
        Args:
            function_names: List of function names to analyze (e.g., ['IfxCxpi_initChannel', 'IfxCxpi_setOperation'])
            
        Returns:
            {
                'module': 'cxpi',
                'function_calls': {
                    'IfxCxpi_initChannel': [
                        {'function': 'clearAllInterrupts', 'order': 0, 'line': 326},
                        {'function': 'setBaudRate', 'order': 1, 'line': 2383}
                    ]
                },
                'function_details': {
                    'IfxCxpi_initChannel': {
                        'name': 'IfxCxpi_initChannel',
                        'has_cases': False,
                        'calls_internally': [...]
                    },
                    'IfxCxpi_setOperation': {
                        'name': 'IfxCxpi_setOperation',
                        'has_cases': True,
                        'case_field': 'action',
                        'cases': {...}
                    }
                },
                'dependencies': {
                    'IfxCxpi_initChannel': ['IfxCxpi_preinit'],
                    ...
                }
            }
        """
        cache_key = f"selected_calls_{','.join(sorted(function_names))}_{self.module}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                print(f"[SOURCE-ANALYZER] ✓ Loaded selected functions analysis from cache ({len(function_names)} functions)")
                return cached
        
        try:
            print(f"[SOURCE-ANALYZER] Analyzing {len(function_names)} selected functions...")
            
            # Extract call information for each selected function
            function_calls = {}
            function_details = {}
            dependencies = {}
            
            for func_name in function_names:
                try:
                    # Analyze this specific function
                    func_analysis = self.analyze_function(func_name)
                    function_details[func_name] = func_analysis
                    
                    # Extract call information (for simple access)
                    if func_analysis.get('has_cases'):
                        # For dispatcher functions, extract all calls from all cases
                        all_calls = []
                        for case_name, case_data in func_analysis.get('cases', {}).items():
                            all_calls.extend(case_data.get('calls_internally', []))
                        if all_calls:
                            function_calls[func_name] = all_calls
                    else:
                        # Regular function, direct calls
                        calls = func_analysis.get('calls_internally', [])
                        if calls:
                            function_calls[func_name] = calls
                    
                    # Get dependencies for this function
                    func_deps = self._get_function_dependencies(func_name)
                    if func_deps:
                        dependencies[func_name] = func_deps
                
                except Exception as e:
                    print(f"[SOURCE-ANALYZER] ⚠ Error analyzing function {func_name}: {e}")
                    continue
            
            analysis = {
                'module': self.module,
                'function_calls': function_calls,
                'function_details': function_details,
                'dependencies': dependencies
            }
            
            print(f"[SOURCE-ANALYZER] ✓ Selected functions analysis complete")
            print(f"                  Functions analyzed: {len(function_details)}")
            print(f"                  Functions with internal calls: {len(function_calls)}")
            print(f"                  Functions with dependencies: {len(dependencies)}")
            
            # Cache the result
            if self.cache:
                self.cache.set(cache_key, analysis)
            
            return analysis
        
        except Exception as e:
            print(f"[SOURCE-ANALYZER] Error analyzing selected functions: {e}")
            return {
                'module': self.module,
                'function_calls': {},
                'function_details': {},
                'dependencies': {}
            }
    
    def analyze_function(self, func_name: str) -> Dict[str, Any]:
        """Analyze specific function's internal calls and case structure
        
        Handles both regular functions and dispatcher functions with switch cases.
        
        Args:
            func_name: Function name (e.g., 'IfxCxpi_initChannel' or 'IfxCxpi_setOperation')
            
        Returns:
            Regular function:
            {
                'name': 'IfxCxpi_initChannel',
                'has_cases': False,
                'calls_internally': [
                    {'function': 'clearAllInterrupts', 'order': 0, 'line': 326},
                    {'function': 'setBaudRate', 'order': 1, 'line': 2383}
                ]
            }
            
            Dispatcher function (with HAS_CASE):
            {
                'name': 'IfxCxpi_setOperation',
                'has_cases': True,
                'case_field': 'action',
                'cases': {
                    'IfxCxpi_TxRxOps_sendHeaderOnly': {
                        'case_value': '0x01',
                        'calls_internally': [
                            {'function': 'sendHeader', 'order': 0, 'line': 450}
                        ]
                    },
                    'IfxCxpi_TxRxOps_sendHeaderSendResponse': {
                        'case_value': '0x02',
                        'calls_internally': [
                            {'function': 'sendHeader', 'order': 0, 'line': 460},
                            {'function': 'receiveResponse', 'order': 1, 'line': 470}
                        ]
                    }
                }
            }
        """
        cache_key = f"func_calls_{func_name}_{self.module}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        try:
            # Get case information (HAS_CASE + case-specific CALLS_INTERNALLY)
            case_info = self._get_function_cases_and_calls(func_name)
            
            func_analysis = {
                'name': func_name,
                'has_cases': case_info.get('has_cases', False),
            }
            
            # Add case or direct call information
            if case_info.get('has_cases'):
                func_analysis['case_field'] = case_info.get('case_field')
                func_analysis['cases'] = case_info.get('cases', {})
            else:
                func_analysis['calls_internally'] = case_info.get('calls_internally', [])
            
            if self.cache:
                self.cache.set(cache_key, func_analysis)
            
            return func_analysis
        except Exception as e:
            print(f"[SOURCE-ANALYZER] Error analyzing function {func_name}: {e}")
            return self._empty_function_analysis(func_name)
    
    # Implementation methods - Query KG only for call relationships
    
    def _analyze_function_calls(self) -> Dict[str, List[Dict]]:
        """Extract CALLS_INTERNALLY relationships from KG
        
        Returns function call information with order and line numbers from source code.
        Structure: {
            'func_name': [
                {'function': 'called_func', 'order': 0, 'line': 326},
                {'function': 'called_func2', 'order': 1, 'line': 2383}
            ]
        }
        """
        try:
            call_graph = defaultdict(list)
            
            # Query KG for CALLS_INTERNALLY relationships (actual source code calls with order & line)
            calls = self.kg_client.query(
                "MATCH (f1:Function)-[r:CALLS_INTERNALLY]->(f2:Function) RETURN f1.name, f2.name, r.order, r.line"
            )
            
            for call_info in calls:
                caller = call_info.get('f1.name') if isinstance(call_info, dict) else (call_info[0] if isinstance(call_info, (list, tuple)) else None)
                callee = call_info.get('f2.name') if isinstance(call_info, dict) else (call_info[1] if isinstance(call_info, (list, tuple)) and len(call_info) > 1 else None)
                order = call_info.get('r.order') if isinstance(call_info, dict) else (call_info[2] if isinstance(call_info, (list, tuple)) and len(call_info) > 2 else None)
                line = call_info.get('r.line') if isinstance(call_info, dict) else (call_info[3] if isinstance(call_info, (list, tuple)) and len(call_info) > 3 else None)
                
                if caller and callee:
                    call_entry = {'function': callee}
                    if order is not None:
                        call_entry['order'] = order
                    if line is not None:
                        call_entry['line'] = line
                    call_graph[caller].append(call_entry)
            
            return dict(call_graph)
        except Exception as e:
            print(f"[SOURCE-ANALYZER] Error analyzing function calls: {e}")
            return {}
    
    def _get_function_cases_and_calls(self, func_name: str) -> Dict[str, Any]:
        """Get case information and case-specific CALLS_INTERNALLY for dispatcher functions
        
        For functions with HAS_CASE relationship:
        - Extract all case variants (EnumValue nodes via HAS_CASE)
        - For each case, get its CALLS_INTERNALLY relationships
        - Return: {
            'has_cases': True,
            'case_field': 'action',  # the switch parameter name
            'cases': {
                'IfxCxpi_TxRxOps_sendHeaderOnly': {
                    'case_value': '0x01',
                    'calls_internally': [
                        {'function': 'sendHeader', 'order': 0},
                        {'function': 'getStatus', 'order': 1}
                    ]
                },
                'IfxCxpi_TxRxOps_sendHeaderSendResponse': {
                    'case_value': '0x02',
                    'calls_internally': [...]
                }
            }
        }
        
        For functions without HAS_CASE:
        - Return: {'has_cases': False, 'calls_internally': [...]}
        """
        try:
            # Check if function has HAS_CASE relationship
            cases_result = self.kg_client.query(
                f"MATCH (f:Function {{name: '{func_name}'}})-[r:HAS_CASE]->(c:EnumValue) RETURN c.name, c.value"
            )
            
            if not cases_result or len(cases_result) == 0:
                # No HAS_CASE - direct function, return direct CALLS_INTERNALLY
                calls = self._get_function_calls(func_name)
                return {
                    'has_cases': False,
                    'calls_internally': calls.get(func_name, [])
                }
            
            # Function has cases - extract case-specific calls
            cases_dict = {}
            
            for case_info in cases_result:
                case_name = case_info.get('c.name') if isinstance(case_info, dict) else (case_info[0] if isinstance(case_info, (list, tuple)) else None)
                case_value = case_info.get('c.value') if isinstance(case_info, dict) else (case_info[1] if isinstance(case_info, (list, tuple)) and len(case_info) > 1 else None)
                
                if case_name:
                    # Get CALLS_INTERNALLY for this specific case
                    case_calls = self.kg_client.query(
                        f"MATCH (c:EnumValue {{name: '{case_name}'}})-[r:CALLS_INTERNALLY]->(f:Function) RETURN f.name, r.order, r.line"
                    )
                    
                    calls_list = []
                    for call_info in case_calls:
                        called_func = call_info.get('f.name') if isinstance(call_info, dict) else (call_info[0] if isinstance(call_info, (list, tuple)) else None)
                        order = call_info.get('r.order') if isinstance(call_info, dict) else (call_info[1] if isinstance(call_info, (list, tuple)) and len(call_info) > 1 else None)
                        line = call_info.get('r.line') if isinstance(call_info, dict) else (call_info[2] if isinstance(call_info, (list, tuple)) and len(call_info) > 2 else None)
                        
                        if called_func:
                            call_entry = {'function': called_func}
                            if order is not None:
                                call_entry['order'] = order
                            if line is not None:
                                call_entry['line'] = line
                            calls_list.append(call_entry)
                    
                    cases_dict[case_name] = {
                        'case_value': case_value,
                        'calls_internally': calls_list
                    }
            
            return {
                'has_cases': True,
                'case_field': None,
                'cases': cases_dict
            }
        
        except Exception as e:
            print(f"[SOURCE-ANALYZER] Error analyzing function cases: {e}")
            return {'has_cases': False, 'calls_internally': []}
    
    def _analyze_dependencies(self) -> Dict[str, List[str]]:
        """Extract DEPENDS_ON relationships from KG
        
        Returns dependencies between functions (e.g., initialization dependencies,
        required setup functions, etc.)
        """
        try:
            dependencies = defaultdict(list)
            
            # Query KG for DEPENDS_ON relationships
            deps = self.kg_client.query(
                "MATCH (f1:Function)-[:DEPENDS_ON]->(f2:Function) RETURN f1.name, f2.name"
            )
            
            for dep_pair in deps:
                func = dep_pair.get('f1.name') if isinstance(dep_pair, dict) else (dep_pair[0] if isinstance(dep_pair, (list, tuple)) else None)
                dep = dep_pair.get('f2.name') if isinstance(dep_pair, dict) else (dep_pair[1] if isinstance(dep_pair, (list, tuple)) else None)
                if func and dep:
                    dependencies[func].append(dep)
            
            return dict(dependencies)
        except Exception as e:
            print(f"[SOURCE-ANALYZER] Error analyzing dependencies: {e}")
            return {}
    
    # Helper methods for KG call relationship queries
    
    def _get_function_calls(self, func_name: str) -> Dict[str, List[Dict]]:
        """Get functions called by this function via CALLS_INTERNALLY
        
        Returns: {'func_name': [{'function': 'callee', 'order': 0, 'line': 326}, ...]}
        """
        try:
            calls = self.kg_client.query(
                f"MATCH (f:Function {{name: '{func_name}'}})-[r:CALLS_INTERNALLY]->(c:Function) RETURN c.name, r.order, r.line"
            )
            calls_list = []
            for call_info in calls:
                callee = call_info.get('c.name') if isinstance(call_info, dict) else (call_info[0] if isinstance(call_info, (list, tuple)) else None)
                order = call_info.get('r.order') if isinstance(call_info, dict) else (call_info[1] if isinstance(call_info, (list, tuple)) and len(call_info) > 1 else None)
                line = call_info.get('r.line') if isinstance(call_info, dict) else (call_info[2] if isinstance(call_info, (list, tuple)) and len(call_info) > 2 else None)
                
                if callee:
                    call_entry = {'function': callee}
                    if order is not None:
                        call_entry['order'] = order
                    if line is not None:
                        call_entry['line'] = line
                    calls_list.append(call_entry)
            
            return {func_name: calls_list}
        except:
            return {func_name: []}
    
    def _get_function_callers(self, func_name: str) -> List[str]:
        """Get functions that call this function (reverse lookup)"""
        try:
            callers = self.kg_client.query(
                f"MATCH (c:Function)-[:CALLS_INTERNALLY]->(f:Function {{name: '{func_name}'}}) RETURN c.name"
            )
            return [c.get('c.name') if isinstance(c, dict) else (c[0] if isinstance(c, (list, tuple)) else None) for c in callers if c]
        except:
            return []
    
    def _get_function_dependencies(self, func_name: str) -> List[str]:
        """Get functions that this function depends on (DEPENDS_ON relationships)"""
        try:
            deps = self.kg_client.query(
                f"MATCH (f:Function {{name: '{func_name}'}})-[:DEPENDS_ON]->(d:Function) RETURN d.name"
            )
            return [d.get('d.name') if isinstance(d, dict) else (d[0] if isinstance(d, (list, tuple)) else None) for d in deps if d]
        except:
            return []
    
    # Empty structures for error cases
    
    def _empty_analysis(self, module: str) -> Dict[str, Any]:
        """Return empty call graph structure"""
        return {
            'module': module,
            'function_calls': {},
            'dependencies': {}
        }
    
    def _empty_function_analysis(self, func_name: str) -> Dict[str, Any]:
        """Return empty function call analysis"""
        return {
            'name': func_name,
            'has_cases': False,
            'calls_internally': []
        }
