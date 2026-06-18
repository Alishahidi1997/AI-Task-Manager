# Smart Task Tracker - start full local stack (Windows PowerShell)
#
# Usage (from repo root):
#   .\run-app.ps1           # Docker + API + worker + frontend
#   .\run-app.ps1 -Simple   # API + frontend only (SQLite, no Docker)
#
# First-time setup (once):
#   python -m venv .venv
#   .\.venv\Scripts\pip install -r requirements.txt
#   copy .env.example .env
#   cd frontend; npm install; cd ..

param(
    [switch]$Simple
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    $dq = [char]34
    Get-Content $Path | ForEach-Object {
        $line = $_
        if ($line -match '^\s*#' -or $line -match '^\s*$') { return }
        if ($line -match '^\s*([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value.Length -ge 2 -and $value[0] -eq $dq -and $value[-1] -eq $dq) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$Command
    )
    $escapedRoot = $Root -replace "'", "''"
    $full = "Set-Location '$escapedRoot'; $Command"
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "`$host.UI.RawUI.WindowTitle = '$Title'; $full"
    ) | Out-Null
}

function Add-EnvLine {
    param([string]$Name, [string]$Value)
    if (-not $Value) { return }
    $escaped = $Value -replace "'", "''"
    $script:envLines += ('{0} = ''{1}''' -f $Name, $escaped)
}

Write-Host "Smart Task Tracker - starting..." -ForegroundColor Cyan

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Error "Missing .venv. Run: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

if (-not (Test-Path ".\.env")) {
    if (Test-Path ".\.env.example") {
        Copy-Item ".\.env.example" ".\.env"
        Write-Host "Created .env from .env.example - add OPENAI_API_KEY for AI routes." -ForegroundColor Yellow
    }
}

Import-DotEnv ".\.env"

if (-not $env:JWT_SECRET_KEY) { $env:JWT_SECRET_KEY = "dev-secret" }
if (-not $env:DEMO_MODE) { $env:DEMO_MODE = "true" }

$useDocker = -not $Simple
$dockerOk = $false

if ($useDocker) {
    Write-Host "Starting Docker services..." -ForegroundColor Cyan
    docker compose up -d 2>&1 | Out-Host
    if ($LASTEXITCODE -eq 0) {
        $dockerOk = $true
        if (-not $env:DATABASE_URL) {
            $env:DATABASE_URL = "postgresql+psycopg://smarttask:smarttask@localhost:5432/smarttask"
        }
        if (-not $env:RABBITMQ_URL) {
            $env:RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
        }
        if (-not $env:REDIS_URL) {
            $env:REDIS_URL = "redis://localhost:6379/0"
        }
        if (-not $env:LLM_QUEUE_ENABLED) {
            $env:LLM_QUEUE_ENABLED = "true"
        }
        Write-Host "Docker is up." -ForegroundColor Green
    } else {
        Write-Host "Docker failed - continuing with SQLite." -ForegroundColor Yellow
        $useDocker = $false
    }
} else {
    Write-Host "Simple mode: SQLite backend, no Docker." -ForegroundColor Yellow
}

if (-not (Test-Path ".\frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location ".\frontend"
    npm install
    Pop-Location
}

$envLines = @(
    @'
function Import-ChildDotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    $dq = [char]34
    Get-Content $Path | ForEach-Object {
        $line = $_
        if ($line -match '^\s*#' -or $line -match '^\s*$') { return }
        if ($line -match '^\s*([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value.Length -ge 2 -and $value[0] -eq $dq -and $value[-1] -eq $dq) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}
Import-ChildDotEnv '.env'
'@
)
Add-EnvLine -Name '$env:JWT_SECRET_KEY' -Value $env:JWT_SECRET_KEY
Add-EnvLine -Name '$env:DEMO_MODE' -Value $env:DEMO_MODE
Add-EnvLine -Name '$env:DATABASE_URL' -Value $env:DATABASE_URL
Add-EnvLine -Name '$env:RABBITMQ_URL' -Value $env:RABBITMQ_URL
Add-EnvLine -Name '$env:REDIS_URL' -Value $env:REDIS_URL
Add-EnvLine -Name '$env:LLM_QUEUE_ENABLED' -Value $env:LLM_QUEUE_ENABLED
Add-EnvLine -Name '$env:OPENAI_API_KEY' -Value $env:OPENAI_API_KEY
$envBootstrap = $envLines -join '; '

Write-Host "Starting API (uvicorn)..." -ForegroundColor Cyan
Start-ServiceWindow -Title "Smart Task API :8000" -Command "$envBootstrap; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

if ($useDocker -and $env:RABBITMQ_URL) {
    Write-Host "Starting LLM worker (RabbitMQ)..." -ForegroundColor Cyan
    Start-ServiceWindow -Title "Smart Task Worker" -Command "$envBootstrap; .\.venv\Scripts\python.exe -m app.worker.main"
}

Write-Host "Starting frontend (Vite)..." -ForegroundColor Cyan
Start-ServiceWindow -Title "Smart Task UI :5173" -Command "Set-Location '.\frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

Write-Host ""
Write-Host "Ready - open these URLs:" -ForegroundColor Green
Write-Host "  App:        http://127.0.0.1:5173"
Write-Host "  API docs:   http://127.0.0.1:8000/docs"
Write-Host "  Demo login: demo@smarttracker.local / demo1234"
if ($useDocker) {
    Write-Host "  RabbitMQ:   http://localhost:15672  (guest/guest)"
    Write-Host "  Grafana:    http://localhost:3000   (admin/admin)"
    Write-Host "  Prometheus: http://localhost:9090"
}
Write-Host ""
Write-Host "Each service runs in its own PowerShell window. Close a window to stop that service." -ForegroundColor DarkGray
