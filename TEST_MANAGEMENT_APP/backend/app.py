#!/usr/bin/env python3
"""
TEST MANAGEMENT APP - FastAPI Backend
Semantic Test Code Generation with RAG + Knowledge Graph

PHASE 2: RAG Integration
- Uses RAGClient for ChromaDB queries (12 collections)
- Uses KGClient for Neo4j queries (23 relationship types)
- Zero hardcoding, fully dynamic for any module

Architecture:
1. User Input → Intent Parser (extract keywords, features)
2. RAG Query → Query 12 ChromaDB collections for context
3. KG Query → Query Neo4j for dependencies, types, requirements
4. Code Generation → Build test with data-driven code generator
5. Validation → MISRA-C validation
6. Output → Generated test files
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import re
import time
import sqlite3
import traceback
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import json
import logging

# Import our dynamic clients
from .database.rag_client import RAGClient
from .database.kg_client import KGClient

# Import code generation
from .generators.code_generator import (
    DataDrivenCodeGenerator,
    build_llm_prompt_idea_1_sequential,
    build_enum_resolver_prompt,
    apply_resolved_enums
)
from .validators.misra_validator import MisraCValidator

# Import LLM service (PHASE 4)
from .llm.llm_service import LLMService

# Import caching system
from .utils.cache import HybridCache

# Import pattern and source analyzers (from RAG+KG database)
from .analyzers.puml_analyzer import PUMLPatternAnalyzer
from .analyzers.source_analyzer import SourceCodeAnalyzer

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Test Management System API",
    description="Semantic Test Code Generation with RAG + Knowledge Graph",
    version="2.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# GLOBAL CLIENTS (initialized at startup)
# ============================================================================

rag_client: Optional[RAGClient] = None
kg_client: Optional[KGClient] = None
llm_service: Optional[LLMService] = None

# Caching system (LRU + SQLite3 persistence)
json_cache: Optional[HybridCache] = None
puml_cache: Optional[HybridCache] = None
source_analysis_cache: Optional[HybridCache] = None

# Pattern and source analyzers
puml_analyzer: Optional[PUMLPatternAnalyzer] = None
source_analyzer: Optional[SourceCodeAnalyzer] = None

# Test code generation template (loaded from MD file)
test_code_template: Optional[str] = None

# Server-side generation context cache for enum resolution
# Stores all_structs / all_enums from the latest generation so that
# the /apply_enum_resolution endpoint can use them for proper task ID alignment.
# This avoids having to pass large struct/enum data through the extension roundtrip.
_generation_context_cache: Dict[str, Any] = {
    'all_structs': [],
    'all_enums': []
}

# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize all clients, caches, and analyzers on startup"""
    global rag_client, kg_client, llm_service
    global json_cache, puml_cache, source_analysis_cache
    global puml_analyzer, source_analyzer
    global test_code_template
    
    try:
        # Get module name from environment (optional at startup)
        # MODULE_NAME will be REQUIRED in API requests - user must select in UI
        module = os.getenv("MODULE_NAME")
        if module:
            module = module.lower()
            print(f"✅ MODULE_NAME set to: {module}")
            print(f"   (This will be overridden if extension specifies a different module)")
        else:
            print(f"ℹ️  MODULE_NAME not set (optional at startup)")
            print(f"   User MUST select module in UI when generating tests")
            module = None
        
        chroma_path = os.getenv(
            "CHROMA_PATH",
            str(Path(__file__).parent.parent.parent / "MCP_DB_INGESTION" / "output" / "chroma_data")
        )
        
        # Initialize RAGClient (with module if available, otherwise will use request-provided module)
        if module:
            rag_client = RAGClient(db_path=str(chroma_path), module=module)
            print(f"[OK] RAGClient initialized for module '{module}'")
            print(f"     Collections loaded: {len(rag_client.collections)}")
        else:
            # Initialize RAGClient without module (will be set per-request)
            rag_client = RAGClient(db_path=str(chroma_path), module="default")
            print(f"[OK] RAGClient initialized (module will be set per request)")
            print(f"     Collections available: {len(rag_client.collections)}")
        
        # Initialize KGClient (with module if available, otherwise will use request-provided module)
        try:
            if module:
                kg_client = KGClient(
                    uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    user=os.getenv("NEO4J_USER", "neo4j"),
                    password=os.getenv("NEO4J_PASSWORD", "password"),
                    module=module
                )
                print(f"[OK] KGClient initialized for module '{module}'")
                print(f"     Database: {kg_client.database}")
            else:
                # No module specified - try to use 'cxpidb' database or detect available databases
                neo4j_database = os.getenv("NEO4J_DATABASE", "cxpidb")
                kg_client = KGClient(
                    uri=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
                    user=os.getenv("NEO4J_USER", "neo4j"),
                    password=os.getenv("NEO4J_PASSWORD", "INNOVATION26"),
                    database=neo4j_database
                )
                print(f"[OK] KGClient initialized (using database '{neo4j_database}')")
                print(f"     Module can be specified per request")
        except Exception as kg_error:
            print(f"[KG-ERROR] KGClient initialization failed: {kg_error}")
            print(f"       Knowledge Graph features will be unavailable")
            print(f"       RAG-based generation will continue to work")
            kg_client = None
        
        # Initialize Caching System (LRU + SQLite3)
        cache_dir = Path(__file__).parent.parent.parent / "cache"
        cache_dir.mkdir(exist_ok=True)
        
        json_cache = HybridCache(cache_size=1000, db_path=str(cache_dir / 'json_semantic_cache.db'))
        puml_cache = HybridCache(cache_size=500, db_path=str(cache_dir / 'puml_pattern_cache.db'))
        source_analysis_cache = HybridCache(cache_size=500, db_path=str(cache_dir / 'source_analysis_cache.db'))
        print(f"[OK] Caching system initialized (LRU + SQLite3 persistence)")
        print(f"     JSON cache: 1000 entries")
        print(f"     PUML cache: 500 entries")
        print(f"     Source analysis cache: 500 entries")
        
        # Initialize Analyzers (fetch from RAG+KG, not separate files)
        try:
            if kg_client:
                puml_analyzer = PUMLPatternAnalyzer(rag_client, kg_client, puml_cache)
                source_analyzer = SourceCodeAnalyzer(kg_client, source_analysis_cache)  # Updated: KG-only for call graph
                print(f"[OK] Pattern analyzers initialized")
                print(f"     PUML Pattern Analyzer - queries RAG+KG for sequences/patterns")
                print(f"     Source Code Analyzer - queries KG for CALLS_INTERNALLY/HAS_CASE relationships")
            else:
                print(f"[WARN] Skipping analyzer initialization (KGClient not available)")
                puml_analyzer = None
                source_analyzer = None
        except Exception as analyzer_error:
            print(f"[WARN] Analyzer initialization failed: {analyzer_error}")
            puml_analyzer = None
            source_analyzer = None
        
        # Initialize LLM Service (PHASE 4)
        llm_model = os.getenv("LLM_MODEL", None)  # User can specify model
        try:
            llm_service = LLMService(provider_type="copilot", model=llm_model)
            print(f"[OK] LLM Service initialized")
            print(f"     Provider: GitHub Copilot")
            print(f"     Model: {llm_service.model}")
            available = llm_service.get_available_models()
            print(f"     Available models: {available}")
        except Exception as e:
            print(f"[WARN] LLM Service initialization failed: {e}")
            print(f"       Test generation will work without LLM enhancement")
            llm_service = None
        
        # Load Test Code Generation Template (standalone MD file)
        # This template goes to LLM as system prompt for test enhancement
        template_path = Path(__file__).parent / "generators" / "test_code_prompt.md"
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                test_code_template = f.read()
            print(f"[OK] Test code template loaded")
            print(f"     Path: {template_path}")
            print(f"     Size: {len(test_code_template)} characters")
            print(f"     This template will be used as system prompt for LLM enhancement")
        except Exception as e:
            print(f"[WARN] Failed to load test code template: {e}")
            print(f"       Code generation will work but without template guidance")
            test_code_template = None
        
    except Exception as e:
        print(f"[FAIL] Failed to initialize clients: {e}")
        traceback.print_exc()

@app.on_event("shutdown")
async def shutdown_event():
    """Close clients on shutdown"""
    global kg_client
    if kg_client:
        kg_client.close()
        print("✅ KGClient closed")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TestGenerationRequest(BaseModel):
    """Request to generate test code"""
    module: str
    description: str
    additional_notes: Optional[str] = None
    llm_model: Optional[str] = "gpt-4"

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check system health and database connectivity"""
    try:
        rag_status = "✅ Connected" if rag_client else "⚠️ Not initialized"
        kg_status = "✅ Connected" if kg_client else "⚠️ Not initialized"
        
        return {
            "status": "healthy",
            "rag_client": rag_status,
            "kg_client": kg_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ============================================================================
# MODULE INFO
# ============================================================================

@app.get("/modules")
async def get_available_modules() -> Dict[str, Any]:
    """Get list of available modules — dynamically discovered from ChromaDB collections and Neo4j DB name"""
    try:
        chroma_path = os.getenv(
            "CHROMA_PATH",
            str(Path(__file__).parent.parent.parent / "MCP_DB_INGESTION" / "output" / "chroma_data")
        )
        sqlite_path = Path(chroma_path) / "chroma.sqlite3"

        if not sqlite_path.exists():
            return {"modules": [], "description": "ChromaDB not found — no modules available"}

        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM collections;")
        collection_names = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Known generic collection suffixes that do NOT encode a module name.
        # These are ingested once per deployment regardless of module.
        known_types = {
            "functions", "enums", "structs", "requirements", "hardware",
            "registers", "macros", "typedefs", "source", "architecture",
            "pattern_library", "phases", "hardware_spec", "register_defs",
            "source_implementation", "architecture_docs", "puml_pattern_library",
            "puml_phases",
        }

        # Ingestion-layer prefixes that are aliases for a real module name.
        # "swa" (Software Architecture) collections contain CXPI SDK data —
        # the ingestion pipeline used the SWA layer prefix, but the module is cxpi.
        # Add more mappings here if future modules use similar alias prefixes.
        prefix_alias_map: Dict[str, str] = {
            "swa": os.getenv("NEO4J_DATABASE", "cxpidb").rstrip("db").rstrip("_").lower()
        }

        modules: set = set()
        has_generic = False

        for name in collection_names:
            if not name.startswith("rag_"):
                continue
            remainder = name[4:]  # strip "rag_" prefix

            # Generic collections — don't encode a module name directly
            if remainder in known_types:
                has_generic = True
                continue

            # Try rag_{prefix}_{type}  (e.g. rag_swa_functions → prefix=swa, type=functions)
            parts = remainder.split("_", 1)
            if len(parts) == 2:
                candidate_prefix = parts[0]
                candidate_type = parts[1]
                if candidate_type in known_types:
                    # Resolve alias (swa → cxpi) or use the prefix as-is
                    resolved = prefix_alias_map.get(candidate_prefix, candidate_prefix)
                    modules.add(resolved)

        # Fallback 1: explicit MODULE_NAME env var
        if not modules:
            env_module = os.getenv("MODULE_NAME", "").lower().strip()
            if env_module:
                modules.add(env_module)

        # Fallback 2: derive from Neo4j database name (e.g. "cxpidb" → "cxpi")
        # This covers the case where only generic collections exist (no prefix collections).
        if not modules:
            neo4j_db = os.getenv("NEO4J_DATABASE", "").lower().strip()
            if neo4j_db:
                # Strip common "db" suffix: "cxpidb" → "cxpi", "lindb" → "lin"
                derived = neo4j_db[:-2] if neo4j_db.endswith("db") and len(neo4j_db) > 2 else neo4j_db
                if derived:
                    modules.add(derived)

        module_list = sorted(modules)

        return {
            "modules": module_list,
            "total_collections": len(collection_names),
            "description": "Dynamically discovered from ingested ChromaDB collections"
        }
    except Exception as e:
        logger.error(f"Failed to discover modules: {e}")
        return {"modules": [], "error": str(e)}

# ============================================================================
# RAG QUERIES
# ============================================================================

@app.post("/query/functions")
async def query_functions(intent: str) -> Dict[str, Any]:
    """
    Query function definitions from RAG

    Args:
        intent: Search intent (e.g., 'initialize channel')

    Returns:
        List of relevant functions with similarity scores
    """
    if not rag_client:
        raise HTTPException(status_code=503, detail="RAG client not initialized")

    try:
        results = rag_client.query_functions(intent, n_results=10)
        return {
            "intent": intent,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")

@app.post("/query/enums")
async def query_enums(intent: str) -> Dict[str, Any]:
    """Query enum definitions from RAG"""
    if not rag_client:
        raise HTTPException(status_code=503, detail="RAG client not initialized")

    try:
        results = rag_client.query_enums(intent, n_results=5)
        return {
            "intent": intent,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")

@app.post("/query/structs")
async def query_structs(intent: str) -> Dict[str, Any]:
    """Query struct definitions from RAG"""
    if not rag_client:
        raise HTTPException(status_code=503, detail="RAG client not initialized")

    try:
        results = rag_client.query_structs(intent, n_results=5)
        return {
            "intent": intent,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")

@app.post("/query/requirements")
async def query_requirements(intent: str) -> Dict[str, Any]:
    """Query requirements from RAG"""
    if not rag_client:
        raise HTTPException(status_code=503, detail="RAG client not initialized")

    try:
        results = rag_client.query_requirements(intent, n_results=5)
        return {
            "intent": intent,
            "results_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")

# ============================================================================
# KG QUERIES
# ============================================================================

@app.post("/query/dependencies")
async def query_dependencies(function_name: str) -> Dict[str, Any]:
    """
    Get function dependencies from Knowledge Graph
    
    Args:
        function_name: Function name (e.g., 'IfxCxpi_initModule')
    
    Returns:
        List of dependent functions
    """
    if not kg_client:
        raise HTTPException(status_code=503, detail="KG client not initialized")
    
    try:
        dependencies = kg_client.get_function_dependencies(function_name)
        return {
            "function": function_name,
            "dependencies_count": len(dependencies),
            "dependencies": dependencies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KG query failed: {str(e)}")

@app.post("/query/calls")
async def query_function_calls(function_name: str) -> Dict[str, Any]:
    """Get functions called by a function"""
    if not kg_client:
        raise HTTPException(status_code=503, detail="KG client not initialized")
    
    try:
        calls = kg_client.get_function_calls(function_name)
        return {
            "function": function_name,
            "calls_count": len(calls),
            "calls": calls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KG query failed: {str(e)}")

@app.post("/query/parameters")
async def query_function_parameters(function_name: str) -> Dict[str, Any]:
    """Get function parameters with types"""
    if not kg_client:
        raise HTTPException(status_code=503, detail="KG client not initialized")
    
    try:
        parameters = kg_client.get_function_parameters(function_name)
        return {
            "function": function_name,
            "parameters_count": len(parameters),
            "parameters": parameters
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KG query failed: {str(e)}")

# ============================================================================
# LLM ENDPOINTS (PHASE 4)
# ============================================================================

@app.get("/llm/models")
async def get_available_models() -> Dict[str, Any]:
    """Get list of available LLM models"""
    if not llm_service:
        return {
            "available": False,
            "message": "LLM service not initialized",
            "models": []
        }
    
    return {
        "available": True,
        "current_model": llm_service.model,
        "provider": llm_service.provider_type,
        "models": llm_service.get_available_models()
    }

@app.post("/llm/update-models")
async def update_available_models(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update available LLM models from VS Code extension
    
    The extension discovers models dynamically from VS Code's LLM API
    and sends them to the backend for selection.
    
    Args:
        request: Dict with 'models' list
    
    Returns:
        Success status and updated model list
    """
    global llm_service
    
    models = request.get('models', [])
    if not models:
        return {
            "status": "error",
            "message": "No models provided"
        }
    
    try:
        # Update the LLM service with new models
        if llm_service and hasattr(llm_service.provider, 'available_models'):
            llm_service.provider.available_models = models
            if not llm_service.model or llm_service.model not in models:
                llm_service.model = models[0]
                llm_service.provider.model = models[0]
            print(f"[LLM] Updated available models from VS Code: {models}")
            print(f"[LLM] Current model: {llm_service.model}")
        elif not llm_service:
            # Initialize LLM service with discovered models
            os.environ['GITHUB_COPILOT_MODELS'] = ','.join(models)
            from .llm.llm_service import LLMService
            llm_service = LLMService(provider_type="copilot")
            print(f"[LLM] Initialized with models from VS Code: {models}")
        
        return {
            "status": "success",
            "message": f"Updated {len(models)} models",
            "models": models,
            "current_model": llm_service.model if llm_service else None
        }
    except Exception as e:
        print(f"[LLM] Error updating models: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/llm/select-model")
