# PMON-AI-OPS Stop Script
# Stops all running backend and frontend processes

$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  PMON-AI-OPS Stop Services" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

$stopped = 0

# Python uvicorn backend
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = $_.CommandLine
    } catch {
        $cmd = ""
    }
    if ($cmd -and $cmd -like "*uvicorn*") {
        Stop-Process -Id $_.Id -Force
        Write-Host "  [X] Stopped backend PID=$($_.Id)" -ForegroundColor Yellow
        $stopped++
    }
}

# Node vite frontend
Get-Process node -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = $_.CommandLine
    } catch {
        $cmd = ""
    }
    if ($cmd -and $cmd -like "*vite*") {
        Stop-Process -Id $_.Id -Force
        Write-Host "  [X] Stopped frontend PID=$($_.Id)" -ForegroundColor Yellow
        $stopped++
    }
}

if ($stopped -eq 0) {
    Write-Host "  No PMON processes found" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "  Stopped $stopped process(es)" -ForegroundColor Green
}

Write-Host ""
