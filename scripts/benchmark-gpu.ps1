param([ValidateRange(1,20)][int]$Repeats=3)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& "$PSScriptRoot/setup.ps1"
powershell -ExecutionPolicy Bypass -File "$PSScriptRoot/setup-tools.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Portable hashcat setup failed' }
& .venv/Scripts/python.exe scripts/setup-wordlist.py
if ($LASTEXITCODE -ne 0) { throw 'RockYou setup failed' }
& .venv/Scripts/python.exe -m lab3.src.dictionary_benchmark --repeats $Repeats
if ($LASTEXITCODE -ne 0) { throw 'GPU comparison failed' }
