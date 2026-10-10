# Official portable tools, pinned versions; nothing is added to global PATH.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force .tools\hashcat | Out-Null
$downloads = @(
    @{ Url = 'https://hashcat.net/files/hashcat-7.1.2.7z'; Path = '.tools/hashcat.7z'; Sha256 = '80DB0316387794CE9D14ED376DA75B8A7742972485B45DB790F5F8260307FF98' }
)
foreach ($download in $downloads) {
    if (-not (Test-Path -LiteralPath $download.Path)) { Invoke-WebRequest $download.Url -OutFile $download.Path }
    if ((Get-FileHash -LiteralPath $download.Path -Algorithm SHA256).Hash -ne $download.Sha256) { throw "Checksum mismatch: $($download.Path)" }
}
if (-not (Test-Path .tools/hashcat/hashcat-7.1.2/hashcat.exe)) {
    & tar -xf .tools/hashcat.7z -C .tools/hashcat
    if ($LASTEXITCODE -ne 0) { throw 'Portable hashcat extraction failed' }
}
Write-Output 'Portable tools ready in .tools; no global installation.'
