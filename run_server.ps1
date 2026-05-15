$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Test-Python($Path) {
    if (-not (Test-Path $Path)) {
        return $false
    }
    try {
        & $Path -c "import sys; print(sys.executable)" | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function New-ProjectVenv() {
    Write-Host "Creating a usable .venv..."
    if (Test-Path ".venv") {
        Remove-Item ".venv" -Recurse -Force
    }

    try {
        py -m venv .venv
    } catch {
        python -m venv .venv
    }
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Python $python)) {
    Write-Host "Current .venv is missing or not usable."
    New-ProjectVenv
    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
}

try {
    & $python -c "import fastapi, uvicorn, langchain_openai, ddgs"
} catch {
    Write-Host "Installing missing dependencies..."
    & $python -m pip install -r requirements.txt
}

Write-Host "Starting API server: http://127.0.0.1:8000"
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
