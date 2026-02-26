#!/usr/bin/env powershell

$ROOT = $PSScriptRoot

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  TEST MANAGEMENT SYSTEM - SETUP WIZARD" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$hasError = $false

#  1. Check Node.js / npm 
Write-Host "Checking Node.js and npm..." -ForegroundColor Yellow
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Host "   npm not found. Install Node.js 18+ from https://nodejs.org/" -ForegroundColor Red
    $hasError = $true
} else {
    $npmVer = (npm --version 2>&1)
    $nodeVer = (node --version 2>&1)
    Write-Host "   Node.js $nodeVer  |  npm $npmVer" -ForegroundColor Green
}

#  2. Check Python 
Write-Host "Checking Python..." -ForegroundColor Yellow
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Write-Host "   Python not found. Install Python 3.10+ from https://www.python.org/" -ForegroundColor Red
    Write-Host "     IMPORTANT: On the installer first screen, tick 'Add Python to PATH'" -ForegroundColor Yellow
    $hasError = $true
} else {
    $pyVer = (python --version 2>&1)
    # Check version is 3.10+
    if ($pyVer -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Host "   $pyVer found but Python 3.10+ is required." -ForegroundColor Red
            $hasError = $true
        } else {
            Write-Host "   $pyVer" -ForegroundColor Green
        }
    } else {
        Write-Host "   $pyVer (could not parse version  proceed with caution)" -ForegroundColor Yellow
    }
}

if ($hasError) {
    Write-Host ""
    Write-Host " Please fix the above issues and re-run setup.ps1" -ForegroundColor Red
    exit 1
}

Write-Host ""

#  3. Check .env file 
Write-Host "Checking .env configuration file..." -ForegroundColor Yellow
$envPath = Join-Path $ROOT "TEST_MANAGEMENT_APP\.env"
if (-not (Test-Path $envPath)) {
    Write-Host "    .env file not found at TEST_MANAGEMENT_APP\.env" -ForegroundColor Yellow
    Write-Host "  Creating default .env file..." -ForegroundColor Yellow
    $envContent = @"
# Neo4j Knowledge Graph
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=INNOVATION26
NEO4J_DATABASE=cxpidb

# ChromaDB vector database path (relative to workspace root)
CHROMA_PATH=$ROOT\output\chroma_data

# Module
MODULE_NAME=cxpi

# Server
BACKEND_PORT=8000
BACKEND_HOST=0.0.0.0

# Logging
LOG_LEVEL=INFO

# Cache
CACHE_SIZE_MB=512
CACHE_TTL_HOURS=24
"@
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8
    Write-Host "   Created TEST_MANAGEMENT_APP\.env with default settings" -ForegroundColor Green
    Write-Host "     If your Neo4j password differs from INNOVATION26, edit this file before pressing F5" -ForegroundColor Yellow
} else {
    Write-Host "   .env file exists" -ForegroundColor Green
}

Write-Host ""

#  4. Check ChromaDB data 
Write-Host "Checking ChromaDB vector database..." -ForegroundColor Yellow
$chromaDb = Join-Path $ROOT "output\chroma_data\chroma.sqlite3"
$chromaDir = Join-Path $ROOT "output\chroma_data"
if (-not (Test-Path $chromaDb)) {
    if (Test-Path $chromaDir) {
        Write-Host "    chroma.sqlite3 not found but chroma_data/ folder exists." -ForegroundColor Yellow
        Write-Host "     The database may still be present in segmented files  continuing." -ForegroundColor Yellow
    } else {
        Write-Host "   ChromaDB data folder not found: output\chroma_data\" -ForegroundColor Red
        Write-Host "     This is CRITICAL  the backend cannot run without the vector database." -ForegroundColor Red
        Write-Host "     Make sure the chroma_data/ folder was included in the ZIP." -ForegroundColor Yellow
        $hasError = $true
    }
} else {
    $dbSize = [math]::Round((Get-Item $chromaDb).Length / 1MB, 1)
    Write-Host "   ChromaDB data found (chroma.sqlite3  ${dbSize} MB)" -ForegroundColor Green
}

Write-Host ""

#  5. Neo4j reminder 
Write-Host "" -ForegroundColor Cyan
Write-Host "  NEO4J REMINDER" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan
Write-Host "  Before pressing F5, ensure Neo4j Desktop is:" -ForegroundColor White
Write-Host "    1. Installed from https://neo4j.com/download" -ForegroundColor White
Write-Host "    2. A DBMS exists with password: INNOVATION26" -ForegroundColor White
Write-Host "    3. cxpidb database restored from: output\cxpidb.dump" -ForegroundColor White
Write-Host "    4. The DBMS is STARTED (green dot in Neo4j Desktop)" -ForegroundColor White
Write-Host "  See COMPLETE_SETUP_AND_USAGE_GUIDE.md for restore steps." -ForegroundColor Yellow
Write-Host "" -ForegroundColor Cyan
Write-Host ""

if ($hasError) {
    Write-Host " Critical errors found. Fix ChromaDB data issue before continuing." -ForegroundColor Red
    exit 1
}

#  6. Install extension npm packages 
Write-Host "Installing VS Code extension dependencies..." -ForegroundColor Yellow
$extPath = Join-Path $ROOT "TEST_MANAGEMENT_EXTENSION"
Push-Location $extPath
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "   npm install failed in TEST_MANAGEMENT_EXTENSION" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "   Extension npm packages installed" -ForegroundColor Green
Pop-Location

Write-Host ""

#  7. Compile TypeScript extension 
Write-Host "Compiling TypeScript extension..." -ForegroundColor Yellow
Push-Location $extPath
npm run compile
if ($LASTEXITCODE -ne 0) {
    Write-Host "   TypeScript compilation failed" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "   Extension compiled successfully" -ForegroundColor Green
Pop-Location

Write-Host ""

#  8. Install Python backend dependencies 
Write-Host "Installing Python backend dependencies..." -ForegroundColor Yellow
$appPath = Join-Path $ROOT "TEST_MANAGEMENT_APP"
Push-Location $appPath
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "   pip install failed. Check Python/pip installation." -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "   Backend Python packages installed" -ForegroundColor Green
Pop-Location

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " SETUP COMPLETE!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Make sure Neo4j Desktop is running with cxpidb database" -ForegroundColor White
Write-Host "  2. Press F5 in VS Code to launch the system" -ForegroundColor White
Write-Host "  3. A new VS Code window opens  use the beaker icon () to generate tests" -ForegroundColor White
Write-Host ""
Write-Host "For detailed instructions: COMPLETE_SETUP_AND_USAGE_GUIDE.md" -ForegroundColor Yellow
Write-Host ""
