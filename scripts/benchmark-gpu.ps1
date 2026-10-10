param([ValidateRange(1,20)][int]$Repeats=3)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .venv/Scripts/python.exe)) {
    powershell -ExecutionPolicy Bypass -File "$PSScriptRoot/setup.ps1"
    if ($LASTEXITCODE -ne 0) { throw 'Local Python setup failed' }
}
& .venv/Scripts/python.exe -m pip install --disable-pip-version-check --cache-dir .cache/pip -r requirements-gpu.txt
if ($LASTEXITCODE -ne 0) { throw 'Local GPU dependency setup failed' }
powershell -ExecutionPolicy Bypass -File "$PSScriptRoot/setup-tools.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Portable hashcat setup failed' }
& .venv/Scripts/python.exe scripts/setup-wordlist.py
if ($LASTEXITCODE -ne 0) { throw 'RockYou setup failed' }
& .venv/Scripts/python.exe -m lab3.src.gpu_benchmark --repeats $Repeats
if ($LASTEXITCODE -ne 0) { throw 'GPU comparison failed' }
