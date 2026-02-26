# Test Domain Assistant — Setup & Usage Guide

**What is this tool?**
The **Test Domain Assistant** is a VS Code extension that generates professional C test code for automotive software modules (CXPI, LIN, SENT, and others). You describe what you want to test in plain English, and the assistant generates a complete, structured C test file — with the correct API functions, struct initialisations, polling loops, and error monitoring — ready to compile and run.

**Last Updated:** February 24, 2026

---

## BEFORE YOU START — Install These Four Things First

Work through this list top to bottom before opening VS Code.

---

### 1. Python 3.10 or newer

Download from: **https://www.python.org/downloads**

> ⚠️ **Critical Windows step:** On the very first screen of the installer, tick the checkbox **"Add Python to PATH"** before clicking Install Now. If you miss this, Python will not be found.

Verify after installation — open a new terminal and run:
```
python --version
```
You should see `Python 3.10.x` or higher.

---

### 2. Node.js (version 18 LTS or 20 LTS)

Download from: **https://nodejs.org** — choose the **LTS** version, accept all defaults.

Verify:
```
node --version
npm --version
```
Both should print a version number.

---

### 3. Visual Studio Code + GitHub Copilot Extension

Download VS Code from: **https://code.visualstudio.com**

After installing:
1. Open VS Code
2. Click the **Extensions icon** in the left sidebar (four squares)
3. Search for **"GitHub Copilot"** → click **Install**
4. Sign in with your GitHub account when prompted

> GitHub Copilot is used to refine the generated test code with better comments and assertions.

---

### 4. Neo4j Desktop — Database Setup

Download from: **https://neo4j.com/download** and create a free account when prompted.

> ✅ **You do NOT need to ingest any data.** The fully populated knowledge graph database is included in the package as a single dump file (`output\cxpidb.dump`). You just restore it — one command, done.

#### Step A — Create a new DBMS

1. Open **Neo4j Desktop**
2. Click **"New"** → **"Create Project"** → name it anything (e.g. `Test Modules`)
3. Inside the project, click **"Add"** → **"Local DBMS"**
4. Set these values:

   | Field | Value |
   |---|---|
   | **Name** | anything (e.g. `cxpidb`) |
   | **Password** | `INNOVATION26` |
   | **Version** | Latest 5.x |

5. Click **"Create"** — but **do NOT start it yet**

#### Step B — Restore the database from the dump file

The dump file is included in your package at:
```
output\cxpidb.dump
```

1. In Neo4j Desktop, find the DBMS you just created
2. Click the **"..."** (three dots) menu next to it → click **"Terminal"**
3. In the terminal that opens, run this single command:

```
bin\neo4j-admin database load cxpidb --from-path="<path_to_package>\output" --overwrite-destination=true
```

Replace `<path_to_package>` with the actual path where you extracted the ZIP, for example:
```
bin\neo4j-admin database load cxpidb --from-path="C:\Users\YourName\Desktop\KNOWLEDGE GRAPH V2\output" --overwrite-destination=true
```

4. Wait for it to complete (takes about 10–30 seconds)

#### Step C — Start the DBMS

Back in Neo4j Desktop, click **"Start"** on your DBMS — wait for the **green dot**.

#### Step D — Verify

1. Click **"Open"** → **"Neo4j Browser"**
2. Run:
   ```cypher
   :use cxpidb
   MATCH (n) RETURN count(n) AS total
   ```
   Expected: a number in the **hundreds or thousands**. If you see `0`, re-run the load command in Step B.

> ⚠️ **The DBMS must be running** (green dot in Neo4j Desktop) every time you use the tool.

---

> ✅ **ChromaDB (RAG vector database) — no setup needed at all.**  
> The fully populated vector database is already included in the package as the `output\chroma_data\` folder. The backend reads it directly on startup. Nothing to install, nothing to ingest.

---

## ONE-TIME SETUP

### Step 1 — Open the folder in VS Code

1. Open **VS Code**
2. **File → Open Folder**
3. Select the **`KNOWLEDGE GRAPH V2`** folder (the one containing `setup.ps1`)
4. Click **"Select Folder"**

The left sidebar should show: `TEST_MANAGEMENT_APP`, `TEST_MANAGEMENT_EXTENSION`, `.vscode`, `setup.ps1`, and this guide.

---

### Step 2 — Run the setup script

1. Open a terminal: **Terminal → New Terminal** (or `` Ctrl+` ``)
2. The terminal starts in the correct folder automatically
3. Run:

```powershell
.\setup.ps1
```

