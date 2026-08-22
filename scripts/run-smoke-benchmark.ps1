# End-to-end smoke benchmark: pull the smoke-tier model and run aihwbench.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run-smoke-benchmark.ps1

$ErrorActionPreference = "Stop"

$model = "qwen2.5:0.5b-instruct-q4_K_M"

Write-Host "Pulling smoke-tier model: $model"
ollama pull $model

Write-Host "Running benchmark (2 warm-up + 5 measured iterations)..."
python -m benchmark.cli benchmark --runtime ollama --model $model --output results

Write-Host "Validating latest result..."
$latest = Get-ChildItem results/raw/*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
python -m benchmark.cli validate $latest.FullName