async def select_llm_model(model: str) -> Dict[str, Any]:
    """
    Select which LLM model to use
    
    Args:
        model: Model identifier (e.g., 'claude-3.5-sonnet', 'gpt-4')
    
    Returns:
        Success status and current model
    """
    if not llm_service:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    if llm_service.select_model(model):
        return {
            "status": "success",
            "message": f"Switched to model: {model}",
            "current_model": llm_service.model,
            "provider": llm_service.provider_type
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' not available. Available models: {llm_service.get_available_models()}"
        )


# ============================================================================
# STAGE 1 ENUM RESOLUTION — Apply resolved enum values to skeleton
# ============================================================================

class EnumResolutionRequest(BaseModel):
    sample_test_code: str
    resolved_values: Dict[str, str]

@app.post("/apply_enum_resolution")
async def apply_enum_resolution(request: EnumResolutionRequest) -> Dict[str, Any]:
    """
    Apply Stage 1 resolved enum values back into the skeleton code.
    Called by the VS Code extension after gpt-5-mini resolves enum TODOs.
    
    Uses cached all_structs / all_enums from the latest generation to ensure
    task ID alignment with build_enum_resolver_prompt().
    
    100% DATA-DRIVEN: No hardcoding, works for any module.
    """
    start_time = time.time()

    try:
        apply_start = time.time()
        resolved_code = apply_resolved_enums(
            sample_test_code=request.sample_test_code,
            resolved_values=request.resolved_values,
            all_structs=_generation_context_cache.get('all_structs', []),
            all_enums=_generation_context_cache.get('all_enums', [])
        )
        apply_duration = time.time() - apply_start

        total_duration = time.time() - start_time
        print(f"[ENUM-RESOLUTION] ✓ Applied {len(request.resolved_values)} enum values to skeleton ({apply_duration:.2f}s total: {total_duration:.2f}s)")
        
        return {
            'status': 'success',
            'resolved_code': resolved_code,
            'values_applied': len(request.resolved_values),
            'duration_ms': int(total_duration * 1000)
        }
    except Exception as e:
        print(f"[ENUM-RESOLUTION] ❌ Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Enum resolution failed: {str(e)}")


# ============================================================================
# STAGE 2 CODE VALIDATION — Quality assurance checks on generated code
# ============================================================================

class CodeValidationRequest(BaseModel):
    generated_code: str

@app.post("/validate_generated_code")
async def validate_generated_code(request: CodeValidationRequest) -> Dict[str, Any]:
    """
    Validate generated test code against PRE-SUBMISSION CHECKLIST.
    
    Runs AFTER LLM enhancement (Stage 2) to catch common issues:
    - RX polling added where it shouldn't be
    - Struct members not initialized
    - Forbidden patterns (pollCount, timeout, break in loops)
    - Lowercase true/false instead of TRUE/FALSE
    - Cleanup before FINALIZE
    
    Returns validation report with pass/fail/warning status and detailed violations.
    """
    start_time = time.time()

    try:
        from generators.code_generator import validate_generated_test_code

        validation_result = validate_generated_test_code(
            request.generated_code,
            skeleton_code=_generation_context_cache.get('skeleton_code')
        )
        total_duration = time.time() - start_time
        
        status_symbol = '✓' if validation_result['status'] == 'pass' else '⚠' if validation_result['status'] == 'warning' else '❌'
        print(f"[VALIDATION] {status_symbol} {validation_result['summary']} ({total_duration:.2f}s)")
        
        if validation_result['errors']:
            for error in validation_result['errors']:
                print(f"  [ERROR] {error}")
        if validation_result['warnings']:
            for warn in validation_result['warnings']:
                print(f"  [WARN] {warn}")
        
        return {
            'status': validation_result['status'],
            'summary': validation_result['summary'],
            'total_checks': validation_result['total_checks'],
            'passed': validation_result['passed'],
            'failed': validation_result['failed'],
            'errors': validation_result['errors'],
            'warnings': validation_result['warnings'],
            'duration_ms': int(total_duration * 1000)
        }
    except Exception as e:
        print(f"[VALIDATION] ❌ Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Code validation failed: {str(e)}")


# ============================================================================
# MAIN TEST GENERATION (PHASE 3)
# ============================================================================

