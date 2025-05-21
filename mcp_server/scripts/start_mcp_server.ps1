# PowerShell script to start the WinDbg MCP Server
# This script should be used to start the server with proper configuration for Cursor IDE integration

# Make sure we're in the correct directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Set environment variables for the server
$env:MCP_TRANSPORT = "sse"  # Use SSE transport for Cursor
$env:MCP_HOST = "localhost"
$env:MCP_PORT = "8000"

# You can uncomment the line below to enable debug logging
# $env:DEBUG = "true"

Write-Host "Starting WinDbg MCP Server for Cursor Integration..." -ForegroundColor Green
Write-Host "Server will be available at http://localhost:8000/sse" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow

# Check if Python is available
try {
    $pythonVersion = python --version
    Write-Host "Using $pythonVersion" -ForegroundColor Cyan
}
catch {
    Write-Host "Error: Python not found. Please install Python 3.11 or later." -ForegroundColor Red
    exit 1
}

# Check if required packages are installed
try {
    python -c "import fastmcp" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing required packages..." -ForegroundColor Yellow
        pip install -r requirements.txt
    }
}
catch {
    Write-Host "Installing required packages..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Start the server
try {
    python server.py
}
catch {
    Write-Host "Error starting server: $_" -ForegroundColor Red
    exit 1
} 