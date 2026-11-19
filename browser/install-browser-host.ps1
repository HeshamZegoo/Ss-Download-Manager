param(
  [Parameter(Mandatory=$true)][string]$InstallDir,
  [Parameter(Mandatory=$true)][string[]]$ChromiumExtensionIds
)
$ErrorActionPreference = "Stop"
$hostExe = Join-Path $InstallDir "ssdm-native-host.exe"
if (!(Test-Path $hostExe)) { throw "Native host executable not found: $hostExe" }
if ($ChromiumExtensionIds.Count -lt 1) { throw "Provide at least one Chromium extension ID." }
$allowedOrigins = @()
foreach ($id in $ChromiumExtensionIds) {
  if ($id -notmatch '^[a-p]{32}$') { throw "Invalid Chromium extension ID: $id" }
  $allowedOrigins += "chrome-extension://$id/"
}
$manifest = @{
  name = "com.ssdownloadmanager"
  description = "Ss Download Manager native messaging bridge"
  path = $hostExe
  type = "stdio"
  allowed_origins = $allowedOrigins
  allowed_extensions = @("ss-download-manager@heshamzegoo")
} | ConvertTo-Json -Depth 5
$manifestPath = Join-Path $InstallDir "com.ssdownloadmanager.json"
[System.IO.File]::WriteAllText($manifestPath, $manifest, (New-Object System.Text.UTF8Encoding($false)))
$keys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ssdownloadmanager",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.ssdownloadmanager",
  "HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.ssdownloadmanager",
  "HKCU:\Software\Mozilla\NativeMessagingHosts\com.ssdownloadmanager"
)
foreach ($key in $keys) {
  New-Item -Path $key -Force | Out-Null
  Set-Item -Path $key -Value $manifestPath
}
Write-Host "Native host registered for Chrome, Edge, Brave, and Firefox."
