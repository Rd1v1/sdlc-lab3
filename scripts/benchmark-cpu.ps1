param([ValidateRange(1,20)][int]$Repeats=3, [ValidateSet('legacy','dictionary')][string]$Comparison='dictionary')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
powershell -ExecutionPolicy Bypass -File "$PSScriptRoot/setup-tools.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Portable hashcat setup failed' }
if ($Comparison -eq 'dictionary') {
    if (-not (Test-Path .venv/Scripts/python.exe)) {
        powershell -ExecutionPolicy Bypass -File "$PSScriptRoot/setup.ps1"
        if ($LASTEXITCODE -ne 0) { throw 'Local Python setup failed' }
    }
    & .venv/Scripts/python.exe scripts/setup-wordlist.py
    if ($LASTEXITCODE -ne 0) { throw 'RockYou setup failed' }
}
docker build -f lab3/cpu-benchmark/Dockerfile -t sdlc-lab3-cpu:local .
if ($LASTEXITCODE -ne 0) { throw 'CPU benchmark image build failed' }
docker run --rm --network none --cpuset-cpus 0 --cpus 1 --memory 2g --pids-limit 256 --cap-drop ALL --security-opt no-new-privileges -v "${PWD}:/work" -w /work sdlc-lab3-cpu:local python -m lab3.src.cpu_benchmark --repeats $Repeats --comparison $Comparison
if ($LASTEXITCODE -ne 0) { throw 'CPU benchmark failed' }
