$ErrorActionPreference = "Stop"
$InstallDir = Split-Path -Parent $PSScriptRoot
$HostExe = Join-Path $InstallDir "ssdm-native-host.exe"
if (!(Test-Path $HostExe)) { throw "Missing native messaging host: $HostExe" }

$ManifestDir = Join-Path $env:LOCALAPPDATA "SsDownloadManager\NativeHost"
New-Item -ItemType Directory -Path $ManifestDir -Force | Out-Null
$ManifestPath = Join-Path $ManifestDir "com.ssdownloadmanager.json"
$Manifest = @{
  name = "com.ssdownloadmanager"
  description = "Ss Download Manager native messaging bridge"
  path = $HostExe
  type = "stdio"
  allowed_origins = @("chrome-extension://egoijdabioaaoapbipodjmlpikfjbejd/")
  allowed_extensions = @("ss-download-manager@heshamzegoo")
} | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($ManifestPath, $Manifest, [Text.UTF8Encoding]::new($false))

$RegistryKeys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ssdownloadmanager",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.ssdownloadmanager",
  "HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.ssdownloadmanager",
  "HKCU:\Software\Mozilla\NativeMessagingHosts\com.ssdownloadmanager"
)
foreach ($Key in $RegistryKeys) {
  New-Item -Path $Key -Force | Out-Null
  Set-Item -Path $Key -Value $ManifestPath
}

$Instructions = @"
Ss Download Manager browser setup

The native messaging bridge is already installed and registered.

CHROME / EDGE / BRAVE:
1. Open the browser's Extensions page.
2. Turn on Developer mode.
3. Choose Load unpacked.
4. Select this folder:
   $InstallDir\browser\chromium

The Chromium extension ID is fixed in the package; the native bridge is pre-registered.

FIREFOX:
1. Open about:debugging#/runtime/this-firefox
2. Choose Load Temporary Add-on.
3. Select:
   $InstallDir\browser\firefox\manifest.json

Firefox temporary add-ons are removed when Firefox closes. A permanent Firefox install requires Mozilla signing and publication.

Copyright (c) 2026 HeshamZegoo
"@
$Readme = Join-Path $InstallDir "Browser-Setup.txt"
[IO.File]::WriteAllText($Readme, $Instructions, [Text.UTF8Encoding]::new($false))
Write-Host "Native messaging host registered. Browser extension folders are ready."
Write-Host "See $Readme for the one-time browser confirmation."