**What the script does automatically:**
- ✅ Checks Python (3.10+) and Node.js are installed
- ✅ Creates `TEST_MANAGEMENT_APP\.env` with the right defaults (if it doesn't exist)
- ✅ Checks that the ChromaDB vector database is present
- ✅ Installs all npm packages for the VS Code extension (`npm install`)
- ✅ Compiles the TypeScript extension to JavaScript (`npm run compile`)
- ✅ Installs all Python packages for the backend (`pip install -r requirements.txt`)

**What success looks like:**

```
================================================
  TEST MANAGEMENT SYSTEM - SETUP WIZARD
================================================

Checking Node.js and npm...
  ✓ Node.js v20.11.0  |  npm 10.2.4
Checking Python...
  ✓ Python 3.12.0
Checking .env configuration file...
  ✓ Created TEST_MANAGEMENT_APP\.env with default settings
Checking ChromaDB vector database...
  ✓ ChromaDB data found (chroma.sqlite3 — 45.2 MB)

================================================
  NEO4J REMINDER — make sure cxpidb is running!
================================================

Installing VS Code extension dependencies...
  ✓ Extension npm packages installed
Compiling TypeScript extension...
  ✓ Extension compiled successfully
Installing Python backend dependencies...
  ✓ Backend Python packages installed

================================================
✅ SETUP COMPLETE!

Next steps:
  1. Start Neo4j Desktop — confirm cxpidb has a green dot
  2. Press F5 in VS Code
  3. Use the 🧪 beaker icon in the new window to generate tests
================================================
```

> If you see any ❌ errors, jump to the **Troubleshooting** section at the bottom.

---

## DAILY USE — How to Start and Use the Tool

### Step 1 — Start Neo4j

Open **Neo4j Desktop** — confirm `cxpidb` shows a **green dot**.
If it is grey/stopped, click **"Start"** and wait for the green dot before continuing.

---

### Step 2 — Press F5

In VS Code (the `KNOWLEDGE GRAPH V2` window), press **F5**.

If a dropdown appears, select **"Test Management Extension"** — it is the only option.

**What happens (takes 10–20 seconds):**

```
Phase A ─ Extension compiles
          Terminal shows: "Found 0 errors. Watching for file changes."

Phase B ─ Python backend starts (FastAPI on port 8000)
          Terminal shows:
            ╔══════════════════════════════════╗
            ║  TEST MANAGEMENT APP - FastAPI   ║
            ╚══════════════════════════════════╝
            [OK] RAGClient   — 11 collections loaded
            [OK] KGClient    — connected to cxpidb
            [OK] PUMLAnalyzer loaded
            Uvicorn running on http://0.0.0.0:8000

Phase C ─ A SECOND VS Code window opens
          This is the Extension Development Host.
          This is where you use the tool.
```

> ⚠️ After pressing F5 you will have **two VS Code windows** open:
> - **Window 1** (original) — shows logs and terminal. Do not close this.
> - **Window 2** (Extension Development Host) — this is where you work.

---

### Step 3 — Open the Test Generator panel

In **Window 2** (the new window):

1. Look at the **left sidebar** — find the **🧪 beaker icon** labelled "Test Management"
2. Click it — the **Test Generator Panel** opens on the right

---

### Step 4 — Fill in the form and generate

In the Test Generator Panel, fill in three fields:

| Field | What to enter |
|---|---|
| **Module** | Select the module you are testing from the dropdown (e.g. `CXPI`, `LIN`, `SENT`, etc.) |
| **Test Type** | Select a category: `Basic`, `Error Handling`, `API Test`, etc. |
| **Description** | Type what you want to test in plain English |

**Example descriptions to try (shown here for CXPI — the same style works for any loaded module):**

| Description | What gets generated |
|---|---|
| `Initialize the module with baudrate 1000000` | Full init sequence with all config structs |
| `Transmit a header and receive a response` | TX/RX frame operation with polling loop |
| `Inject a CRC error and check the error flags` | Error injection test with error status monitoring |
| `Set baudrate using the API` | Focused test for the setBaudrate function |
| `Master sends header, slave receives with polling` | Multi-channel scenario test |
| `Disable and reset the module` | Module teardown and cleanup test |
| `Consecutive master response test` | Back-to-back frame transfer sequence |

Then click **"Generate Test"**.

---

### Step 5 — Review and accept

After 1–5 seconds, a complete C test file appears in the panel.

Look it over, then:
- ✅ Click **"Accept"** → saves the `.c` file to `TEST_MANAGEMENT_APP/output/generated_tests/`
- ❌ Click **"Reject"** → discards it; refine your description and try again

---

### Step 6 — Stop the system when done

Press **Shift+F5** in Window 1, or simply close Window 2.
This stops the backend server and ends the debug session.

---

## HOW IT WORKS (overview)

When you click "Generate Test" the backend does six things:

1. **Intent classification** — your description is turned into an embedding and matched against the vector database to identify which module operations are relevant

2. **RAG retrieval** — ChromaDB (11 collections) is searched for:
   - API function signatures and documentation for the selected module
   - Config struct member names and types
   - Enum values and their meanings
   - Hardware register details
   - Known PUML sequence patterns for that module

3. **Knowledge Graph query** — Neo4j (`cxpidb`) is queried for:
   - Function call order (topological dependency graph)
   - Exact function signatures and parameter types
   - Struct field names and types

4. **C code assembly** — a complete skeleton is built:
   - Functions sequenced in correct dependency order
   - Struct members initialised with correct values
   - Polling loops and timeout handling
   - TX/RX buffer declarations

5. **LLM refinement** — GitHub Copilot improves comments and may add assertions

6. **Response** — the finished code is returned to the VS Code panel

---

## TROUBLESHOOTING

### ❌ setup.ps1 — "Python not found"
Re-install Python from https://www.python.org/downloads  
On the **first screen** tick **"Add Python to PATH"**  
Restart the terminal, then run `.\setup.ps1` again

### ❌ setup.ps1 — "npm not found" or "Node.js not found"
Install Node.js LTS from https://nodejs.org  
Restart the terminal, then run `.\setup.ps1` again

### ❌ setup.ps1 — "ChromaDB data folder not found"
The `chroma_data/` folder is missing from your package.  
Ask whoever gave you the package to resend it with the `output/chroma_data/` folder included.

### ❌ After F5 — "Neo4j connection failed" in the terminal
- Open Neo4j Desktop → confirm `cxpidb` has a green dot (must be **started**)
- Open `TEST_MANAGEMENT_APP/.env` → confirm `NEO4J_PASSWORD=INNOVATION26` and `NEO4J_DATABASE=cxpidb`
- Open http://localhost:7474 in a browser — you should see the Neo4j Browser login page

### ❌ Window 2 shows "Cannot connect to backend"
The backend may still be starting up. Wait 10 seconds and retry.  
If it persists, check Window 1's terminal for a Python error message.

### ❌ ModuleNotFoundError: No module named 'fastapi' (or similar)
```powershell
cd TEST_MANAGEMENT_APP
pip install -r requirements.txt
```

### ❌ TypeScript compilation error
```powershell
cd TEST_MANAGEMENT_EXTENSION
Remove-Item -Recurse -Force node_modules
npm install
npm run compile
```

### ❌ Beaker icon not visible in the sidebar
Make sure you are in **Window 2** (the Extension Development Host), not Window 1.  
If still not visible: **Ctrl+Shift+P** → type `Test Management` → run **"Show Test Generator"**

### ❌ Generated code is empty or has incorrect function names
- In Neo4j Browser run `MATCH (n) RETURN count(n)` — must return a non-zero number
- Confirm `output/chroma_data/chroma.sqlite3` exists on disk
- Check Window 1 terminal for a Python stack trace pointing to the root cause

---

## CONFIGURATION REFERENCE

The backend is configured by `TEST_MANAGEMENT_APP/.env`.  
The setup script creates this file automatically. You only need to edit it if your Neo4j password is different from the default.

```env
# Neo4j Knowledge Graph
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=INNOVATION26    ← change only if your Neo4j password is different
NEO4J_DATABASE=cxpidb          ← do not change this

# ChromaDB path  ← set automatically by setup.ps1, do not change
CHROMA_PATH=C:\...\KNOWLEDGE GRAPH V2\output\chroma_data

# Module (set to the module whose knowledge graph is loaded in Neo4j)
MODULE_NAME=cxpi               ← change to the module you are working with (e.g. lin, sent)

# Server
BACKEND_PORT=8000
BACKEND_HOST=0.0.0.0

# Logging  (DEBUG = verbose, INFO = normal)
LOG_LEVEL=INFO

# Cache
CACHE_SIZE_MB=512
CACHE_TTL_HOURS=24
```

---

## QUICK REFERENCE CARD

| What you want to do | How |
|---|---|
| First-time setup | Run `.\setup.ps1` in the VS Code terminal |
| Start the tool | Press **F5** → select "Test Management Extension" |
| Open the test generator | Click the 🧪 beaker icon in Window 2's left sidebar |
| Generate a test | Type a description → click "Generate Test" |
| Save a test | Click "Accept" in the panel |
| View backend logs | Window 1 → Terminal tab |
| View debug output | Window 1 → **View → Debug Console** (Ctrl+Shift+Y) |
| Reload the extension | Press **Ctrl+R** in Window 2 |
| Stop everything | Press **Shift+F5**, or close Window 2 |
| Check backend health | Open http://localhost:8000/health in a browser |
| Browse the Neo4j graph | Open http://localhost:7474 in a browser |

---

**Status:** ✅ Production Ready — Version 2.0
**Last Updated:** February 24, 2026