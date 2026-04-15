# PMON-AI-OPS One-Click Startup Script
# Starts both backend (FastAPI) and frontend (Vite), verifies health
# Usage: right-click > Run with PowerShell

$ErrorActionPreference = "Stop"

# -- Paths --
$BackendDir = "F:\CodingProjects\电源监控日志实时分析系统\backend"
$ViteDir    = "F:\CodingProjects\电源监控日志实时分析系统\frontend"
$ViteBin    = Join-Path $ViteDir "node_modules\vite\bin\vite.js"

$BackendPort = 8000
$VitePort    = 5173

# -- Helper functions --
function Write-Step($msg) { Write-Host "[START] $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-ERR($msg)  { Write-Host "  [ERR] $msg" -ForegroundColor Red }
function Write-WARN($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }

# ==============================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor White
Write-Host "  PMON-AI-OPS One-Click Startup" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host ""

# -- 1. Clean up old processes --
Write-Step "Cleaning up old processes..."

Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = $_.CommandLine
    } catch {
        $cmd = ""
    }
    if ($cmd -and $cmd -like "*uvicorn*") {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  [X] Stopped old backend PID=$($_.Id)" -ForegroundColor Yellow
    }
}

Get-Process node -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = $_.CommandLine
    } catch {
        $cmd = ""
    }
    if ($cmd -and $cmd -like "*vite*") {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  [X] Stopped old frontend PID=$($_.Id)" -ForegroundColor Yellow
    }
}

Start-Sleep -Seconds 1
Write-OK "Cleanup done"

# -- 2. Start backend --
Write-Step "Starting backend (FastAPI :$BackendPort)..."

$backendProc = Start-Process -FilePath "python" `
    -ArgumentList "-X","utf8","-m","uvicorn","src.main:app","--host","0.0.0.0","--port",$BackendPort,"--log-level","info" `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -PassThru

Write-Host "  [>>] Backend PID=$($backendProc.Id)" -ForegroundColor Gray

# Wait for backend port
$backendReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $c = Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
         Where-Object { $_.State -eq "Listen" }
    if ($c) { $backendReady = $true; break }
}

if ($backendReady) {
    Write-OK "Backend running PID=$($backendProc.Id) on :$BackendPort"
} else {
    Write-ERR "Backend failed to start"
    exit 1
}

# -- 3. Start frontend --
Write-Step "Starting frontend (Vite :$VitePort)..."

$frontendProc = Start-Process -FilePath "node" `
    -ArgumentList """$ViteBin""","dev","--host","0.0.0.0","--port",$VitePort `
    -WorkingDirectory $ViteDir `
    -WindowStyle Hidden `
    -PassThru

Write-Host "  [>>] Frontend PID=$($frontendProc.Id)" -ForegroundColor Gray

# Wait for frontend port
$frontendReady = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $c = Get-NetTCPConnection -LocalPort $VitePort -ErrorAction SilentlyContinue |
         Where-Object { $_.State -eq "Listen" }
    if ($c) { $frontendReady = $true; break }
}

if ($frontendReady) {
    Write-OK "Frontend running PID=$($frontendProc.Id) on :$VitePort"
} else {
    Write-ERR "Frontend failed to start"
    exit 1
}

# -- 4. Verify health --
Write-Step "Verifying services..."

Start-Sleep -Milliseconds 500

# Backend health
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$BackendPort/api/health" -TimeoutSec 5 -UseBasicParsing
    Write-OK "Backend API: $($r.Content)"
} catch {
    Write-WARN "Backend API check failed: $($_.Exception.Message)"
}

# Backend metrics
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$BackendPort/api/metrics" -TimeoutSec 5 -UseBasicParsing
    Write-OK "Backend Metrics: $($r.Content)"
} catch {
    Write-WARN "Backend metrics check failed"
}

# Frontend
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$VitePort/" -TimeoutSec 5 -UseBasicParsing
    Write-OK "Frontend Vite: HTTP $($r.StatusCode) ($($r.Content.Length) bytes)"
} catch {
    Write-WARN "Frontend check failed: $($_.Exception.Message)"
}

# -- 5. WebSocket verify --
Write-Step "Testing WebSocket..."

try {
    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $ct = [Threading.CancellationToken]::None
    $ws.ConnectAsync("ws://localhost:$BackendPort/ws", $ct).Wait(5000)
    if ($ws.State -eq 'Open') {
        Write-OK "WebSocket connection: OPEN"
        $ws.CloseAsync('NormalClosure', "", $ct).Wait(1000)
    } else {
        Write-WARN "WebSocket state: $($ws.State)"
    }
} catch {
    Write-WARN "WebSocket test skipped: $($_.Exception.Message)"
}

# -- 6. Done --
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  PMON-AI-OPS Started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend (browser):" -ForegroundColor White
Write-Host "    Local:   http://localhost:$VitePort" -ForegroundColor Cyan
Write-Host "    LAN:     http://192.168.10.5:$VitePort" -ForegroundColor Cyan
Write-Host "    External: https://22mj4798in35.vicp.fun" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Backend API:" -ForegroundColor White
Write-Host "    http://localhost:$BackendPort" -ForegroundColor Cyan
Write-Host "    http://localhost:$BackendPort/docs  (Swagger docs)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  WebSocket: ws://localhost:$BackendPort/ws" -ForegroundColor Gray
Write-Host ""
Write-Host "  TFTP dir: $BackendDir\tftp_receive" -ForegroundColor Gray
Write-Host ""
Write-Host "  Stop: run stop-all.ps1" -ForegroundColor DarkGray
Write-Host ""

Start-Sleep -Seconds 2