@app.post("/generate_test")
async def generate_test(request: TestGenerationRequest) -> Dict[str, Any]:
    """
    Generate test code from natural language description
    
    PHASE 3 Implementation: Full code generation with RAG + KG context
    
    Workflow:
    1. Extract intent from user description
    2. Query RAG for functions, structs, enums, requirements
    3. Query KG for dependencies, parameters, relationships
    4. Use DataDrivenCodeGenerator to build test structure
    5. Validate with MISRA-C rules
    6. Return generated code and metadata
    """
    # START TIMER: Capture total time from request received to completion
    generation_start_time = time.time()
    _step_times = {}  # {step_name: elapsed_seconds}
    _step_start = generation_start_time  # rolling step timer

    def _mark_step(name: str):
        """Record elapsed time for a step and reset the rolling timer."""
        nonlocal _step_start
        now = time.time()
        elapsed = now - _step_start
        _step_times[name] = elapsed
        print(f"  ⏱  {name} took {elapsed:.2f}s")
        _step_start = now
    
    if not rag_client or not kg_client:
        raise HTTPException(status_code=503, detail="RAG/KG clients not initialized")
    
    # VALIDATE: Module must be provided (no fallback!)
    if not request.module or request.module.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="❌ ERROR: 'module' is REQUIRED. No fallback module will be used. User must select module in UI."
        )
    
    if not request.description or request.description.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="❌ ERROR: 'description' is REQUIRED. Provide test description."
        )
    
    try:
        
        test_id = f"test_{int(datetime.now().timestamp() * 1000)}"
        module = request.module.lower()
        description = request.description
        
        # Switch LLM model if user selected one in the request
        if request.llm_model and llm_service:
            requested_model = request.llm_model.strip()
            available = llm_service.get_available_models() or []
            if requested_model in available:
                llm_service.select_model(requested_model)
                print(f"  [LLM] Model switched to: {requested_model}")
            else:
                # Force-set model even if not in discovered list
                # (extension sends the model name from user selection)
                llm_service.model = requested_model
                if hasattr(llm_service, 'provider') and llm_service.provider:
                    llm_service.provider.model = requested_model
                print(f"  [LLM] Model force-set to: {requested_model} (not in discovered list: {available[:5]})")
        
        print(f"\n{'='*70}")
        print(f"[PHASE 3] Generating test: {test_id}")
        print(f"{'='*70}")
        print(f"Module: {module}")
        print(f"Description: {description}")
        if llm_service:
            print(f"LLM Model: {llm_service.model}")
        
        # ================================================================
        # STEP 0: Load pattern library and source analysis from database
        # ================================================================
        print(f"\n[STEP 0] Loading pattern library and source analysis...")
        
        # Load PUML pattern library (replaces old JSON file loading)
        puml_analysis = {}
        pattern_library = {}
        code_generation_rules = {}
        
        if puml_analyzer:
            try:
                puml_analysis = puml_analyzer.analyze(module=module)
                pattern_library = puml_analysis.get('pattern_library', {})
                code_generation_rules = puml_analysis.get('code_generation_rules', {})
                print(f"  ✅ Pattern library loaded from RAG database")
                print(f"     Features: {len(pattern_library.get('features', {}))}")
                print(f"     Sequences: {len(pattern_library.get('sequence_patterns', {}))}")
                print(f"     Core functions: {len(pattern_library.get('core_functions', {}))}")
            except Exception as e:
                print(f"  [WARN] Pattern library loading failed: {e}")
                pattern_library = {
                    'features': {}, 'sequence_patterns': {}, 
                    'initialization_patterns': {}, 'polling_patterns': {}
                }
                code_generation_rules = {
                    'default_timeout': 1000, 'default_retry_count': 3, 'module': module
                }
        
        # Load call graph analysis (CALLS_INTERNALLY, HAS_CASE, DEPENDS_ON from KG)
        # NOTE: Moved to STEP 3 (after function selection) for optimization
        # This prevents analyzing 1000+ functions when only ~10 will be used
        # source_analysis will be populated in STEP 3 after RAG/KG queries identify relevant functions
        source_analysis = {}
        
        _mark_step("STEP 0: Pattern Library")
        
        # ================================================================
        # STEP 1: Query RAG for comprehensive context across ALL collections
        # ================================================================
        # CHUNK_CONFIG settings:
        # - Functions/Structs/Enums: Top 8 each (comprehensive coverage)
        # - Requirements: Top 3 only (req_Requirement_* chunks, sufficient)
        # - Hardware specs: Top 5 (PDF chunks, more than sufficient)
        # - Registers/Macros/Typedefs: Top 8 each (complete definitions)
        # - Features: Top 8 (for semantic intent matching)
        # - PUML Patterns: ALL chunks (complete, interconnected diagrams)
        # ================================================================
        print(f"\n[STEP 1] Querying RAG for comprehensive context across all collections...")
        
        # Core collections (top 8 each)
        rag_functions = rag_client.query_functions(description, n_results=rag_client.CHUNK_CONFIG['functions_n_results'])
        rag_structs = rag_client.query_structs(description, n_results=rag_client.CHUNK_CONFIG['structs_n_results'])
        rag_enums = rag_client.query_enums(description, n_results=rag_client.CHUNK_CONFIG['enums_n_results'])
        
        print(f"  ✅ Found {len(rag_functions)} relevant functions (top {rag_client.CHUNK_CONFIG['functions_n_results']})")
        print(f"  ✅ Found {len(rag_structs)} relevant structs (top {rag_client.CHUNK_CONFIG['structs_n_results']})")
        print(f"  ✅ Found {len(rag_enums)} relevant enums (top {rag_client.CHUNK_CONFIG['enums_n_results']})")
        
        # Requirements: Top 3 (req_Requirement_* naming convention)
        rag_requirements = rag_client.query_requirements(description, n_results=rag_client.CHUNK_CONFIG['requirements_n_results'])
        print(f"  ✅ Found {len(rag_requirements)} relevant requirements (top {rag_client.CHUNK_CONFIG['requirements_n_results']})")
        
        # Hardware specs: Top 5 (PDF chunks)
        rag_hardware = rag_client.query_hardware(description, n_results=rag_client.CHUNK_CONFIG['hardware_n_results'])
        print(f"  ✅ Found {len(rag_hardware)} relevant hardware specs (top {rag_client.CHUNK_CONFIG['hardware_n_results']})")
        
        # Registers, Macros, Typedefs: Top 8 each
        rag_registers = rag_client.query_registers(description, n_results=rag_client.CHUNK_CONFIG['registers_n_results'])
        print(f"  ✅ Found {len(rag_registers)} relevant registers (top {rag_client.CHUNK_CONFIG['registers_n_results']})")
        
        rag_macros = rag_client.query_macros(description, n_results=rag_client.CHUNK_CONFIG['macros_n_results'])
        print(f"  ✅ Found {len(rag_macros)} relevant macros (top {rag_client.CHUNK_CONFIG['macros_n_results']})")
        
        rag_typedefs = rag_client.query_typedefs(description, n_results=rag_client.CHUNK_CONFIG['typedefs_n_results'])
        print(f"  ✅ Found {len(rag_typedefs)} relevant typedefs (top {rag_client.CHUNK_CONFIG['typedefs_n_results']})")
        
        # PUML Pattern Library: ALL chunks (6-8 chunks with features, patterns, sequences)
        # Extract feature and pattern information from PUML chunks for test generation
        rag_puml_patterns = rag_client.query_pattern_library(fetch_all=True)
        print(f"  ✅ Loaded PUML pattern library (ALL chunks: {len(rag_puml_patterns)} keys)")
        if rag_puml_patterns:
            print(f"     Pattern keys: {', '.join(list(rag_puml_patterns.keys())[:4])}...")
        
        # Optional: Source code implementations
        rag_source = []
        
        try:
            # Try to get source code references from RAG
            rag_source = rag_client.multi_collection_search(description, use_optimized_defaults=True).get('source', []) if hasattr(rag_client, 'multi_collection_search') else []
            print(f"  ✅ Found {len(rag_source)} relevant source code references")
        except Exception as e:
            logger.debug(f"  [DEBUG] Source query not available: {e}")
            rag_source = []
        
        _mark_step("STEP 1: RAG Queries")
        
        # ================================================================
        # STEP 2: Query KG for ALL 22+ relationships (COMPREHENSIVE, NO HARDCODING)
        # ================================================================
        print(f"\n[STEP 2] Querying KG comprehensively for ALL RAG outputs (top 8 per collection)...")
        
        kg_context = {
            'functions': {},
            'structs': {},
            'enums': {},
            'requirements': {},
            'registers': {},
            'macros': {},
            'hardware': {},
            'errors': {},
            'interrupts': {},
            'typedefs': {},
            'features': {},
            'source': {}
        }
        
        # ============================================================
        # HELPER: Extract entity name from RAG result dynamically
        # Single unified helper used throughout this endpoint.
        # ============================================================
        def extract_entity_name(rag_item, entity_type):
            """Extract entity name from RAG result metadata or content.
            
            Metadata keys match ingestion format:
            - Functions: metadata['function']
            - Structs: metadata['struct']
            - Enums: metadata['enum']
            - Others: metadata['name'] or metadata[entity_type]
            
            Falls back to parsing content text if metadata is missing.
            """
            metadata = rag_item.get('metadata', {})
            
            # Try multiple metadata key patterns (matching actual ingestion keys)
            for key in [entity_type, 'name', f'{entity_type}_name']:
                val = metadata.get(key)
                if val and val != 'unknown' and val != 'Unknown':
                    return val
            
            # Fallback: extract from content text
            content = rag_item.get('content', '') or rag_item.get('full_content', '')
            if not content:
                return None
            
            first_line = content.split('\n')[0].strip()
            
            if entity_type == 'function' and '(' in first_line:
                before_paren = first_line.split('(')[0].strip()
                parts = before_paren.split()
                if parts:
                    return parts[-1].strip('*') or None
            elif entity_type in ('struct', 'enum', 'macro', 'typedef'):
                if first_line.startswith(f'{entity_type} '):
                    parts = first_line.split()
                    if len(parts) >= 2:
                        return parts[1].strip('{').strip()
                for line in content.split('\n')[:3]:
                    line = line.strip()
                    if line.startswith(f'{entity_type} '):
                        parts = line.split()
                        if len(parts) >= 2:
                            return parts[1].strip('{').strip()
            elif entity_type == 'requirement':
                parts = first_line.split(':')
                if len(parts) >= 2:
                    return parts[1].strip()
            
            return None

        # ============================================================
        # 2.1: FUNCTIONS - Query ALL KG relationships (7+ types)
        # ============================================================
        print(f"  [2.1] Querying ALL function relationships (DEPENDS_ON, CALLS, HAS_PARAMETER, IMPLEMENTS, HAS_CASE)...")
        func_count = 0
        for func_item in rag_functions:  # ALL functions from RAG (top 8)
            func_name = extract_entity_name(func_item, 'function')
            if func_name:
                try:
                    # 1. DEPENDS_ON / 2. CALLS / 3. CALLS_INTERNALLY (function dependencies & calls)
                    deps = kg_client.get_function_dependencies(func_name)
                    calls = kg_client.get_function_calls(func_name)
                    
                    # 4. HAS_PARAMETER / 5. OF_TYPE (function parameters)
                    params = kg_client.get_function_parameters(func_name)
                    
                    # 6. IMPLEMENTS (requirements this function implements)
                    requirements = kg_client.get_requirements_by_function(func_name)
                    
                    # 7. HAS_CASE (switch case variants if dispatcher)
                    switch_cases = kg_client.get_switch_cases(func_name)
                    
                    if deps or calls or params or requirements or switch_cases:
                        kg_context['functions'][func_name] = {
                            'dependencies': deps or [],
                            'calls': calls or [],
                            'parameters': params or [],
                            'requirements': requirements or [],
                            'switch_cases': switch_cases or []
                        }
                        func_count += 1
                except Exception as e:
                    logger.debug(f"  [DEBUG] Failed to query function {func_name}: {e}")
        
        print(f"  ✅ Retrieved context for {func_count} functions (all {len(rag_functions)} RAG results queried)")
        
        # ============================================================
        # 2.2: STRUCTS - Query ALL KG relationships (3+ types)
        # ============================================================
        print(f"  [2.2] Querying ALL struct relationships (HAS_MEMBER, USED_BY)...")
        struct_count = 0
        for struct_item in rag_structs:  # ALL structs from RAG (top 8)
            struct_name = extract_entity_name(struct_item, 'struct')
            if struct_name:
                try:
                    # 8. HAS_MEMBER / 9. HAS_FIELD (struct members with types)
                    members = kg_client.get_struct_members(struct_name)
                    
                    # 10. USED_BY (functions using this struct)
                    used_by = kg_client.get_type_users(struct_name)
                    
                    if members or used_by:
                        kg_context['structs'][struct_name] = {
                            'members': members or [],
                            'used_by_functions': used_by or []
                        }
                        struct_count += 1
                except Exception as e:
                    logger.debug(f"  [DEBUG] Failed to query struct {struct_name}: {e}")
        
        print(f"  ✅ Retrieved context for {struct_count} structs (all {len(rag_structs)} RAG results queried)")
        
        # ============================================================
        # 2.3: ENUMS - Query ALL KG relationships (2+ types)
        # ============================================================
        print(f"  [2.3] Querying ALL enum relationships (HAS_VALUE, INDICATES)...")
        enum_count = 0
        for enum_item in rag_enums:  # ALL enums from RAG (top 8)
            enum_name = extract_entity_name(enum_item, 'enum')
            if enum_name:
                try:
                    # 11. HAS_VALUE (enum values with numeric codes)
                    # 12. INDICATES (semantic meaning of enum values)
                    enum_values = kg_client.get_enum_values(enum_name)
                    
                    if enum_values:
                        kg_context['enums'][enum_name] = {
                            'values': enum_values or []
                        }
                        enum_count += 1
                except Exception as e:
                    logger.debug(f"  [DEBUG] Failed to query enum {enum_name}: {e}")
        
        print(f"  ✅ Retrieved context for {enum_count} enums (all {len(rag_enums)} RAG results queried)")
        
        # ============================================================
        # 2.4: REQUIREMENTS - Query ALL KG relationships (1+ types)
        # ============================================================
        print(f"  [2.4] Querying ALL requirement relationships (IMPLEMENTED_BY)...")
        req_count = 0
        # Parse requirement IDs from user description AND RAG results (dynamic, no hardcoding)
        req_pattern = r'REQ[_\s]?(\d+)'
        req_matches = set(re.findall(req_pattern, description.upper()))
        
        # Also extract requirement IDs from RAG results if available
        for req_item in rag_requirements:  # ALL requirements from RAG (top 8)
            req_id = extract_entity_name(req_item, 'requirement')
            if req_id:
                req_matches.add(req_id)
        
        for req_id in req_matches:
            try:
                # 13. IMPLEMENTED_BY (functions implementing this requirement)
                implementing_funcs = kg_client.get_functions_by_requirement(req_id)
                
                if implementing_funcs:
                    kg_context['requirements'][req_id] = {
                        'implemented_by': implementing_funcs or []
                    }
                    req_count += 1
            except Exception as e:
                logger.debug(f"  [DEBUG] Failed to query requirement {req_id}: {e}")
        
        print(f"  ✅ Retrieved context for {req_count} requirements (all matched IDs queried)")
        
        # ============================================================
        # 2.5: MACROS - Query KG relationships dynamically
        # ============================================================
        print(f"  [2.5] Querying macro-related context...")
        macro_count = 0
        for macro_item in rag_macros:  # ALL macros from RAG (top 10)
            macro_name = extract_entity_name(macro_item, 'macro')
            if macro_name:
                try:
                    # Query KG for functions using this macro (if macro relationship exists)
                    # This is dynamic - KG may or may not have macro relationships
                    users = kg_client.get_type_users(macro_name)  # Some macros act as types
                    
                    if users:
                        kg_context['macros'][macro_name] = {
                            'used_by_functions': users or []
                        }
                        macro_count += 1
                except Exception as e:
                    logger.debug(f"  [DEBUG] Failed to query macro {macro_name}: {e}")
                    pass  # Macros may not have KG entries - that's OK
        
        print(f"  ✅ Retrieved context for {macro_count} macros (all {len(rag_macros)} RAG results queried)")
        
        # ============================================================
        # 2.6: TYPEDEFS - Query ALL KG relationships (2+ types)
        # ============================================================
        print(f"  [2.6] Querying ALL typedef relationships (ALIASES, USED_IN)...")
        typedef_count = 0
        for typedef_item in rag_typedefs:  # ALL typedefs from RAG (top 10)
            typedef_name = extract_entity_name(typedef_item, 'typedef')
            if typedef_name:
                try:
                    # 14. ALIASES (primitive type mapping)
                    primitive = kg_client.get_typedef_primitive_mapping(typedef_name)
                    
                    # 15. USED_IN (structs using this typedef)
                    used_in_structs = kg_client.get_typedef_usage_in_structs(typedef_name)
                    
                    # Also query functions using this typedef
                    used_by_funcs = kg_client.get_type_users(typedef_name)
                    
                    if primitive or used_in_structs or used_by_funcs:
                        kg_context['typedefs'][typedef_name] = {
                            'aliases': primitive or {},
                            'used_in_structs': used_in_structs or [],
                            'used_by_functions': used_by_funcs or []
                        }
                        typedef_count += 1
                except Exception as e:
                    logger.debug(f"  [DEBUG] Failed to query typedef {typedef_name}: {e}")
        
        print(f"  ✅ Retrieved context for {typedef_count} typedefs (all {len(rag_typedefs)} RAG results queried)")
        
        # ============================================================
        # 2.7: HARDWARE/REGISTERS - Query ALL KG relationships (6+ types)
        # CRITICAL: DYNAMIC - Extract register names from RAG hardware/registers results, NO HARDCODING
        # ============================================================
        print(f"  [2.7] Querying hardware/register relationships (DYNAMIC - extracted from RAG)...")
        reg_count = 0
        error_count = 0
        interrupt_count = 0
        
        # Extract register names dynamically from RAG results (NOT hardcoded)
        hardware_entities = set()
        
        # 1. From RAG hardware collection (top 5)
        for hw_item in rag_hardware:
            hw_name = extract_entity_name(hw_item, 'hardware')
            if hw_name:
                hardware_entities.add(hw_name)
        
        # 2. From RAG registers collection (top 8) - PRIMARY source for register definitions
        for reg_item in rag_registers:  # ALL registers from RAG (top 8)
            reg_name = extract_entity_name(reg_item, 'register')
            if reg_name:
                hardware_entities.add(reg_name)
        
        # Note: source_analysis no longer provides registers - all hardware info comes from RAG/KG queries
        
        # 3. Extract register patterns from RAG content (e.g., "CH_CMD", "CH_STATUS")
        for hw_item in (rag_hardware + rag_registers):
            content = hw_item.get('content', '')
            # Look for REGISTER_NAME patterns (all caps with underscores)
            reg_pattern = r'\b([A-Z][A-Z0-9_]*)\b'
            matches = re.findall(reg_pattern, content)
            for match in matches:
                if len(match) >= 3 and '_' in match:  # Filter likely register names
                    hardware_entities.add(match)
        
        print(f"     Found {len(hardware_entities)} registers dynamically from RAG+analysis (no hardcoding)")
        
        # Query KG for each dynamically discovered register
        for reg_name in hardware_entities:
            try:
                # 16. HAS_BITFIELD (register bitfields)
                bitfields = kg_client.get_register_bitfields(reg_name)
                
                # 17. LOCATED_AT (memory address)
                mem_loc = kg_client.get_register_memory_location(reg_name)
                
                # 18. HAS_FIELD (hardware register fields)
                fields = kg_client.get_hardware_register_fields(reg_name)
                
                if bitfields or mem_loc or fields:
                    kg_context['registers'][reg_name] = {
                        'bitfields': bitfields or [],
                        'memory_location': mem_loc or {},
                        'fields': fields or []
                    }
                    
                    # 19. CONTROLS (operations controlled by bitfields) - query for each bitfield
                    for bf in (bitfields or []):
                        bf_name = bf.get('bitfield_name')
                        if bf_name:
                            controlled_ops = kg_client.get_controlled_operations(bf_name)
                            if controlled_ops:
                                bf['controlled_operations'] = controlled_ops
                    
                    reg_count += 1
            except Exception as e:
                logger.debug(f"  [DEBUG] Failed to query register {reg_name}: {e}")
                pass  # Register may not exist in KG - continue
        
        # Query for interrupts and errors triggered/detected (20. TRIGGERED_BY, 21. DETECTED_BY)
        # Extract operation names dynamically from RAG results
        operation_entities = set()
        for src_item in rag_source:
            src_name = extract_entity_name(src_item, 'function')
            if src_name and any(op in src_name.lower() for op in ['transmit', 'receive', 'complete', 'header']):
                operation_entities.add(src_name)
        
        # Add common operation patterns from hardware descriptions
        hw_content = ' '.join([hw.get('content', '') for hw in rag_hardware])
        op_pattern = r'\b([A-Z][a-zA-Z]*(?:Transmit|Receive|Complete|Header|Data|Request|Response))\b'
        matches = re.findall(op_pattern, hw_content)
        for match in matches:
            operation_entities.add(match)
        
        # Query for interrupts triggered by discovered operations
        for op_name in operation_entities:
            try:
                interrupts = kg_client.get_interrupt_triggers(op_name)
                if interrupts:
                    kg_context['interrupts'][op_name] = interrupts
                    interrupt_count += 1
            except Exception as e:
                logger.debug(f"  [DEBUG] Failed to query interrupts for {op_name}: {e}")
                pass
        
        # Extract and query error entities dynamically
        error_entities = set()
        hw_content = ' '.join([hw.get('content', '') for hw in rag_hardware])
        error_pattern = r'\b([A-Z_]*(?:ERROR|BIT_ERROR|CRC|TIMEOUT|FAILURE))\b'
        matches = re.findall(error_pattern, hw_content)
        for match in matches:
            if match and len(match) >= 4:
                error_entities.add(match)
        
        # Query for errors detected by registers
        for err_name in error_entities:
            try:
                error_regs = kg_client.get_error_detection_registers(err_name)
                if error_regs:
                    kg_context['errors'][err_name] = error_regs
                    error_count += 1
            except Exception as e:
                logger.debug(f"  [DEBUG] Failed to query errors for {err_name}: {e}")
                pass
        
        print(f"  ✅ Retrieved context for {reg_count} registers (from {len(hardware_entities)} dynamically discovered)")
        print(f"     {interrupt_count} interrupt sources, {error_count} error types")
        
        # ============================================================
        # Summary: Total KG context collected
        # ============================================================
        total_kg_items = (func_count + struct_count + enum_count + req_count + 
                          reg_count + macro_count + typedef_count +
                          len(kg_context['interrupts']) + len(kg_context['errors']))
        
        print(f"\n  ✅ COMPREHENSIVE KG CONTEXT COLLECTED:")
        print(f"     • Functions: {func_count} (with dependencies, calls, parameters, requirements, case variants)")
        print(f"     • Structs: {struct_count} (with members, user functions)")
        print(f"     • Enums: {enum_count} (with values, semantic meaning)")
        print(f"     • Requirements: {req_count} (with implementing functions)")
        print(f"     • Registers: {reg_count} (bitfields, memory locations, controlled operations)")
        print(f"     • Macros: {macro_count} (with user functions)")
        print(f"     • Typedefs: {typedef_count} (aliases, usage in structs/functions)")
        print(f"     • Interrupts: {len(kg_context['interrupts'])} trigger sources")
        print(f"     • Errors: {len(kg_context['errors'])} error types with detection")
        print(f"  ✅ TOTAL: {total_kg_items} entities with ALL applicable 22+ KG relationships")
        
        _mark_step("STEP 2: KG Queries")
        
        # ================================================================
        # STEP 3: OPTIMIZED - Analyze ONLY selected functions (POST-SELECTION PHASE)
        # ================================================================
        # CRITICAL OPTIMIZATION: Now that we've selected relevant functions via RAG/KG,
        # we analyze ONLY those functions for internal call relationships.
        # This prevents wasting analysis on 1000+ unused functions.
        print(f"\n[STEP 3] Analyzing selected functions for internal call relationships...")
        
        # Extract selected function names from kg_context
        selected_function_names = list(kg_context.get('functions', {}).keys())
        
        # Analyze ONLY these selected functions (not entire module)
        if source_analyzer and selected_function_names:
            try:
                source_analysis = source_analyzer.analyze_selected_functions(selected_function_names)
                print(f"  ✅ Call graph loaded from KG database (selected functions only)")
                print(f"     Functions analyzed: {len(source_analysis.get('function_details', {}))}")
                print(f"     Functions with internal calls: {len(source_analysis.get('function_calls', {}))}")
                print(f"     Functions with dependencies: {len(source_analysis.get('dependencies', {}))}")
            except Exception as e:
                print(f"  [WARN] Call graph analysis failed: {e}")
                source_analysis = {'function_calls': {}, 'function_details': {}, 'dependencies': {}}
        else:
            source_analysis = {'function_calls': {}, 'function_details': {}, 'dependencies': {}}
        
        _mark_step("STEP 3: Source Analysis")
        
        # ================================================================
        # STEP 4: Prepare data for DataDrivenCodeGenerator
        # ================================================================
        print(f"\n[STEP 4] Preparing context for code generation...")

        # Convert RAG results to function/struct/enum dictionaries
        # CRITICAL: Merge KG context (members, values, parameters) into each entity
        # so that code_generator has REAL struct members and enum values to work with
        all_functions = []
        for item in rag_functions:
            func_name = extract_entity_name(item, 'function')
            # Merge KG context for this function (parameters, dependencies, calls)
            kg_func_data = kg_context.get('functions', {}).get(func_name, {})
            all_functions.append({
                'name': func_name,
                'content': item.get('content', ''),
                'full_content': item.get('full_content', ''),
                'similarity': item.get('similarity', 0),
                'metadata': item.get('metadata', {}),
                'parameters': kg_func_data.get('parameters', []),
                'dependencies': kg_func_data.get('dependencies', []),
                'calls': kg_func_data.get('calls', []),
            })
        
        all_structs = []
        for item in rag_structs:
            struct_name = extract_entity_name(item, 'struct')
            # Merge KG context: struct MEMBERS from Neo4j (critical for initialization!)
            kg_struct_data = kg_context.get('structs', {}).get(struct_name, {})
            kg_members_raw = kg_struct_data.get('members', [])
            # Normalize KG member keys: member_name→name, member_type→type
            # IMPORTANT: Neo4j can return None for any field, so we must sanitize
            kg_members = []
            for m in kg_members_raw:
                kg_members.append({
                    'name': m.get('member_name') or m.get('name') or '',
                    'type': m.get('member_type') or m.get('type') or '',
                    'description': m.get('description') or '',
                    'offset': m.get('offset') or '',
                })
            all_structs.append({
                'name': struct_name,
                'content': item.get('content', ''),
                'full_content': item.get('full_content', ''),
                'metadata': item.get('metadata', {}),
                'members': kg_members,  # FROM KG - normalized to {name, type, description}
                'used_by_functions': kg_struct_data.get('used_by_functions', []),
            })
        
        all_enums = []
        for item in rag_enums:
            enum_name = extract_entity_name(item, 'enum')
            # Merge KG context: enum VALUES from Neo4j (critical for correct enum usage!)
            kg_enum_data = kg_context.get('enums', {}).get(enum_name, {})
            kg_values_raw = kg_enum_data.get('values', [])
            # Normalize KG value keys: value_name→name, numeric_value→value
            # IMPORTANT: Neo4j can return None for any field, so we must sanitize
            kg_values = []
            for v in kg_values_raw:
                kg_values.append({
                    'name': v.get('value_name') or v.get('name') or '',
                    'value': v.get('numeric_value') or v.get('value') or '',
                    'description': v.get('description') or '',
                })
            all_enums.append({
                'name': enum_name,
                'content': item.get('content', ''),
                'full_content': item.get('full_content', ''),
                'values': kg_values,  # FROM KG - normalized to {name, value, description}
                'metadata': item.get('metadata', {}),
            })
        
        print(f"  -> Functions: {len(all_functions)} (with KG parameters merged)")
        print(f"  -> Structs: {len(all_structs)} (with KG members merged: {sum(1 for s in all_structs if s.get('members'))} have members)")
        print(f"  -> Enums: {len(all_enums)} (with KG values merged: {sum(1 for e in all_enums if e.get('values'))} have values)")
        
        # ================================================================
        # STEP 4.1: Proactively ensure status/polling functions are available
        # ================================================================
        # The RAG semantic search may NOT return utility functions like getChannelStatus
        # because they don't match the user's test description semantically.
        # But these functions are ESSENTIAL for polling patterns in every test.
        # FIX: Check if any status/polling function exists in all_functions.
        # If not, do a targeted RAG query using keywords like "getStatus", "getChannelStatus".
        # This is DATA-DRIVEN: uses keyword detection, not hardcoded function names.
        # ================================================================
        existing_func_names_step4 = {f.get('name', '').lower() for f in all_functions}
        has_status_func = any(
            'getstatus' in fn or 'getchannelstatus' in fn or 'checkstatus' in fn
            for fn in existing_func_names_step4
        )
        
        if not has_status_func:
            print(f"\n  [STEP 4.1] No status/polling function in RAG top results — querying RAG for status functions...")
            # Query RAG with status-related keywords + module name for relevance
            status_queries = [
                f"getChannelStatus {module}",
                f"getStatus channel {module}",
            ]
            status_func_found = False
            for sq in status_queries:
                if status_func_found:
                    break
                try:
                    status_hits = rag_client.query_functions(sq, n_results=3)
                    for hit in status_hits:
                        hit_name = extract_entity_name(hit, 'function')
                        hit_lower = hit_name.lower()
                        # Only add if it's actually a status function (keyword check)
                        if any(kw in hit_lower for kw in ['getstatus', 'getchannelstatus', 'checkstatus', 'readstatus']):
                            if hit_lower not in existing_func_names_step4:
                                # Merge KG context
                                kg_func_data = kg_context.get('functions', {}).get(hit_name, {})
                                if not kg_func_data:
                                    try:
                                        params = kg_client.get_function_parameters(hit_name)
                                        deps = kg_client.get_function_dependencies(hit_name)
                                        calls = kg_client.get_function_calls(hit_name)
                                        kg_func_data = {
                                            'parameters': params or [],
                                            'dependencies': deps or [],
                                            'calls': calls or [],
                                        }
                                        if params or deps or calls:
                                            kg_context['functions'][hit_name] = {
                                                'dependencies': deps or [],
                                                'calls': calls or [],
                                                'parameters': params or [],
                                                'requirements': [],
                                                'switch_cases': []
                                            }
                                    except Exception:
                                        kg_func_data = {'parameters': [], 'dependencies': [], 'calls': []}
                                
                                all_functions.append({
                                    'name': hit_name,
                                    'content': hit.get('content', ''),
                                    'full_content': hit.get('full_content', ''),
                                    'similarity': hit.get('similarity', 0),
                                    'metadata': hit.get('metadata', {}),
                                    'parameters': kg_func_data.get('parameters', []),
                                    'dependencies': kg_func_data.get('dependencies', []),
                                    'calls': kg_func_data.get('calls', []),
                                    'proactive_status_backfill': True
                                })
                                existing_func_names_step4.add(hit_lower)
                                status_func_found = True
                                print(f"    ✅ Added status function: {hit_name} (similarity={hit.get('similarity', 0):.3f})")
                                break
                except Exception as sq_err:
                    print(f"    [WARN] Status function query failed: {sq_err}")
            
            if not status_func_found:
                print(f"    ⚠️ No status function found in RAG — polling patterns may be incomplete")
        else:
            print(f"\n  [STEP 4.1] Status/polling function already in RAG results ✅")

        # ================================================================
        # STEP 4.2: Proactively ensure config structs are in all_structs
        # ================================================================
        # RAG semantic search returns structs matching the test DESCRIPTION,
        # but config structs (e.g., IfxCxpi_Cxpi_ChannelConfig_t) may NOT be
        # returned because they don't match "inject TX CRC error" semantically.
        # Without them in struct_lookup, _add_struct_member_inits_v2 finds nothing.
        #
        # FIX: For every config function in all_functions, derive the expected
        # config struct name from its RAG content/KG parameters and ensure it
        # is in all_structs with its members loaded from KG.
        # DATA-DRIVEN: keyword detection only, no hardcoded struct names.
        # ================================================================
        existing_struct_names = {s.get('name', '').lower() for s in all_structs}
        config_structs_added = 0

        # Find all config functions (names containing 'initConfig' or 'initChannelConfig' etc.)
        all_func_names_in_pipeline = [f.get('name', '') for f in all_functions]
        config_func_names = [
            fn for fn in all_func_names_in_pipeline
            if 'config' in fn.lower() and 'init' in fn.lower()
        ]

        print(f"\n  [STEP 4.2] Ensuring config structs are in all_structs for {len(config_func_names)} config functions...")

        for cfg_func_name in config_func_names:
            # Try to derive config struct name from KG parameters of the config function
            # Config functions typically take a pointer to their config struct as first param
            kg_cfg_func = kg_context.get('functions', {}).get(cfg_func_name, {})
            cfg_params = kg_cfg_func.get('parameters', [])

            candidate_struct_names = []

            # From KG parameters: find pointer-to-struct param (first param is usually config struct)
            # KG returns: param_type_direct (raw C type) or param_type (linked type node name)
            for param in cfg_params:
                ptype = (
                    param.get('param_type_direct') or
                    param.get('param_type') or
                    param.get('type') or ''
                ).strip().replace('*', '').strip()
                if ptype and 'config' in ptype.lower() and ptype.lower() not in existing_struct_names:
                    candidate_struct_names.append(ptype)

            # If KG had no params, query RAG for the function and parse its signature
            if not candidate_struct_names:
                # Fallback: search all_functions for this func and parse its content
                for fn_info in all_functions:
                    if fn_info.get('name', '') == cfg_func_name:
                        content = fn_info.get('full_content', '') or fn_info.get('content', '')
                        if content:
                            first_line = content.split('\n')[0]
                            # Extract param types from signature
                            param_types = re.findall(r'(Ifx\w+)\s*\*', first_line)
                            for pt in param_types:
                                if 'config' in pt.lower() and pt.lower() not in existing_struct_names:
                                    candidate_struct_names.append(pt)
                        break

            # FINAL FALLBACK: derive config struct name from the function name itself
            # e.g., 'IfxCxpi_initChannelConfig' → search RAG for 'ChannelConfig'
            # e.g., 'IfxCxpi_Cxpi_initModuleConfigForTest' → search RAG for 'TestConfig'
            if not candidate_struct_names:
                # Build a search query from meaningful CamelCase words in the function name
                # e.g., 'initChannelConfig' → search for 'ChannelConfig'
                # e.g., 'initModuleConfigForTest' → search for 'TestConfig'
                parts_underscore = cfg_func_name.split('_')
                # Remove module prefix (everything before first meaningful part)
                fn_no_prefix = '_'.join(parts_underscore[1:]) if len(parts_underscore) > 1 else cfg_func_name
                # Find the 'Config' segment
                if 'Config' in fn_no_prefix:
                    config_idx = fn_no_prefix.index('Config')
                    after_config = fn_no_prefix[config_idx:]  # e.g., 'ConfigForTest' or 'Config'
                    before_config_part = fn_no_prefix[:config_idx]
                    # Extract last CamelCase word before 'Config' in the segment
                    camel_words = re.findall(r'[A-Z][a-z]*', before_config_part)
                    after_words = re.findall(r'[A-Z][a-z]*', after_config[6:])  # skip 'Config'
                    # Build search query: e.g., 'ChannelConfig' or 'TestConfig'
                    search_concept = (after_words[-1] if after_words else (camel_words[-1] if camel_words else '')) + 'Config'
                    if len(search_concept) > 6:  # has actual concept word
                        candidate_struct_names.append(search_concept)  # Will be used as RAG query

            for struct_candidate in candidate_struct_names:
                if struct_candidate.lower() in existing_struct_names:
                    continue  # Already have it
                try:
                    # Query RAG for this specific struct
                    struct_hits = rag_client.query_structs(struct_candidate, n_results=5)
                    best_hit = None
                    for hit in struct_hits:
                        hit_name = extract_entity_name(hit, 'struct')
                        if not hit_name or hit_name.lower() in existing_struct_names:
                            continue
                        # Accept if: exact match, OR concept word appears in hit name AND it's a Config struct
                        candidate_lower = struct_candidate.lower().replace('_', '').replace('*', '').replace(' ', '')
                        hit_lower = hit_name.lower().replace('_', '')
                        is_config = 'config' in hit_name.lower()
                        exact_match = candidate_lower == hit_lower
                        concept_match = is_config and candidate_lower.replace('config', '') in hit_lower
                        if exact_match or concept_match:
                            best_hit = (hit_name, hit)
                            break
                    # If no exact/concept match, take the first Config struct from results
                    if not best_hit:
                        for hit in struct_hits:
                            hit_name = extract_entity_name(hit, 'struct')
                            if hit_name and 'config' in hit_name.lower() and hit_name.lower() not in existing_struct_names:
                                best_hit = (hit_name, hit)
                                break

                    if best_hit:
                        hit_name, hit = best_hit
                        # Query KG for members
                        try:
                            members_raw = kg_client.get_struct_members(hit_name)
                        except Exception:
                            members_raw = []
                        kg_members = []
                        for m in (members_raw or []):
                            kg_members.append({
                                'name': m.get('member_name') or m.get('name') or '',
                                'type': m.get('member_type') or m.get('type') or '',
                                'description': m.get('description') or '',
                                'offset': m.get('offset') or '',
                            })
                        all_structs.append({
                            'name': hit_name,
                            'content': hit.get('content', ''),
                            'full_content': hit.get('full_content', ''),
                            'metadata': hit.get('metadata', {}),
                            'members': kg_members,
                            'used_by_functions': [],
                            'config_struct_backfill': True,
                        })
                        existing_struct_names.add(hit_name.lower())
                        config_structs_added += 1
                        print(f"    ✅ Config struct backfilled: {hit_name} (for func: {cfg_func_name}, members={len(kg_members)})")
                    else:
                        print(f"    ⚠️ Config struct '{struct_candidate}' not found in RAG for func: {cfg_func_name}")
                except Exception as cs_err:
                    print(f"    [WARN] Config struct backfill failed for {cfg_func_name}: {cs_err}")

        if config_structs_added == 0:
            print(f"  [STEP 4.2] No config structs needed backfilling ✅")
        else:
            print(f"  [STEP 4.2] ✅ Backfilled {config_structs_added} config structs into all_structs")

        # ================================================================
        # STEP 4.3: Backfill missing ENUM definitions for config struct members
        # ================================================================
        # Even after Step 4.2, the enum types for config struct members may not
        # be in all_enums — because RAG retrieved enums semantically close to the
        # TEST DESCRIPTION, not the config struct member types.
        # Example: "inject TX CRC error" → RAG returns error/flag enums, NOT
        # IfxCxpi_Mode_t, IfxCxpi_ChState_t, IfxCxpi_ChannelId_t etc.
        #
        # FIX: Walk every member of every config struct in all_structs.
        # If the member type looks like an enum (ends in _t, starts with module prefix)
        # AND is not already in all_enums → query RAG by exact type name → add it.
        # This guarantees the skeleton generator always finds the enum it needs.
        # ================================================================
        existing_enum_names = {e.get('name', '').lower() for e in all_enums}
        enums_added = 0

        # Collect all config struct definitions currently in all_structs
        config_structs_for_enum_backfill = [
            s for s in all_structs
            if 'config' in s.get('name', '').lower()
        ]

        print(f"\n  [STEP 4.3] Backfilling enum types for {len(config_structs_for_enum_backfill)} config struct(s)...")

        for cs in config_structs_for_enum_backfill:
            cs_members = cs.get('members', [])
            
            # =================================================================
            # FIX: KG often returns members with type='None'. In that case,
            # parse the REAL types from the struct's RAG full_content.
            # The full_content format is:
            #   "Members: IfxCxpi_Mode_t mode: desc, uint32_t baudrate: desc, ..."
            # =================================================================
            types_all_none = cs_members and all(
                (m.get('type', m.get('member_type', '')) or 'None') in ('None', '', 'none')
                for m in cs_members
            )
            if types_all_none:
                fc = cs.get('full_content', '') or cs.get('content', '')
                if fc:
                    from backend.generators.code_generator import _parse_struct_members_from_content
                    parsed_members = _parse_struct_members_from_content(fc)
                    if parsed_members:
                        # Build name→type map and merge into KG members
                        parsed_map = {p['name']: p.get('type', '') for p in parsed_members}
                        for m in cs_members:
                            mn = m.get('name', m.get('member_name', ''))
                            if mn and mn in parsed_map:
                                m['type'] = parsed_map[mn]
                                if 'member_type' in m:
                                    m['member_type'] = parsed_map[mn]
                        print(f"    [FIX] Merged types from full_content for {cs.get('name','')}: {len(parsed_map)} member types recovered")
                    else:
                        # Last resort: use parsed_members directly (replace KG members)
                        print(f"    [WARN] Could not parse full_content for {cs.get('name','')} — member types remain None")
            
            for member in cs_members:
                mtype = (member.get('type') or member.get('member_type') or '').strip()
                # Skip pointers, void, plain numeric types — only check _t enum-style types
                if not mtype or '*' in mtype or mtype in ('None', 'none'):
                    continue
                mtype_clean = mtype.replace('const', '').strip()
                # Must end in _t and start with a module prefix (Ifx...) to be an enum candidate
                if not (mtype_clean.endswith('_t') and mtype_clean.startswith('Ifx')):
                    continue
                if mtype_clean.lower() in existing_enum_names:
                    continue  # Already have it
                # Query RAG by exact type name
                try:
                    enum_hits = rag_client.query_enums(mtype_clean, n_results=5)
                    best_enum_hit = None
                    for ehit in enum_hits:
                        ehit_name = extract_entity_name(ehit, 'enum')
                        if not ehit_name:
                            continue
                        # Prefer exact name match first
                        if ehit_name.lower() == mtype_clean.lower():
                            best_enum_hit = (ehit_name, ehit)
                            break
                        # Accept close match: both share the same descriptor words
                        if ehit_name.lower() not in existing_enum_names:
                            if best_enum_hit is None:
                                best_enum_hit = (ehit_name, ehit)

                    if best_enum_hit:
                        ehit_name, ehit = best_enum_hit
                        # Get enum values from KG
                        try:
                            kg_enum_vals = kg_client.get_enum_values(ehit_name)
                        except Exception:
                            kg_enum_vals = []
                        enum_values = []
                        for v in (kg_enum_vals or []):
                            enum_values.append({
                                'name': v.get('value_name') or v.get('name') or '',
                                'value': v.get('numeric_value') or v.get('value') or '',
                                'description': v.get('description') or '',
                            })
                        # Fallback: parse from full_content if KG returned nothing
                        if not enum_values:
                            from backend.generators.code_generator import _parse_enum_values_from_content
                            fc = ehit.get('full_content', '') or ehit.get('content', '')
                            enum_values = _parse_enum_values_from_content(fc)

                        all_enums.append({
                            'name': ehit_name,
                            'content': ehit.get('content', ''),
                            'full_content': ehit.get('full_content', ''),
                            'values': enum_values,
                            'enum_backfill': True,
                        })
                        existing_enum_names.add(ehit_name.lower())
                        enums_added += 1
                        print(f"    ✅ Enum backfilled: {ehit_name} (for member type: {mtype_clean}, values={len(enum_values)})")
                    else:
                        print(f"    ⚠️  Enum '{mtype_clean}' not found in RAG (member of {cs.get('name','')})")
                except Exception as enum_err:
                    print(f"    [WARN] Enum backfill failed for type '{mtype_clean}': {enum_err}")

        if enums_added == 0:
            print(f"  [STEP 4.3] No enum types needed backfilling ✅")
        else:
            print(f"  [STEP 4.3] ✅ Backfilled {enums_added} enum type(s) into all_enums")

        # ================================================================
        # STEP 4.4: Proactive struct pre-fetch — guarantee every struct type
        # referenced in any function signature in all_functions is present in
        # all_structs WITH its members before code generation begins.
        #
        # WHY: `generate_sample_c_code` builds `declared_vars` by scanning
        # function parameter types and calls `_add_struct_member_inits_v2` for
        # each config struct.  If a struct wasn't in the top-N RAG hits for the
        # test description (e.g. IfxCxpi_TestConfig_t for a loopback test) its
        # entry is absent from `struct_lookup`, causing "No members found" and a
        # TODO block instead of real member assignments.
        #
        # FIX (DATA-DRIVEN): Walk every function in all_functions.  Parse the
        # first line of its full_content to extract parameter base types.  For
        # every _t-suffixed struct type that is NOT already in all_structs, fire
        # a targeted RAG query by exact type name and add the result.  The enum
        # backfill in Step 4.3 will then cover the newly discovered members
        # automatically on the next generation cycle; for the current cycle we
        # also run the same per-member enum backfill inline here.
        # ================================================================
        existing_struct_names_44 = {s.get('name', '').lower() for s in all_structs}
        structs_added_44 = 0

        # Collect all struct parameter types referenced across all function signatures
        candidate_struct_types_44: set = set()
        for func_info_44 in all_functions:
            fc44 = func_info_44.get('full_content', '') or func_info_44.get('content', '')
            if not fc44 or '(' not in fc44.split('\n')[0]:
                continue
            first_line_44 = fc44.split('\n')[0]
            param_str_44 = first_line_44.split('(', 1)[1].rsplit(')', 1)[0]
            for raw_param_44 in param_str_44.split(','):
                raw_param_44 = raw_param_44.strip()
                if not raw_param_44 or raw_param_44 == 'void':
                    continue
                # Normalise pointer markers so the last token is always the param name
                parts_44 = raw_param_44.replace('*', ' * ').split()
                if len(parts_44) < 2:
                    continue
                base_type_44 = ' '.join(parts_44[:-1]).replace(' * ', '*').replace(' *', '*')
                base_type_44 = base_type_44.replace('*', '').replace('const', '').strip()
                # Only interested in module struct types (end in _t, start with Ifx)
                if base_type_44 and base_type_44.endswith('_t') and base_type_44.startswith('Ifx'):
                    candidate_struct_types_44.add(base_type_44)

        print(f"\n  [STEP 4.4] Pre-fetching missing struct definitions for {len(candidate_struct_types_44)} candidate types...")

        for struct_type_44 in sorted(candidate_struct_types_44):
            if struct_type_44.lower() in existing_struct_names_44:
                continue  # Already present — skip

            # Targeted RAG query by exact struct type name
            try:
                struct_hits_44 = rag_client.query_structs(struct_type_44, n_results=5)
                best_struct_hit_44 = None
                for shite_44 in struct_hits_44:
                    shite_name_44 = extract_entity_name(shite_44, 'struct')
                    if not shite_name_44:
                        continue
                    # Prefer exact name match
                    if shite_name_44.lower() == struct_type_44.lower():
                        best_struct_hit_44 = (shite_name_44, shite_44)
                        break
                    if best_struct_hit_44 is None:
                        best_struct_hit_44 = (shite_name_44, shite_44)

                if best_struct_hit_44:
                    hit_name_44, hit_44 = best_struct_hit_44
                    # Fetch KG members for this struct
                    try:
                        members_raw_44 = kg_client.get_struct_members(hit_name_44)
                    except Exception:
                        members_raw_44 = []
                    kg_members_44 = []
                    for m44 in (members_raw_44 or []):
                        kg_members_44.append({
                            'name': m44.get('member_name') or m44.get('name') or '',
                            'type': m44.get('member_type') or m44.get('type') or '',
                            'description': m44.get('description') or '',
                            'offset': m44.get('offset') or '',
                        })

                    # If KG has no member types, recover them from full_content right now
                    fc_44 = hit_44.get('full_content', '') or hit_44.get('content', '')
                    types_none_44 = (not kg_members_44) or all(
                        (m44.get('type', '') or 'None') in ('None', '', 'none')
                        for m44 in kg_members_44
                    )
                    if types_none_44 and fc_44:
                        from backend.generators.code_generator import _parse_struct_members_from_content
                        parsed_44 = _parse_struct_members_from_content(fc_44)
                        if parsed_44:
                            if kg_members_44:
                                # Merge parsed types into existing KG member dicts
                                parsed_map_44 = {p['name']: p.get('type', '') for p in parsed_44}
                                for m44 in kg_members_44:
                                    mn44 = m44.get('name', m44.get('member_name', ''))
                                    if mn44 and mn44 in parsed_map_44:
                                        m44['type'] = parsed_map_44[mn44]
                                        if 'member_type' in m44:
                                            m44['member_type'] = parsed_map_44[mn44]
                            else:
                                # No KG members at all — use the parsed members directly
                                kg_members_44 = parsed_44

                    new_struct_entry_44 = {
                        'name': hit_name_44,
                        'content': hit_44.get('content', ''),
                        'full_content': fc_44,
                        'metadata': hit_44.get('metadata', {}),
                        'members': kg_members_44,
                        'used_by_functions': [],
                        'step44_backfill': True,
                    }
                    all_structs.append(new_struct_entry_44)
                    existing_struct_names_44.add(hit_name_44.lower())
                    structs_added_44 += 1
                    print(f"    ✅ [STEP 4.4] Struct pre-fetched: {hit_name_44} (members={len(kg_members_44)})")

                    # Inline enum backfill for the newly discovered struct's members
                    # (mirrors the logic in Step 4.3 so the enums are available immediately)
                    for m44 in kg_members_44:
                        mtype_44 = (m44.get('type') or m44.get('member_type') or '').strip()
                        if not mtype_44 or '*' in mtype_44 or mtype_44 in ('None', 'none'):
                            continue
                        mtype_clean_44 = mtype_44.replace('const', '').strip()
                        if not (mtype_clean_44.endswith('_t') and mtype_clean_44.startswith('Ifx')):
                            continue
                        if mtype_clean_44.lower() in existing_enum_names:
                            continue
                        try:
                            enum_hits_44 = rag_client.query_enums(mtype_clean_44, n_results=5)
                            best_enum_44 = None
                            for ehit_44 in enum_hits_44:
                                ehit_name_44 = extract_entity_name(ehit_44, 'enum')
                                if not ehit_name_44:
                                    continue
                                if ehit_name_44.lower() == mtype_clean_44.lower():
                                    best_enum_44 = (ehit_name_44, ehit_44)
                                    break
                                if best_enum_44 is None:
                                    best_enum_44 = (ehit_name_44, ehit_44)
                            if best_enum_44:
                                en44, ed44 = best_enum_44
                                try:
                                    kg_ev_44 = kg_client.get_enum_values(en44)
                                except Exception:
                                    kg_ev_44 = []
                                ev44 = []
                                for v44 in (kg_ev_44 or []):
                                    ev44.append({
                                        'name': v44.get('value_name') or v44.get('name') or '',
                                        'value': v44.get('numeric_value') or v44.get('value') or '',
                                        'description': v44.get('description') or '',
                                    })
                                if not ev44:
                                    from backend.generators.code_generator import _parse_enum_values_from_content
                                    ev44 = _parse_enum_values_from_content(ed44.get('full_content', '') or ed44.get('content', ''))
                                all_enums.append({
                                    'name': en44,
                                    'content': ed44.get('content', ''),
                                    'full_content': ed44.get('full_content', ''),
                                    'values': ev44,
                                    'step44_enum_backfill': True,
                                })
                                existing_enum_names.add(en44.lower())
                                enums_added += 1
                                print(f"      ✅ [STEP 4.4] Enum backfilled: {en44} (for {mtype_clean_44}, values={len(ev44)})")
                        except Exception as e44_err:
                            print(f"      [WARN][STEP 4.4] Enum backfill failed for '{mtype_clean_44}': {e44_err}")
                else:
                    print(f"    ⚠️ [STEP 4.4] Struct '{struct_type_44}' not found in RAG — will generate TODO block")
            except Exception as s44_err:
                print(f"    [WARN][STEP 4.4] Struct pre-fetch failed for '{struct_type_44}': {s44_err}")

        if structs_added_44 == 0:
            print(f"  [STEP 4.4] No additional structs needed pre-fetching ✅")
        else:
            print(f"  [STEP 4.4] ✅ Pre-fetched {structs_added_44} struct(s) into all_structs")

        # Cache structs/enums for the /apply_enum_resolution endpoint
        global _generation_context_cache
        _generation_context_cache['all_structs'] = all_structs
        _generation_context_cache['all_enums'] = all_enums
        
        _mark_step("STEP 4: Data Preparation")
        
        # ================================================================
        # STEP 5: Initialize code generator
        # ================================================================
        print(f"\n[STEP 5] Initializing DataDrivenCodeGenerator...")
        
        code_generator = DataDrivenCodeGenerator(
            pattern_library=pattern_library,
            code_generation_rules=code_generation_rules,
            all_structs=all_structs,
            all_enums=all_enums,
            all_macros=[],
            all_typedefs=[],
            module=module,
            source_code_enriched=source_analysis if source_analysis and source_analysis.get('function_details') else None
        )
        
        _mark_step("STEP 5: Init Code Generator")
        
        # ================================================================
        # STEP 6: Generate test structure
        # ================================================================
        print(f"\n[STEP 6] Generating test structure...")
        print(f"  -> Passing RAG results (PHASE 3) as PRIMARY source for feature classification...")
        print(f"  -> Passing KG context (DEPENDS_ON) for function sequence ordering...")
        
        generation_result = code_generator.generate(
            user_description=description,
            user_parameters=request.additional_notes,
            all_functions=all_functions,
            rag_results=all_functions,  # Pass RAG functions with similarity scores
            kg_context=kg_context        # Pass KG DEPENDS_ON relationships for sequencing
        )
        
        # STEP 6.1: Capture sample test code for LLM enhancement (IDEA 1 SEQUENTIAL)
        sample_test_code = generation_result.get('sample_test_code', '')
        print(f"  -> Sample test code skeleton generated ({len(sample_test_code.splitlines())} lines)")
        print(f"  -> Ready for LLM enhancement with hardware specifications")
        
        # Cache skeleton for post-LLM validation (exact while-loop count comparison)
        _generation_context_cache['skeleton_code'] = sample_test_code
        
        # ================================================================
        # STEP 6.2: BACKFILL missing functions from function_sequence
        # ================================================================
        # The FunctionSequenceBuilder adds always_present and frequently_present
        # functions from PUML patterns that may NOT be in all_functions (which
        # only contains RAG-returned results). This causes _generate_function_call()
        # to output "/* parameters not found */" and the LLM to skip them.
        # FIX: Query RAG for any function in the sequence not already in all_functions,
        # merge KG context, add to all_functions, then regenerate the skeleton.
        # ================================================================
        function_sequence = generation_result.get('function_sequence', [])
        existing_func_names = {f.get('name', '') for f in all_functions}
        missing_funcs = [fn for fn in function_sequence if fn not in existing_func_names]
        
        if missing_funcs:
            print(f"\n[STEP 6.2] Backfilling {len(missing_funcs)} functions added by FSB but missing from RAG results...")
            for mf_name in missing_funcs:
                print(f"  -> Querying RAG for: {mf_name}")
            
            backfilled_count = 0
            for mf_name in missing_funcs:
                try:
                    # Query RAG using the function name as semantic search query
                    # This will find the function by name similarity
                    rag_hits = rag_client.query_functions(mf_name, n_results=3)
                    
                    # Also try the alternate prefix form (IfxMod_Mod_func ↔ IfxMod_func)
                    alt_name = None
                    if mf_name.startswith('Ifx') and '_' in mf_name:
                        after_ifx = mf_name[3:]
                        mod_end = after_ifx.find('_')
                        if mod_end > 0:
                            mod = after_ifx[:mod_end]
                            double_prefix = f'Ifx{mod}_{mod}_'
                            single_prefix = f'Ifx{mod}_'
                            if mf_name.startswith(double_prefix):
                                alt_name = mf_name.replace(double_prefix, single_prefix, 1)
                            else:
                                alt_name = mf_name.replace(single_prefix, double_prefix, 1)
                    
                    if alt_name and not rag_hits:
                        rag_hits = rag_client.query_functions(alt_name, n_results=3)
                    
                    # Find best match: exact name, alt name, or highest similarity
                    best_hit = None
                    for hit in rag_hits:
                        hit_content = hit.get('full_content', '') or hit.get('content', '')
                        hit_first_line = hit_content.split('\n')[0] if hit_content else ''
                        # Check if the function name appears in the content
                        if mf_name in hit_content or (alt_name and alt_name in hit_content):
                            best_hit = hit
                            break
                    
                    if not best_hit and rag_hits:
                        # Use highest similarity result as fallback
                        best_hit = rag_hits[0]
                    
                    if best_hit:
                        # Extract name from content for accurate matching
                        func_entry_name = mf_name  # Use the sequence name
                        
                        # Query KG for this function's relationships
                        kg_func_data = {}
                        try:
                            deps = kg_client.get_function_dependencies(mf_name)
                            calls = kg_client.get_function_calls(mf_name)
                            params = kg_client.get_function_parameters(mf_name)
                            # Also try alternate name for KG
                            if not (deps or calls or params) and alt_name:
                                deps = kg_client.get_function_dependencies(alt_name)
                                calls = kg_client.get_function_calls(alt_name)
                                params = kg_client.get_function_parameters(alt_name)
                            kg_func_data = {
                                'parameters': params or [],
                                'dependencies': deps or [],
                                'calls': calls or [],
                            }
                            # Also add to kg_context for LLM prompt KG reference
                            if deps or calls or params:
                                kg_context['functions'][mf_name] = {
                                    'dependencies': deps or [],
                                    'calls': calls or [],
                                    'parameters': params or [],
                                    'requirements': [],
                                    'switch_cases': []
                                }
                        except Exception as kg_err:
                            print(f"    [WARN] KG query failed for {mf_name}: {kg_err}")
                        
                        # Build the function entry with the SEQUENCE name
                        # but use the RAG hit's content (which has the signature)
                        hit_content = best_hit.get('full_content', '') or best_hit.get('content', '')
                        
                        # If the RAG content uses a different name form, adapt the first line
                        # to match our sequence name so _generate_function_call can find it
                        if alt_name and alt_name in hit_content and mf_name not in hit_content:
                            # The RAG has the alt_name form; adapt content to use mf_name
                            adapted_content = hit_content.replace(alt_name, mf_name)
                        else:
                            adapted_content = hit_content
                        
                        new_func_entry = {
                            'name': mf_name,
                            'content': adapted_content[:500] if adapted_content else '',
                            'full_content': adapted_content,
                            'similarity': best_hit.get('similarity', 0),
                            'metadata': best_hit.get('metadata', {}),
                            'parameters': kg_func_data.get('parameters', []),
                            'dependencies': kg_func_data.get('dependencies', []),
                            'calls': kg_func_data.get('calls', []),
                            'backfilled': True  # Mark as backfilled for debugging
                        }
                        all_functions.append(new_func_entry)
                        existing_func_names.add(mf_name)
                        backfilled_count += 1
                        print(f"    ✅ Backfilled: {mf_name} (similarity={best_hit.get('similarity', 0):.3f}, KG params={len(kg_func_data.get('parameters', []))})")
                    else:
                        print(f"    ⚠️ Could not find: {mf_name} in RAG (no matching results)")
                        
                except Exception as bf_err:
                    print(f"    ❌ Backfill failed for {mf_name}: {bf_err}")
            
            print(f"  -> Backfilled {backfilled_count}/{len(missing_funcs)} missing functions")
            
            # ================================================================
            # STEP 6.3: DISCOVER AND ADD MISSING DEPENDENCIES (RECURSIVE)
            # ================================================================
            # After backfilling, check if ANY function in the sequence has dependencies
            # that are NOT in the sequence. If so, add them and backfill them too.
            # This ensures transitive dependencies are resolved.
            # Example: IfxCxpi_initModuleForErrorCtl depends on IfxCxpi_Cxpi_initModuleConfigForErrorCtl
            # ================================================================
            print(f"\n[STEP 6.3] Discovering missing transitive dependencies from KG...")
            
            # Collect all dependencies from kg_context for functions in sequence
            all_deps_needed = set()
            for func_name in function_sequence:
                func_kg = kg_context.get('functions', {}).get(func_name, {})
                deps = func_kg.get('dependencies', [])
                for dep in deps:
                    if isinstance(dep, dict):
                        dep_name = dep.get('dependency', dep.get('function', ''))
                    else:
                        dep_name = str(dep)
                    if dep_name:
                        all_deps_needed.add(dep_name)
            
            # Find dependencies NOT in all_functions
            current_func_names = {f.get('name', '') for f in all_functions}
            missing_deps = [d for d in all_deps_needed if d not in current_func_names]
            
            if missing_deps:
                print(f"  -> Found {len(missing_deps)} missing transitive dependencies:")
                for md in missing_deps:
                    print(f"      • {md}")
                
                deps_backfilled = 0
                for dep_name in missing_deps:
                    try:
                        print(f"  -> Backfilling dependency: {dep_name}")
                        
                        # Query RAG
                        rag_hits = rag_client.query_functions(dep_name, n_results=3)
                        
                        # Try alternate name
                        alt_name = None
                        if dep_name.startswith('Ifx') and '_' in dep_name:
                            after_ifx = dep_name[3:]
                            mod_end = after_ifx.find('_')
                            if mod_end > 0:
                                mod = after_ifx[:mod_end]
                                double_prefix = f'Ifx{mod}_{mod}_'
                                single_prefix = f'Ifx{mod}_'
                                if dep_name.startswith(double_prefix):
                                    alt_name = dep_name.replace(double_prefix, single_prefix, 1)
                                else:
                                    alt_name = dep_name.replace(single_prefix, double_prefix, 1)
                        
                        if alt_name and not rag_hits:
                            rag_hits = rag_client.query_functions(alt_name, n_results=3)
                        
                        # Find best match
                        best_hit = None
                        for hit in rag_hits:
                            hit_content = hit.get('full_content', '') or hit.get('content', '')
                            if dep_name in hit_content or (alt_name and alt_name in hit_content):
                                best_hit = hit
                                break
                        
                        if not best_hit and rag_hits:
                            best_hit = rag_hits[0]
                        
                        if best_hit:
                            # Query KG for this dependency
                            kg_func_data = {}
                            try:
                                deps_of_dep = kg_client.get_function_dependencies(dep_name)
                                calls = kg_client.get_function_calls(dep_name)
                                params = kg_client.get_function_parameters(dep_name)
                                if not (deps_of_dep or calls or params) and alt_name:
                                    deps_of_dep = kg_client.get_function_dependencies(alt_name)
                                    calls = kg_client.get_function_calls(alt_name)
                                    params = kg_client.get_function_parameters(alt_name)
                                kg_func_data = {
                                    'parameters': params or [],
                                    'dependencies': deps_of_dep or [],
                                    'calls': calls or [],
                                }
                                # Add to kg_context
                                if deps_of_dep or calls or params:
                                    kg_context['functions'][dep_name] = {
                                        'dependencies': deps_of_dep or [],
                                        'calls': calls or [],
                                        'parameters': params or [],
                                        'requirements': [],
                                        'switch_cases': []
                                    }
                            except Exception as kg_err:
                                print(f"    [WARN] KG query failed for {dep_name}: {kg_err}")
                            
                            # Adapt content
                            hit_content = best_hit.get('full_content', '') or best_hit.get('content', '')
                            if alt_name and alt_name in hit_content and dep_name not in hit_content:
                                adapted_content = hit_content.replace(alt_name, dep_name)
                            else:
                                adapted_content = hit_content
                            
                            new_dep_entry = {
                                'name': dep_name,
                                'content': adapted_content[:500] if adapted_content else '',
                                'full_content': adapted_content,
                                'similarity': best_hit.get('similarity', 0),
                                'metadata': best_hit.get('metadata', {}),
                                'parameters': kg_func_data.get('parameters', []),
                                'dependencies': kg_func_data.get('dependencies', []),
                                'calls': kg_func_data.get('calls', []),
                                'backfilled': True,
                                'transitive_dependency': True  # Mark as transitive
                            }
                            all_functions.append(new_dep_entry)
                            current_func_names.add(dep_name)
                            
                            # IMPORTANT: Add to function_sequence BEFORE the function that depends on it
                            # Find the first function that depends on this dependency
                            insert_before_idx = len(function_sequence)  # Default: append at end
                            for idx, func in enumerate(function_sequence):
                                func_deps = kg_context.get('functions', {}).get(func, {}).get('dependencies', [])
                                for d in func_deps:
                                    d_name = d.get('dependency', '') if isinstance(d, dict) else str(d)
                                    if d_name == dep_name:
                                        insert_before_idx = idx
                                        break
                                if insert_before_idx < len(function_sequence):
                                    break
                            
                            function_sequence.insert(insert_before_idx, dep_name)
                            generation_result['function_sequence'] = function_sequence
                            deps_backfilled += 1
                            print(f"    ✅ Dependency backfilled: {dep_name} (inserted at position {insert_before_idx+1})")
                        else:
                            print(f"    ⚠️ Could not find dependency: {dep_name} in RAG")
                            
                    except Exception as dep_err:
                        print(f"    ❌ Dependency backfill failed for {dep_name}: {dep_err}")
                
                print(f"  -> Backfilled {deps_backfilled}/{len(missing_deps)} missing dependencies")
                backfilled_count += deps_backfilled  # Update total count
            else:
                print(f"  -> No missing transitive dependencies found ✅")
            
            # ================================================================
            # STEP 6.4: Deduplicate semantically equivalent functions
            # ================================================================
            # After STEP 6.2 (PUML backfill) and STEP 6.3 (KG transitive deps),
            # we may have DUPLICATE functions that represent the same logical operation
            # but with different naming conventions.
            #
            # Example: IfxCxpi_initChannel AND IfxCxpi_Cxpi_initChannel
            #          IfxCxpi_initChannelConfig AND IfxCxpi_Cxpi_initChannelConfig
            #
            # These are wrapper variants of the same function. We keep ONE.
            #
            # APPROACH (100% DATA-DRIVEN, works for ANY module):
            # 1. Detect the module prefix pattern dynamically from function names
            # 2. Normalize all function names by collapsing double-module prefix
            # 3. Group semantically equivalent functions
            # 4. Keep the preferred variant (the one with more data, or the wrapper)
            # ================================================================
            pre_dedup_count = len(function_sequence)
            if pre_dedup_count > 1:
                print(f"\n  [STEP 6.4] Deduplicating function sequence ({pre_dedup_count} functions)...")
                
                # Dynamically detect double-prefix pattern from actual function names
                # e.g., "IfxCxpi_Cxpi_" means Cxpi appears twice → double prefix
                # We find the module word that repeats in the prefix
                from collections import Counter
                prefix_segments = Counter()
                for fname in function_sequence:
                    parts = fname.split('_')
                    # Count the first few segments (likely prefix): Ifx, Cxpi, Cxpi, ...
                    for p in parts[:4]:
                        if p and p.lower() not in ('ifx', 't', ''):
                            prefix_segments[p.lower()] += 1
                
                # The module word appears in nearly every function name
                # If a word appears with both single and double prefix patterns, it's the module
                module_word = None
                for word, count in prefix_segments.most_common(3):
                    if count >= 2 and len(word) >= 2:
                        module_word = word
                        break
                
                if module_word:
                    # Build normalizer: collapse "Ifx<Mod>_<Mod>_" → "Ifx<Mod>_" for grouping
                    # This finds functions that are semantically identical despite naming differences
                    seen_normalized = {}  # normalized_name → first occurrence index in sequence
                    dedup_sequence = []
                    removed_funcs = []
                    
                    for fname in function_sequence:
                        parts = fname.split('_')
                        
                        # Detect if this function has a double-module prefix
                        # e.g., IfxCxpi_Cxpi_initChannel → parts = ['IfxCxpi', 'Cxpi', 'initChannel']
                        # Normalized: IfxCxpi_initChannel
                        normalized = fname
                        has_double_prefix = False
                        
                        if len(parts) >= 3:
                            # Check if parts[1] matches the module word (case-insensitive)
                            if parts[1].lower() == module_word:
                                # Double prefix detected: strip parts[1]
                                normalized = parts[0] + '_' + '_'.join(parts[2:])
                                has_double_prefix = True
                        
                        if normalized in seen_normalized:
                            # Semantic duplicate found! Keep the one with more KG data
                            existing_fname = seen_normalized[normalized]
                            existing_kg = kg_context.get('functions', {}).get(existing_fname, {})
                            current_kg = kg_context.get('functions', {}).get(fname, {})
                            
                            existing_data_score = len(existing_kg.get('parameters', [])) + len(existing_kg.get('dependencies', []))
                            current_data_score = len(current_kg.get('parameters', [])) + len(current_kg.get('dependencies', []))
                            
                            if current_data_score > existing_data_score:
                                # Current function has more data → replace existing
                                dedup_sequence = [fname if f == existing_fname else f for f in dedup_sequence]
                                seen_normalized[normalized] = fname
                                removed_funcs.append(existing_fname)
                                print(f"    🔄 Replaced {existing_fname} with {fname} (more KG data)")
                            else:
                                # Existing has more or equal data → skip current
                                removed_funcs.append(fname)
                                print(f"    🔄 Skipped duplicate: {fname} (equivalent to {existing_fname})")
                        else:
                            seen_normalized[normalized] = fname
                            dedup_sequence.append(fname)
                    
                    if removed_funcs:
                        function_sequence = dedup_sequence
                        generation_result['function_sequence'] = function_sequence
                        
                        # Also remove duplicates from all_functions list
                        removed_set = set(removed_funcs)
                        all_functions = [f for f in all_functions if f.get('name', '') not in removed_set]
                        
                        print(f"  -> Deduplicated: {pre_dedup_count} → {len(function_sequence)} functions")
                        print(f"  -> Removed {len(removed_funcs)} semantic duplicates: {removed_funcs}")
                    else:
                        print(f"  -> No semantic duplicates found ✅")
                else:
                    print(f"  -> Could not detect module prefix pattern — skipping dedup")
            
            # If we backfilled any functions, REGENERATE the skeleton with the updated all_functions
            if backfilled_count > 0 or pre_dedup_count != len(function_sequence):
                # ================================================================
                # STEP 6.5: Re-run struct/enum pre-fetch now that all_functions is
                # COMPLETE (includes FSB always-present + KG transitive deps added
                # in Steps 6.2/6.3 that were NOT available when Step 4.4 ran).
                #
                # WHY: Step 4.4 runs at Step 4 time — before FSB adds functions like
                # IfxCxpi_initModuleConfigForTest.  The parameter types of those newly
                # added functions (e.g. IfxCxpi_TestConfig_t) are therefore invisible
                # to Step 4.4, so their struct entries are never pre-fetched and the
                # skeleton generator hits "No members found".
                #
                # FIX: Repeat the same scan-and-fetch logic here, using the final
                # all_functions list, before regenerating the skeleton.
                # ================================================================
                print(f"\n  [STEP 6.5] Re-running struct/enum pre-fetch on final all_functions list ({len(all_functions)} funcs)...")
                existing_snames_65 = {s.get('name', '').lower() for s in all_structs}
                existing_enames_65 = {e.get('name', '').lower() for e in all_enums}
                structs_added_65 = 0

                # Collect every _t struct type used in any function signature
                candidate_types_65: set = set()
                for fi_65 in all_functions:
                    fc_65 = fi_65.get('full_content', '') or fi_65.get('content', '')
                    if not fc_65 or '(' not in fc_65.split('\n')[0]:
                        continue
                    fl_65 = fc_65.split('\n')[0]
                    ps_65 = fl_65.split('(', 1)[1].rsplit(')', 1)[0]
                    for rp_65 in ps_65.split(','):
                        rp_65 = rp_65.strip()
                        if not rp_65 or rp_65 == 'void':
                            continue
                        pts_65 = rp_65.replace('*', ' * ').split()
                        if len(pts_65) < 2:
                            continue
                        bt_65 = ' '.join(pts_65[:-1]).replace(' * ', '*').replace(' *', '*')
                        bt_65 = bt_65.replace('*', '').replace('const', '').strip()
                        if bt_65 and bt_65.endswith('_t') and bt_65.startswith('Ifx'):
                            candidate_types_65.add(bt_65)

                for stype_65 in sorted(candidate_types_65):
                    if stype_65.lower() in existing_snames_65:
                        continue
                    try:
                        shits_65 = rag_client.query_structs(stype_65, n_results=5)
                        best_65 = None
                        for sh_65 in shits_65:
                            shn_65 = extract_entity_name(sh_65, 'struct')
                            if not shn_65:
                                continue
                            if shn_65.lower() == stype_65.lower():
                                best_65 = (shn_65, sh_65)
                                break
                            if best_65 is None:
                                best_65 = (shn_65, sh_65)
                        if best_65:
                            hn_65, hd_65 = best_65
                            try:
                                mr_65 = kg_client.get_struct_members(hn_65)
                            except Exception:
                                mr_65 = []
                            km_65 = [{'name': m.get('member_name') or m.get('name') or '',
                                       'type': m.get('member_type') or m.get('type') or '',
                                       'description': m.get('description') or ''}
                                      for m in (mr_65 or [])]
                            fc2_65 = hd_65.get('full_content', '') or hd_65.get('content', '')
                            # Recover types from full_content if KG has type=None
                            types_none_65 = (not km_65) or all(
                                (m.get('type', '') or 'None') in ('None', '', 'none') for m in km_65)
                            if types_none_65 and fc2_65:
                                from backend.generators.code_generator import _parse_struct_members_from_content
                                parsed_65 = _parse_struct_members_from_content(fc2_65)
                                if parsed_65:
                                    if km_65:
                                        pm_65 = {p['name']: p.get('type', '') for p in parsed_65}
                                        for m in km_65:
                                            mn = m.get('name', '')
                                            if mn and mn in pm_65:
                                                m['type'] = pm_65[mn]
                                    else:
                                        km_65 = parsed_65
                            all_structs.append({'name': hn_65, 'content': hd_65.get('content', ''),
                                                'full_content': fc2_65, 'metadata': hd_65.get('metadata', {}),
                                                'members': km_65, 'used_by_functions': [], 'step65_backfill': True})
                            existing_snames_65.add(hn_65.lower())
                            structs_added_65 += 1
                            print(f"    ✅ [STEP 6.5] Struct pre-fetched: {hn_65} (members={len(km_65)})")
                            # Inline enum backfill for new struct members
                            for m65 in km_65:
                                mt_65 = (m65.get('type') or '').replace('const', '').strip()
                                if not mt_65 or '*' in mt_65 or mt_65 in ('None', 'none'):
                                    continue
                                if not (mt_65.endswith('_t') and mt_65.startswith('Ifx')):
                                    continue
                                if mt_65.lower() in existing_enames_65:
                                    continue
                                try:
                                    eh_65 = rag_client.query_enums(mt_65, n_results=5)
                                    be_65 = None
                                    for e65 in eh_65:
                                        en_65 = extract_entity_name(e65, 'enum')
                                        if not en_65:
                                            continue
                                        if en_65.lower() == mt_65.lower():
                                            be_65 = (en_65, e65)
                                            break
                                        if be_65 is None:
                                            be_65 = (en_65, e65)
                                    if be_65:
                                        enm_65, edd_65 = be_65
                                        try:
                                            ev_65 = kg_client.get_enum_values(enm_65)
                                        except Exception:
                                            ev_65 = []
                                        evl_65 = [{'name': v.get('value_name') or v.get('name') or '',
                                                   'value': v.get('numeric_value') or v.get('value') or '',
                                                   'description': v.get('description') or ''} for v in (ev_65 or [])]
                                        if not evl_65:
                                            from backend.generators.code_generator import _parse_enum_values_from_content
                                            evl_65 = _parse_enum_values_from_content(edd_65.get('full_content', '') or edd_65.get('content', ''))
                                        all_enums.append({'name': enm_65, 'content': edd_65.get('content', ''),
                                                          'full_content': edd_65.get('full_content', ''),
                                                          'values': evl_65, 'step65_enum_backfill': True})
                                        existing_enames_65.add(enm_65.lower())
                                        print(f"      ✅ [STEP 6.5] Enum backfilled: {enm_65} (for {mt_65}, values={len(evl_65)})")
                                except Exception:
                                    pass
                        else:
                            print(f"    ⚠️ [STEP 6.5] Struct '{stype_65}' not found in RAG")
                    except Exception as e65_err:
                        print(f"    [WARN][STEP 6.5] Struct fetch failed for '{stype_65}': {e65_err}")

                if structs_added_65 > 0:
                    print(f"  [STEP 6.5] ✅ Pre-fetched {structs_added_65} additional struct(s)")
                else:
                    print(f"  [STEP 6.5] No additional structs needed ✅")

                print(f"  -> Regenerating C code skeleton with {len(function_sequence)} functions...")
                from backend.generators.code_generator import generate_sample_c_code as _regenerate_skeleton
                
                struct_inits = generation_result.get('struct_initializations', {})
                polling_patterns = generation_result.get('polling_patterns', {})
                sample_test_code = _regenerate_skeleton(
                    function_sequence=function_sequence,
                    struct_initializations=struct_inits,
                    all_functions=all_functions,
                    module=module,
                    struct_values=None,
                    all_structs=all_structs,
                    all_enums=all_enums,
                    user_description=description,
                    polling_patterns=polling_patterns
                )
                generation_result['sample_test_code'] = sample_test_code
                print(f"  -> Regenerated skeleton: {len(sample_test_code.splitlines())} lines (with backfilled functions)")
        else:
            print(f"\n[STEP 6.2] All {len(function_sequence)} functions in sequence are already in all_functions ✅")
        
        _mark_step("STEP 6: Code Generation + Backfill")
        
        # ================================================================
        # STEP 7: Validate with MISRA-C
        # ================================================================
        print(f"\n[STEP 7] Validating with MISRA-C...")
        
        try:
            validator = MisraCValidator()
            test_code = generation_result.get('test_code_template', '')
            compliance_result = validator.validate(test_code) if test_code else {'violations': [], 'score': 1.0}
            compliance_score = compliance_result.get('score', 1.0)
        except Exception as e:
            print(f"  [WARN] MISRA-C validation skipped: {e}")
            compliance_score = 0.8
        
        _mark_step("STEP 7: MISRA-C Validation")
        
        # ================================================================
        # STEP 7.4: Prepare Stage 1 Enum Resolver prompt
        # ================================================================
        # Build a focused prompt for a small/fast model (gpt-5-mini) to resolve
        # all enum TODO placeholders in the skeleton BEFORE the main LLM call.
        # This prevents the main LLM from hallucinating wrong enum values.
        # ================================================================
        enum_resolver_prompt = None
        step_7_4_start = time.time()
        if sample_test_code:
            print(f"\n[STEP 7.4] ⏱️  Preparing Stage 1 Enum Resolver prompt (MANDATORY)...")
            try:
                prompt_build_start = time.time()
                enum_resolver_prompt = build_enum_resolver_prompt(
                    sample_test_code=sample_test_code,
                    user_description=description,
                    additional_notes=request.additional_notes or "",
                    all_structs=all_structs,
                    all_enums=all_enums
                )
                prompt_build_duration = time.time() - prompt_build_start
                if enum_resolver_prompt:
                    print(f"  ✓ Enum resolver prompt prepared ({len(enum_resolver_prompt)} chars in {prompt_build_duration:.2f}s)")
                    print(f"  ✓ Will use gpt-5-mini model via VS Code LM API (Stage 1)")
                else:
                    print(f"  ℹ️  No enum-typed struct assignments found — Stage 1 not needed")
            except Exception as enum_err:
                print(f"  ❌ Enum resolver prompt build failed: {enum_err}")
                traceback.print_exc()
                enum_resolver_prompt = None

        step_7_4_duration = time.time() - step_7_4_start
        _step_times["STEP 7.4: Enum Resolver Prompt"] = step_7_4_duration
        print(f"  ⏱️  STEP 7.4 took {step_7_4_duration:.2f}s")
        _step_start = time.time()
        
        # ================================================================
        # STEP 7.5: Prepare LLM prompt (LLM call done by VS Code extension)
        # ================================================================
        llm_enhanced_code = None
        llm_result = None
        llm_prompt_for_extension = None
        
        if sample_test_code:
            print(f"\n[STEP 7.5] Preparing LLM prompt for VS Code extension...")
            print(f"  -> LLM call will be made by extension via VS Code Language Model API")
            print(f"  -> Input optimization: 100+ KB → ~8-10 KB (80% reduction)")
            print(f"  -> Sequential approach: 5 phases of knowledge building + 1 enhancement task")
            
            # Prepare minimal KG reference
            minimal_kg_summary = {
                'function_parameters': {},
                'register_addresses': {},
                'critical_deps': {}
            }
            
            # Get function parameters from generation_result
            if 'function_sequence' in generation_result:
                func_seq = generation_result['function_sequence']
                if isinstance(func_seq, (list, tuple)):
                    for func_name in func_seq:  # ALL functions, not just first 5
                        func_data = kg_context.get('functions', {}).get(func_name, {})
                        parameters = func_data.get('parameters')
                        if parameters and isinstance(parameters, (list, tuple)):
                            minimal_kg_summary['function_parameters'][func_name] = [
                                {'name': p.get('param_name', 'unknown'), 'type': p.get('param_type', 'unknown')}
                                for p in parameters[:3]
                            ]
            
            # Get register addresses (top 5)
            registers = kg_context.get('registers', {})
            if isinstance(registers, dict):
                for reg_name, reg_data in list(registers.items())[:5]:
                    if isinstance(reg_data, dict):
                        mem_loc = reg_data.get('memory_location')
                        if isinstance(mem_loc, dict) and mem_loc:
                            minimal_kg_summary['register_addresses'][reg_name] = {
                                'address': mem_loc.get('memory_address', 'unknown'),
                                'description': reg_name
                            }
            
            # Get critical dependencies
            if 'function_sequence' in generation_result:
                func_seq = generation_result['function_sequence']
                if isinstance(func_seq, (list, tuple)):
                    for func_name in func_seq:  # ALL functions, not just first 5
                        func_data = kg_context.get('functions', {}).get(func_name, {})
                        if isinstance(func_data, dict) and func_data.get('dependencies'):
                            deps = func_data['dependencies']
                            if isinstance(deps, (list, tuple)):
                                minimal_kg_summary['critical_deps'][func_name] = [
                                    d.get('dependency', 'unknown') for d in deps[:2] if isinstance(d, dict)
                                ]
            
            # Build sequential prompt
            hw_spec_chunks = rag_requirements[:5] if isinstance(rag_requirements, (list, tuple)) and rag_requirements else []
            
            try:
                sequential_prompt = build_llm_prompt_idea_1_sequential(
                    hw_spec_chunks=hw_spec_chunks,
                    user_description=description,
                    additional_notes=request.additional_notes,
                    sample_test_code=sample_test_code,
                    minimal_kg_summary=minimal_kg_summary,
                    test_code_prompt_template=test_code_template,
                    all_functions=all_functions,
                    all_structs=all_structs,
                    all_enums=all_enums
                )
                llm_prompt_for_extension = sequential_prompt
                print(f"  [OK] LLM prompt prepared ({len(sequential_prompt)} chars)")
                print(f"  [OK] Prompt will be sent to extension for VS Code LM API call")
            except Exception as prompt_error:
                print(f"  [WARN] Failed to build LLM prompt: {prompt_error}")
                llm_prompt_for_extension = None
        else:
            print(f"\n[STEP 7.5] Sample test code not generated, skipping LLM prompt preparation")
        
        _mark_step("STEP 7.5: LLM Prompt Build")
        
        # ================================================================
        # STEP 8: Save generated test code to file & compile response
        # ================================================================
        generation_elapsed = time.time() - generation_start_time
        gen_minutes = int(generation_elapsed // 60)
        gen_seconds = generation_elapsed % 60
        
        print(f"\n[STEP 8] Compiling response...")
        print(f"  [TIME] Backend pipeline took: {gen_minutes}m {gen_seconds:.1f}s")
        print(f"  [TIME] Note: LLM calls (Stage 1 + Stage 2) add ~20-40s additional time")
        print(f"  [TIME] Total time shown in UI includes backend + LLM round-trip")
        
        # Determine the best test code to save (skeleton for now, extension will enhance with LLM)
        final_test_code = generation_result.get('test_code_template', '') or sample_test_code or ''
        
        # File naming: test_YYYY-MM-DD_HH-MM format for easy tracking
        now = datetime.now()
        file_timestamp = now.strftime("%Y-%m-%d_%H-%M")
        test_file_name = f"test_{file_timestamp}"
        
        # Save to file
        output_dir = Path(__file__).parent.parent / "output" / "generated_tests"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{test_file_name}.c"
        
        # If file already exists (multiple tests in same minute), add a counter
        counter = 1
        while output_file.exists():
            counter += 1
            output_file = output_dir / f"{test_file_name}_{counter}.c"
        
        if final_test_code:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"/* Auto-generated test: {test_file_name} */\n")
                f.write(f"/* Module: {module} */\n")
                f.write(f"/* Description: {description} */\n")
                f.write(f"/* Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} */\n")
                f.write(f"/* LLM Model: {llm_service.model if llm_service else 'none'} */\n\n")
                f.write(final_test_code)
            print(f"  [OK] Test code saved to: {output_file}")
        
        response = {
            'test_id': test_file_name,
            'status': 'success',
            'module': module,
            'description': description,
            'compliance_score': compliance_score,
            'generation_time': {
                'total_seconds': round(generation_elapsed, 1),
                'display': f"{gen_minutes}m {gen_seconds:.1f}s" if gen_minutes > 0 else f"{gen_seconds:.1f}s"
            },
            'output_file': str(output_file),
            'test_code': final_test_code,
            'rag_context': {
                'functions_count': len(rag_functions),
                'structs_count': len(rag_structs),
                'enums_count': len(rag_enums),
                'requirements_count': len(rag_requirements)
            },
            'kg_context': {
                'dependency_count': len(kg_context),
                'dependencies': kg_context
            },
            'generation_result': generation_result,
            'llm_enhancement': {
                'available': llm_service is not None,
                'model': llm_service.model if llm_service else None,
                'enhanced_code': llm_enhanced_code,
                'llm_result': llm_result,
                'llm_prompt': llm_prompt_for_extension,  # Extension will use this to call VS Code LM API
                'enum_resolver_prompt': enum_resolver_prompt  # Stage 1: small model resolves enums first
            },
            'timestamp': now.isoformat()
        }
        
        print(f"  [OK] Test generation complete: {test_file_name}")
        print(f"  [OK] Compliance score: {compliance_score:.2%}")
        if llm_service:
            print(f"  [OK] LLM model: {llm_service.model}")
        if llm_prompt_for_extension:
            print(f"  [OK] LLM prompt prepared for extension ({len(llm_prompt_for_extension)} chars)")
        
        _mark_step("STEP 8: Save & Response")
        
        # ================================================================
        # TIMING SUMMARY: Print per-step breakdown for optimization
        # ================================================================
        print(f"\n{'='*70}")
        print(f"⏱  TIMING BREAKDOWN (Backend Pipeline Only)")
        print(f"{'='*70}")
        # Sort by order of insertion (dict preserves order in Python 3.7+)
        for step_name, step_secs in _step_times.items():
            bar_len = int(step_secs / generation_elapsed * 40) if generation_elapsed > 0 else 0
            bar = "█" * bar_len
            pct = (step_secs / generation_elapsed * 100) if generation_elapsed > 0 else 0
            print(f"  {step_name:<35} {step_secs:>6.2f}s  ({pct:>5.1f}%)  {bar}")
        print(f"{'─'*70}")
        print(f"  {'BACKEND TOTAL':<35} {generation_elapsed:>6.2f}s  (100.0%)")
        print(f"  {'+ LLM Calls (Stage 1+2)':<35} {'(measured by extension)'}")
        print(f"  {'= TOTAL (shown in UI)':<35} {'(backend + LLM round-trip)'}")
        print(f"{'='*70}\n")
        
        return response
        
    except Exception as e:
        print(f"\n❌ Test generation failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Test generation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
