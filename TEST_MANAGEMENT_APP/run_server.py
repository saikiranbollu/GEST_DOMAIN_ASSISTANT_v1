#!/usr/bin/env python3
"""
QUICK START - Run PHASE 2 FastAPI Server

This script handles:
1. Environment setup
2. Dependency checking
3. Database connection verification
4. Server startup
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

def main():
    """Quick start the server"""
    
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║     TEST MANAGEMENT APP - PHASE 2 (RAG Integration)          ║
    ║                                                               ║
    ║              FastAPI Server Quick Start                      ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Get the root directory
    root_dir = Path(__file__).parent
    backend_dir = root_dir / "backend"
    
    print(f"📁 Root directory: {root_dir}")
    print(f"📁 Backend directory: {backend_dir}")
    
    # Load environment
    env_file = root_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Environment loaded from {env_file}")
    else:
        print(f"⚠️  No .env file found. Using system environment variables.")
        print(f"    Create .env with:")
        print(f"    - MODULE_NAME=cxpi")
        print(f"    - NEO4J_URI=bolt://localhost:7687")
        print(f"    - NEO4J_USER=neo4j")
        print(f"    - NEO4J_PASSWORD=Innovation25")
    
    # Check environment variables
    print("\n📋 Checking environment variables...")
    required_vars = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "Innovation25"
    }
    
    optional_vars = {
        "MODULE_NAME": "(Optional - user selects in UI)"
    }
    
    missing = []
    for var, default in required_vars.items():
        value = os.getenv(var, default)
        status = "✅" if os.getenv(var) else "⚠️"
        print(f"  {status} {var}: {value}")
        if not os.getenv(var):
            missing.append(var)
    
    for var, note in optional_vars.items():
        value = os.getenv(var, "Not set")
        status = "✅" if os.getenv(var) else "ℹ️"
        print(f"  {status} {var}: {value} {note}")
    
    if missing:
        print(f"\n⚠️  Missing REQUIRED environment variables: {', '.join(missing)}")
        print(f"    Set them before running, or create a .env file.")
    
    # Check dependencies
    print("\n📦 Checking dependencies...")
    try:
        import fastapi
        print(f"  ✅ FastAPI {fastapi.__version__}")
    except ImportError:
        print(f"  ❌ FastAPI not installed. Run: pip install -r requirements.txt")
        return 1
    
    try:
        import uvicorn
        print(f"  ✅ Uvicorn installed")
    except ImportError:
        print(f"  ❌ Uvicorn not installed. Run: pip install -r requirements.txt")
        return 1
    
    try:
        import chromadb
        print(f"  ✅ ChromaDB installed")
    except ImportError:
        print(f"  ❌ ChromaDB not installed. Run: pip install -r requirements.txt")
        return 1
    
    try:
        import neo4j
        print(f"  ✅ Neo4j driver installed")
    except ImportError:
        print(f"  ❌ Neo4j driver not installed. Run: pip install -r requirements.txt")
        return 1
    
    # Check database files
    print("\n💾 Checking database files...")
    chroma_path = os.getenv(
        "CHROMA_PATH",
        str(root_dir.parent / "MCP_DB_INGESTION" / "output" / "chroma_data")
    )
    
    if Path(chroma_path).exists():
        print(f"  ✅ ChromaDB data found at {chroma_path}")
    else:
        print(f"  ⚠️  ChromaDB data not found at {chroma_path}")
        print(f"     Run MCP_DB_INGESTION first to generate embeddings.")
    
    # Start server
    print("\n🚀 Starting FastAPI server...")
    print(f"   Server will be available at: http://localhost:8000")
    print(f"   API docs: http://localhost:8000/docs")
    print(f"   ReDoc: http://localhost:8000/redoc")
    print(f"\n   Press Ctrl+C to stop the server")
    print(f"   {'─' * 60}")
    
    os.chdir(root_dir)
    
    # Start server with uvicorn
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "backend.app:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
        return 0
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
