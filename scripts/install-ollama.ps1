# Installs Ollama on Windows via winget and verifies the server responds.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/install-ollama.ps1

$ErrorActionPreference = "Stop"

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "Ollama already installed: $(ollama --version)"
} else {
    Write-Host "Installing Ollama via winget..."
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements --silent
    # Refresh PATH for this session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host "Ollama version: $(ollama --version)"

# Start the server if it is not running
$server = Get-Process ollama -ErrorAction SilentlyContinue
if (-not $server) {
    Write-Host "Starting ollama serve in background..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

try {
    $version = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 5
    Write-Host "Server OK: $($version.version)"
} catch {
    Write-Warning "Server did not respond on localhost:11434. Start it manually with 'ollama serve'."
}