$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$output = Join-Path $repoRoot "dist\\browser-extensions"
New-Item -Path $output -ItemType Directory -Force | Out-Null
Compress-Archive -Path (Join-Path $repoRoot "browser\\chromium\\*") -DestinationPath (Join-Path $output "ssdm-chromium-extension.zip") -Force
Compress-Archive -Path (Join-Path $repoRoot "browser\\firefox\\*") -DestinationPath (Join-Path $output "ssdm-firefox-extension.zip") -Force
Write-Host "Browser extension packages created in $output"
