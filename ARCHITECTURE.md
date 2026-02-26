# GEST Domain Assistant v1 — Architecture & How It Works

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Component Breakdown](#component-breakdown)
   - [VS Code Extension (Frontend)](#vs-code-extension-frontend)
   - [FastAPI Backend](#fastapi-backend)
   - [Database Layer](#database-layer)
4. [Test Generation Pipeline](#test-generation-pipeline)
5. [Data Flow Diagram](#data-flow-diagram)
6. [Key Modules In Depth](#key-modules-in-depth)
   - [RAG Client (ChromaDB)](#rag-client-chromadb)
   - [KG Client (Neo4j)](#kg-client-neo4j)
   - [Code Generator](#code-generator)
   - [LLM Service](#llm-service)
   - [PUML Pattern Analyzer](#puml-pattern-analyzer)
   - [Source Code Analyzer](#source-code-analyzer)
   - [MISRA-C Validator](#misra-c-validator)
   - [Hybrid Cache](#hybrid-cache)
7. [Two-Stage LLM Enhancement](#two-stage-llm-enhancement)
8. [Extension–Backend Communication](#extensionbackend-communication)
9. [Configuration & Environment](#configuration--environment)
10. [Directory Structure](#directory-structure)

---

## Overview

**GEST Domain Assistant** (GEnerate Semantic Tests) is an AI-powered test code generation system for embedded C/C++ software modules (e.g., CXPI, LIN, CAN automotive communication protocols). It takes a **natural language description** of a desired test scenario and produces **production-ready MISRA-C compliant test code** by combining:

| Technique | Purpose |
|-----------|---------|
| **RAG** (Retrieval-Augmented Generation) | Semantic search over 12 ChromaDB collections for functions, structs, enums, requirements, hardware specs, etc. |
| **Knowledge Graph** | Neo4j graph traversal across 22+ relationship types (DEPENDS_ON, CALLS_INTERNALLY, HAS_PARAMETER, HAS_MEMBER, etc.) |
| **LLM Enhancement** | Two-stage pipeline using VS Code's Language Model API (GitHub Copilot models) |
| **Pattern Library** | PUML-derived phase patterns and function priority metadata for correct test structure |
| **MISRA-C Validation** | Static analysis with regex-based and optional clang-based compliance checking |

The system is **fully dynamic** — zero hardcoding of module names, function names, or struct definitions. Everything is data-driven from the ingested RAG and KG databases.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VS Code IDE                                  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              TEST_MANAGEMENT_EXTENSION                        │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐      │  │
│  │  │  Webview UI  │  │ LLM Gateway  │  │ File Generator │      │  │
│  │  │  (Galaxy     │  │ (VS Code LM  │  │ (.c, .h, .md)  │      │  │
│  │  │   Theme)     │  │  API calls)  │  │                │      │  │
│  │  └──────┬───────┘  └──────┬───────┘  └────────────────┘      │  │
│  │         │                 │                                    │  │
│  │  ┌──────┴─────────────────┴───────┐                           │  │
│  │  │      WebviewManager            │                           │  │
│  │  │  (Message routing, Stage 1+2)  │                           │  │
│  │  └──────────────┬─────────────────┘                           │  │
│  │                 │                                              │  │
│  │  ┌──────────────┴─────────────────┐                           │  │
│  │  │      BackendClient (Axios)     │                           │  │
│  │  │  HTTP ↔ FastAPI (port 8000)    │                           │  │
│  │  └──────────────┬─────────────────┘                           │  │
│  └─────────────────┼─────────────────────────────────────────────┘  │
└────────────────────┼────────────────────────────────────────────────┘
                     │ HTTP REST
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TEST_MANAGEMENT_APP                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    FastAPI Backend (app.py)                     │ │
│  │                                                                │ │
│  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌──────────┐ │ │
│  │  │ RAG Client │ │ KG Client  │ │ Code Gen     │ │ LLM Svc  │ │ │
│  │  │ (ChromaDB) │ │ (Neo4j)    │ │ (Data-Driven)│ │ (Copilot)│ │ │
│  │  └─────┬──────┘ └─────┬──────┘ └──────┬───────┘ └──────────┘ │ │
│  │        │               │               │                       │ │
│  │  ┌─────┴──────┐ ┌─────┴──────┐ ┌──────┴───────┐              │ │
│  │  │ PUML       │ │ Source     │ │ MISRA-C      │              │ │
│  │  │ Analyzer   │ │ Analyzer   │ │ Validator    │              │ │
│  │  └────────────┘ └────────────┘ └──────────────┘              │ │
│  │                                                                │ │
│  │  ┌─────────────────────────────────────────┐                  │ │
│  │  │  HybridCache (LRU + SQLite Persistence) │                  │ │
│  │  └─────────────────────────────────────────┘                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                     │                     │                         │
│              ┌──────┴──────┐       ┌──────┴──────┐                 │
│              │  ChromaDB   │       │   Neo4j     │                 │
│              │  (SQLite +  │       │  (Graph DB) │                 │
│              │   HNSW)     │       │             │                 │
│              └─────────────┘       └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### VS Code Extension (Frontend)

The extension (`TEST_MANAGEMENT_EXTENSION/`) provides the user interface inside VS Code.

| File | Responsibility |
|------|---------------|
| `extension.ts` | Extension entry point. Registers commands, initializes clients, discovers LLM models via `vscode.lm.selectChatModels()`, and sends them to the backend. |
| `backend/client.ts` | HTTP client (Axios) wrapping all REST calls to the FastAPI backend. 120s timeout for long-running generation. |
| `ui/webviewContent.ts` | Full HTML/CSS/JS for the "GEST Assistant" panel (Galaxy particle theme). Includes module selector, description textarea, LLM model picker, generate button, and result metrics display. |
| `ui/webview.ts` | `WebviewManager` — orchestrates the webview panel lifecycle, message routing, and the **two-stage LLM enhancement pipeline** (Stage 1: enum resolution via gpt-5-mini, Stage 2: code enhancement via user-selected model). |
| `ui/sidebarViewProvider.ts` | Sidebar launcher that auto-opens the full panel in the editor area. |
| `generators/fileGenerator.ts` | Generates `.c` test file, `.h` header, and `.md` documentation from the generation result. |

**Key Extension Commands:**
- `testManagement.showPanel` — Open the test generator UI
- `testManagement.generateTest` — Generate a test (optionally with pre-filled description)
- `testManagement.selectModule` — Pick the target module (cxpi, lin, btl, can)
- `testManagement.switchModel` — Change the active LLM model

### FastAPI Backend

The backend (`TEST_MANAGEMENT_APP/backend/`) is a Python FastAPI server running on port 8000.

**REST API Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check — returns RAG/KG connection status |
| `/modules` | GET | Dynamically discovers available modules from ChromaDB collections |
| `/generate_test` | POST | **Main endpoint** — full test generation pipeline |
| `/query/functions` | POST | Query functions from RAG |
| `/query/enums` | POST | Query enum definitions from RAG |
| `/query/structs` | POST | Query struct definitions from RAG |
| `/query/requirements` | POST | Query requirements from RAG |
| `/query/dependencies` | POST | Get function dependencies from KG |
| `/query/calls` | POST | Get functions called by a function from KG |
| `/query/parameters` | POST | Get function parameters from KG |
| `/llm/models` | GET | List available LLM models |
| `/llm/update-models` | POST | Receive model list from VS Code extension |
| `/llm/select-model` | POST | Switch the active LLM model |
| `/apply_enum_resolution` | POST | Apply Stage 1 resolved enum values to skeleton code |
| `/validate_generated_code` | POST | Run post-generation quality checks |

### Database Layer

| Database | Technology | Contents |
|----------|-----------|----------|
| **ChromaDB** | SQLite + HNSW vector index | 12 semantic collections per module: functions, enums, structs, requirements, hardware, registers, macros, typedefs, source, architecture, pattern_library, phases |
| **Neo4j** | Graph Database | Knowledge graph with 22+ relationship types: DEPENDS_ON, CALLS_INTERNALLY, HAS_PARAMETER, OF_TYPE, HAS_MEMBER, HAS_VALUE, IMPLEMENTS, HAS_CASE, HAS_BITFIELD, LOCATED_AT, CONTROLS, TRIGGERED_BY, DETECTED_BY, ALIASES, USED_IN, etc. |

---

## Test Generation Pipeline

The `/generate_test` endpoint executes a multi-step pipeline. Here is the complete step-by-step flow:

### Step 0: Load Pattern Library
- Loads PUML pattern library from RAG database (2 essential chunks: `core_functions` and `phase_patterns`)
- Extracts code generation rules: which functions are always/frequently/rarely present, phase structure, typical sequences

### Step 1: RAG Queries (Comprehensive Context)
Queries **all 12 ChromaDB collections** for context relevant to the user's description:

| Collection | Chunks Retrieved | Purpose |
|------------|-----------------|---------|
| Functions | Top 10 | C function definitions with signatures |
| Structs | Top 10 | Data structure definitions |
| Enums | Top 10 | Enumeration type definitions |
| Requirements | Top 8 | System requirements & traceability |
| Hardware | Top 8 | Hardware specifications (from PDFs) |
| Registers | Top 8 | Register definitions |
| Macros | Top 5 | Macro definitions |
| Typedefs | Top 5 | Type definitions |
| Pattern Library | ALL 8 | Interconnected PUML patterns (complete fetch) |
| Source | Best effort | Source code implementations |

**NLP-powered query expansion** normalizes abbreviations (TX→transmit, init→initialize), adds synonyms via WordNet, and applies domain-specific mappings for automotive protocols.

### Step 2: KG Queries (22+ Relationship Types)
For every entity found by RAG, queries Neo4j for all applicable relationships:

- **Functions** → DEPENDS_ON, CALLS_INTERNALLY, HAS_PARAMETER, OF_TYPE, IMPLEMENTS, HAS_CASE
- **Structs** → HAS_MEMBER, HAS_FIELD, USED_BY
- **Enums** → HAS_VALUE, INDICATES
- **Requirements** → IMPLEMENTED_BY
- **Registers** → HAS_BITFIELD, LOCATED_AT, HAS_FIELD, CONTROLS
- **Typedefs** → ALIASES, USED_IN
- **Hardware** → TRIGGERED_BY, DETECTED_BY

### Step 3: Source Analysis (Post-Selection)
Analyzes **only the selected functions** (not the entire module) for internal call relationships:
- `CALLS_INTERNALLY` — prevents duplicate function calls in the test
- `HAS_CASE` — identifies dispatcher functions with switch variants
- `DEPENDS_ON` — function dependency ordering

### Step 4: Context Preparation & Backfill
Merges RAG content with KG context (parameters, members, values) into unified data structures. Includes intelligent backfill sub-steps:

- **Step 4.1**: Proactively ensures status/polling functions are available (e.g., `getChannelStatus`)
- **Step 4.2**: Backfills config struct definitions needed by config functions
- **Step 4.3**: Backfills enum types for config struct members
- **Step 4.4**: Pre-fetches any struct type referenced in function signatures

### Step 5: Feature Classification
Uses **primary RAG semantic similarity** (384-dim embeddings, ~95% accuracy) with PUML core functions as secondary validation. Classifies detected functions into phases:
- **Initialization phase**: init, setup, config functions
- **Operation phase**: transmit, receive, process functions  
- **Cleanup phase**: reset, clear, disable functions

### Step 6: Code Generation
The `DataDrivenCodeGenerator` builds a complete C test skeleton:
1. Generates `#include` directives
2. Initializes config structs with real member values from KG
3. Arranges function calls in phase order (init → operation → cleanup)
4. Adds polling patterns and error handling
5. Inserts requirement traceability comments

### Step 7: LLM Prompt Construction
Builds the system prompt using the `test_code_prompt.md` template and the generated skeleton code. Also builds a separate enum resolver prompt for Stage 1.

### Step 8: MISRA-C Validation
Validates the generated code against MISRA-C 2012 rules (14 priority rules). Uses regex-based analysis and optionally clang static analyzer.

### Step 9: Save & Return
Saves the test file to `output/generated_tests/` and returns the complete result with metrics.

---

## Data Flow Diagram

```
User types: "Test CXPI transmit with CRC error injection"
                    │
                    ▼
   ┌────────────────────────────────┐
   │   VS Code Extension Webview    │
   │   (module=cxpi, model=gpt-4)  │
   └───────────────┬────────────────┘
                   │ POST /generate_test
                   ▼
   ┌────────────────────────────────┐
   │        FastAPI Backend         │
   │                                │
   │  ┌──────────────────────────┐  │
   │  │ STEP 1: RAG Queries      │  │
   │  │ "transmit CRC error" →   │  │
   │  │  NLP expansion →         │  │
   │  │  384-dim embedding →     │  │
   │  │  HNSW cosine search      │  │
   │  │  across 12 collections   │  │
   │  └───────────┬──────────────┘  │
   │              │                  │
   │  ┌───────────▼──────────────┐  │
   │  │ STEP 2: KG Queries       │  │
   │  │ For each RAG result →    │  │
   │  │  Cypher queries for      │  │
   │  │  22+ relationship types  │  │
   │  └───────────┬──────────────┘  │
   │              │                  │
   │  ┌───────────▼──────────────┐  │
   │  │ STEP 3: Source Analysis   │  │
   │  │ Call graph for selected   │  │
   │  │ functions only            │  │
   │  └───────────┬──────────────┘  │
   │              │                  │
   │  ┌───────────▼──────────────┐  │
   │  │ STEP 4: Context Merge     │  │
   │  │ + Backfill missing        │  │
   │  │ structs/enums             │  │
   │  └───────────┬──────────────┘  │
   │              │                  │
   │  ┌───────────▼──────────────┐  │
   │  │ STEP 5: Classification    │  │
   │  │ RAG similarity ranking    │  │
   │  │ + phase ordering          │  │
   │  └───────────┬──────────────┘  │
   │              │                  │
   │  ┌───────────▼──────────────┐  │
   │  │ STEP 6: Code Generation   │  │
   │  │ DataDrivenCodeGenerator   │  │
   │  │ → C test skeleton         │  │
   │  └───────────┬──────────────┘  │
   │              │                  │
   │  ┌───────────▼──────────────┐  │
   │  │ STEP 7: Build LLM Prompt  │  │
   │  │ template + skeleton       │  │
   │  │ + enum resolver prompt    │  │
   │  └──────────┬───────────────┘  │
   │             │                   │
   └─────────────┼───────────────────┘
                 │ Response (skeleton + prompts)
                 ▼
   ┌─────────────────────────────────┐
   │  VS Code Extension              │
   │                                  │
   │  ┌───────────────────────────┐   │
   │  │ STAGE 1: Enum Resolution  │   │
   │  │ gpt-5-mini resolves       │   │
   │  │ /* TODO: enum */ markers   │   │
   │  │ → JSON { task: value }     │   │
   │  └───────────┬───────────────┘   │
   │              │ POST /apply_enum  │
   │              ▼                    │
   │  ┌───────────────────────────┐   │
   │  │ STAGE 2: Code Enhancement │   │
   │  │ User-selected model        │   │
   │  │ (e.g., Claude, GPT-4)     │   │
   │  │ enhances skeleton →        │   │
   │  │ production-ready code      │   │
   │  └───────────┬───────────────┘   │
   │              │                    │
   │  ┌───────────▼───────────────┐   │
   │  │ Save .c file + display    │   │
   │  │ metrics in webview         │   │
   │  └───────────────────────────┘   │
   └──────────────────────────────────┘
```

---

## Key Modules In Depth

### RAG Client (ChromaDB)

**File:** `backend/database/rag_client.py`  
**Purpose:** Semantic search over pre-ingested C code knowledge

- **Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions), loaded from local cache
- **Index:** HNSW (Hierarchical Navigable Small Worlds) for O(log n) approximate nearest neighbor search
- **Distance Metric:** Cosine similarity
- **Storage:** ChromaDB backed by SQLite + binary embedding files
- **Query Expansion:** NLP pipeline using NLTK — lemmatization, WordNet synonyms, domain-specific abbreviation mapping (TX→transmit, RX→receive, init→initialize, hw→hardware, etc.)
- **Collection Pattern:** `rag_{module}_{type}` (e.g., `rag_cxpi_functions`, `rag_swa_enums`)

### KG Client (Neo4j)

**File:** `backend/database/kg_client.py`  
**Purpose:** Structured relationship queries for dependencies, types, and traceability

- **Database naming:** `{module}db` (e.g., `cxpidb`, `lindb`)
- **Node types:** Function, Parameter, Struct, StructMember, Enum, EnumValue, Requirement, Register, Macro, Typedef
- **22+ relationship types** queried via Cypher
- **Key queries:**
  - Function dependency chain (DEPENDS_ON, CALLS_INTERNALLY)
  - Struct member definitions (HAS_MEMBER with types)
  - Enum value resolution (HAS_VALUE with numeric codes)
  - Requirement traceability (IMPLEMENTS / IMPLEMENTED_BY)
  - Register bitfield extraction (HAS_BITFIELD, CONTROLS)
  - Impact analysis (upstream + downstream traversal up to 3 hops)

### Code Generator

**File:** `backend/generators/code_generator.py` (~7,653 lines)  
**Purpose:** Core engine that transforms RAG+KG context into C test code

Key classes:
- **`FeatureClassifier`** — Classifies user intent using RAG semantic similarity scores (primary, ~95% accuracy) with PUML core function validation (secondary). Organizes functions into init/operation/cleanup phases.
- **`FunctionSequenceBuilder`** — Arranges function calls in topologically correct order based on dependency graph and phase patterns.
- **`StructInitializationGenerator`** — Generates config struct member initialization using real KG data (types, values, offsets).
- **`DataDrivenCodeGenerator`** — Orchestrates the full code generation: includes, struct init, function calls, polling, error handling, requirement traceability comments.

Key helper functions:
- `build_llm_prompt_idea_1_sequential()` — Constructs the LLM enhancement prompt
- `build_enum_resolver_prompt()` — Constructs the Stage 1 enum resolution prompt
- `apply_resolved_enums()` — Substitutes resolved enum values into the skeleton

### LLM Service

**File:** `backend/llm/llm_service.py`  
**Purpose:** Abstraction layer for LLM providers

- **Primary Provider:** GitHub Copilot via VS Code LM API (the actual LLM calls happen in the extension side via `vscode.lm.selectChatModels()` and `model.sendRequest()`)
- **Model Discovery:** From environment variables (`GITHUB_COPILOT_MODELS`, `VSCODE_LLM_MODELS`) or VS Code settings
- **Dynamic Model Selection:** Extension discovers available models at startup and sends them to the backend via `POST /llm/update-models`

### PUML Pattern Analyzer

**File:** `backend/analyzers/puml_analyzer.py`  
**Purpose:** Loads pre-computed PUML sequence diagram patterns from RAG

Fetches 2 essential chunks:
1. **`core_functions`** — Priority classification: always_present, frequently_present, rare
2. **`phase_patterns`** — Phase structure with example sequences: initialization, operation, error_handling

Used as a **reference guide** for sequence building — not the authoritative source for function signatures (that comes from RAG top-10 hits).

### Source Code Analyzer

**File:** `backend/analyzers/source_analyzer.py`  
**Purpose:** Extracts internal call relationships to prevent duplicate calls in tests

- Queries `CALLS_INTERNALLY` edges (with order and line number metadata)
- Queries `HAS_CASE` for dispatcher functions with switch case variants
- **Optimization:** Only analyzes selected functions (post-RAG/KG selection), not the entire module of 1000+ functions

### MISRA-C Validator

**File:** `backend/validators/misra_validator.py`  
**Purpose:** Static analysis for MISRA-C 2012 compliance

- 14 priority rules checked (R1.1, R2.2, R5.1, R10.1, R14.3, R15.7, R20.7, etc.)
- Regex-based validation (always available)
- Optional clang static analyzer integration
- Compliance score: 0–100 (priority violations -10 pts each, others -2 pts each)

### Hybrid Cache

**Files:** `backend/utils/cache.py`, `backend/generators/hybrid_cache.py`  
**Purpose:** Two-tier caching for performance

- **Tier 1:** In-memory LRU cache (OrderedDict, <1ms access, configurable size)
- **Tier 2:** SQLite persistence (10-50ms access, survives restarts, unlimited entries)
- **Strategy:** GET checks LRU first → falls back to SQLite. SET writes to both. Eviction removes from LRU but preserves in SQLite.
- **Three cache instances:** JSON semantic cache (1000 entries), PUML pattern cache (500), Source analysis cache (500)

---

## Two-Stage LLM Enhancement

The extension implements a two-stage LLM pipeline to maximize code quality:

### Stage 1: Enum Resolution (Automatic)
- **Model:** `gpt-5-mini` (fast, focused)
- **Input:** Enum resolver prompt with `/* TODO: resolve enum */` markers
- **Output:** JSON map of `{ "task_id": "EnumValue_Name" }`
- **Applied via:** `POST /apply_enum_resolution` → substitutes resolved values into skeleton
- **Why:** Prevents the main LLM from hallucinating incorrect enum values

### Stage 2: Code Enhancement (User-Selected Model)
- **Model:** User's choice (e.g., Claude 3.5 Sonnet, GPT-4)
- **Input:** Full LLM prompt (system template + enum-resolved skeleton + RAG/KG context)
- **Output:** Production-ready C test code
- **Post-processing:** Extracts code from markdown blocks, saves to output file

---

## Extension–Backend Communication

```
Extension                          Backend (FastAPI :8000)
   │                                        │
   │──── GET /health ──────────────────────→│  Startup health check (10 retries)
   │←─── { status: "healthy" } ────────────│
   │                                        │
   │──── POST /llm/update-models ─────────→│  Send discovered VS Code LLM models
   │←─── { status: "success" } ────────────│
   │                                        │
   │──── GET /modules ─────────────────────→│  Dynamically discover available modules
   │←─── { modules: ["cxpi"] } ────────────│
   │                                        │
   │──── GET /llm/models ─────────────────→│  Get available models for UI dropdown
   │←─── { models: [...], current: "..." } │
   │                                        │
   │──── POST /generate_test ─────────────→│  Main generation (Steps 0-9)
   │←─── { skeleton, llm_prompt, ... } ────│
   │                                        │
   │  [Stage 1: gpt-5-mini via VS Code LM] │
   │──── POST /apply_enum_resolution ─────→│  Apply resolved enum values
   │←─── { resolved_code } ────────────────│
   │                                        │
   │  [Stage 2: user model via VS Code LM] │
   │                                        │
   │──── POST /validate_generated_code ───→│  (Optional) Post-generation validation
   │←─── { status, errors, warnings } ─────│
```

---

## Configuration & Environment

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODULE_NAME` | _(none)_ | Target module (e.g., `cxpi`). User selects in UI. |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `NEO4J_DATABASE` | `cxpidb` | Neo4j database name (format: `{module}db`) |
| `CHROMA_PATH` | `../MCP_DB_INGESTION/output/chroma_data` | Path to ChromaDB directory |
| `LLM_MODEL` | _(auto)_ | Override default LLM model |
| `GITHUB_COPILOT_MODELS` | _(discovered)_ | Comma-separated list of available models |

### VS Code Extension Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `testManagement.backendUrl` | `http://localhost:8000` | FastAPI backend URL |
| `testManagement.module` | `cxpi` | Default module |
| `testManagement.llmModel` | _(auto)_ | LLM model for enhancement |
| `testManagement.outputDirectory` | `generated_tests` | Output directory for test files |

### config.json

```json
{
  "app_name": "Test Management System",
  "version": "0.1.0",
  "databases": {
    "chromadb": { "path": "../MCP_DB_INGESTION/output/chroma_data" },
    "neo4j": { "uri": "bolt://localhost:7687", "user": "neo4j" }
  },
  "api": { "host": "127.0.0.1", "port": 8000 }
}
```

---

## Directory Structure

```
GEST_DOMAIN_ASSISTANT_v1/
│
├── ARCHITECTURE.md                      ← This document
├── COMPLETE_SETUP_AND_USAGE_GUIDE.md    ← Setup instructions
├── setup.ps1                            ← PowerShell setup script
│
├── TEST_MANAGEMENT_APP/                 ← Python FastAPI Backend
│   ├── config.json                      ← Application config
│   ├── requirements.txt                 ← Python dependencies
│   ├── run_server.py                    ← Quick-start server script
│   │
│   ├── backend/
│   │   ├── app.py                       ← FastAPI app (2,739 lines) — all endpoints & pipeline
│   │   │
│   │   ├── database/
│   │   │   ├── rag_client.py            ← ChromaDB RAG client (1,164 lines)
│   │   │   └── kg_client.py             ← Neo4j KG client (798 lines)
│   │   │
│   │   ├── generators/
│   │   │   ├── code_generator.py        ← Data-driven code gen engine (7,653 lines)
│   │   │   ├── hybrid_cache.py          ← Cache module (generators-local copy)
│   │   │   ├── test_code_prompt.md      ← LLM system prompt template
│   │   │   └── test_code_prompt_OLD_BACKUP.md
│   │   │
│   │   ├── llm/
│   │   │   └── llm_service.py           ← LLM provider abstraction (511 lines)
│   │   │
│   │   ├── analyzers/
│   │   │   ├── puml_analyzer.py         ← PUML pattern loader (363 lines)
│   │   │   └── source_analyzer.py       ← Call graph analyzer (518 lines)
│   │   │
│   │   ├── validators/
│   │   │   └── misra_validator.py       ← MISRA-C 2012 compliance checker
│   │   │
│   │   └── utils/
│   │       └── cache.py                 ← HybridCache (LRU + SQLite)
│   │
│   ├── local_models/                    ← Cached sentence-transformers model
│   │   └── models--sentence-transformers--all-MiniLM-L6-v2/
│   │
│   └── output/
│       └── generated_tests/             ← Generated test files (.c)
│
├── TEST_MANAGEMENT_EXTENSION/           ← VS Code Extension (TypeScript)
│   ├── package.json                     ← Extension manifest & commands
│   ├── tsconfig.json                    ← TypeScript config
│   │
│   └── src/
│       ├── extension.ts                 ← Extension entry point (259 lines)
│       ├── backend/
│       │   └── client.ts               ← Axios HTTP client for FastAPI
│       ├── ui/
│       │   ├── webview.ts              ← WebviewManager + 2-stage LLM pipeline (482 lines)
│       │   ├── webviewContent.ts       ← Galaxy-themed HTML/CSS/JS UI (416 lines)
│       │   └── sidebarViewProvider.ts  ← Sidebar launcher
│       └── generators/
│           └── fileGenerator.ts        ← .c / .h / .md file generation
│
└── output/                              ← Pre-built data artifacts
    ├── chroma_data/                     ← ChromaDB database (SQLite + embeddings)
    ├── cxpidb.dump                      ← Neo4j database export
    ├── cxpi_knowledge_graph_export.json ← KG data in JSON format
    ├── cxpi_kg_stats.json               ← KG statistics
    └── cxpi_graph_view.html             ← Interactive graph visualization
```

---

## Technology Stack Summary

| Layer | Technology | Version |
|-------|-----------|---------|
| IDE Integration | VS Code Extension API | ^1.85.0 |
| Extension Language | TypeScript | ES2021 |
| HTTP Client | Axios | latest |
| Backend Framework | FastAPI | 0.104.1 |
| ASGI Server | Uvicorn | 0.24.0 |
| Vector Database | ChromaDB | 0.4.24 |
| Graph Database | Neo4j | 5.14+ |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 | 384-dim |
| ANN Index | hnswlib | 0.7+ |
| NLP | NLTK (WordNet, tokenize, lemmatize) | 3.8+ |
| LLM Gateway | VS Code Language Model API | vscode.lm |
| Caching | LRU (OrderedDict) + SQLite3 | built-in |
| Static Analysis | MISRA-C regex + clang (optional) | — |
| Data Validation | Pydantic | 2.7+ |
