# Official portable tools, pinned versions; nothing is added to global PATH.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force .tools\hashcat | Out-Null
$downloads = @(
    @('https://hashcat.net/files/hashcat-7.1.2.7z', '.tools/hashcat.7z', '80DB0316387794CE9D14ED376DA75B8A7742972485B45DB790F5F8260307FF98')
)
foreach ($download in $downloads) {
    if (-not (Test-Path -LiteralPath $download[1])) { Invoke-WebRequest $download[0] -OutFile $download[1] }
    if ((Get-FileHash -LiteralPath $download[1] -Algorithm SHA256).Hash -ne $download[2]) { throw "Checksum mismatch: $($download[1])" }
}
if (-not (Test-Path .tools/hashcat/hashcat-7.1.2/hashcat.exe)) {
    & tar -xf .tools/hashcat.7z -C .tools/hashcat
    if ($LASTEXITCODE -ne 0) { throw 'Portable hashcat extraction failed' }
}
Write-Output 'Portable tools ready in .tools; no global installation.'
