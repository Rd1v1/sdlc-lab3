$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .venv\Scripts\python.exe)) { throw 'Run scripts/setup.ps1 first' }
& .\.venv\Scripts\python.exe -m lab3.src.bruteforce @args
exit $LASTEXITCODE
