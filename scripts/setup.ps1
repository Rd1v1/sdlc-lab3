$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3.13 -m venv .venv }
    else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13+ is required' }
}
& $python -c 'import sys; assert sys.version_info >= (3,13); assert sys.prefix != sys.base_prefix'
if ($LASTEXITCODE -ne 0) { throw 'Invalid local virtual environment' }
& $python -m pip install --disable-pip-version-check --cache-dir .cache/pip -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Local dependency restore failed' }
Write-Output 'Ready. All Python packages are inside .venv.'
