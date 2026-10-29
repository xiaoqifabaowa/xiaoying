param([switch]$Install)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
if ($Install) {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { python -m venv .venv }
    & ./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    & ./.venv/Scripts/python.exe -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed' }
    Push-Location frontend
    try {
        npm.cmd ci --cache ../runtime/npm-cache
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Please run ./start.ps1 -Install first' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Please build frontend first: npm --prefix frontend run build' }
Write-Host 'Open http://127.0.0.1:8000 (API docs: /docs). Ctrl+C to stop.'
& ./.venv/Scripts/python.exe -m uvicorn enterprise_qa.api:app --host 127.0.0.1 --port 8000
