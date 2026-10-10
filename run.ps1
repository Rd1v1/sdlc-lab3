$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path .venv/Scripts/python.exe)) {
    & "$PSScriptRoot/scripts/setup.ps1"
}
& .venv/Scripts/python.exe main.py @args
exit $LASTEXITCODE
