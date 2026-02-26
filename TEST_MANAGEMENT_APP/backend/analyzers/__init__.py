"""
Analyzers package - Extracts patterns and call relationships from RAG+KG database

Analysis roles:
- PUMLPatternAnalyzer: Fetches pre-computed pattern library from RAG (core_functions, phase_patterns)
- SourceCodeAnalyzer: Extracts call graph from KG (CALLS_INTERNALLY, HAS_CASE, DEPENDS_ON)

Usage:
    from .puml_analyzer import PUMLPatternAnalyzer
    from .source_analyzer import SourceCodeAnalyzer
    
    # PUML analyzer needs RAG+KG for pattern library
    puml_analyzer = PUMLPatternAnalyzer(rag_client, kg_client, cache)
    patterns = puml_analyzer.analyze("CAN_Init", "cxpi")
    
    # Source analyzer needs only KG for call graph extraction
    source_analyzer = SourceCodeAnalyzer(kg_client, cache)
    call_graph = source_analyzer.analyze_module("cxpi")
"""

from .puml_analyzer import PUMLPatternAnalyzer
from .source_analyzer import SourceCodeAnalyzer

__all__ = ['PUMLPatternAnalyzer', 'SourceCodeAnalyzer']
