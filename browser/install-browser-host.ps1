param(
  [Parameter(Mandatory=$true)][string]$InstallDir,
  [Parameter(Mandatory=$true)][string]$ChromiumExtensionId
)
$ErrorActionPreference = "Stop"
$hostExe = Join-Path $InstallDir "ssdm-native-host.exe"
if (!(Test-Path $hostExe)) { throw "Native host executable not found: $hostExe" }
$template = Join-Path $PSScriptRoot "native-host/com.ssdownloadmanager.json.template"
$manifest = Get-Content $template -Raw
$manifest = $manifest.Replace("__INSTALL_DIR__", $InstallDir.Replace("", "\"))
$manifest = $manifest.Replace("__CHROMIUM_EXTENSION_ID__", $ChromiumExtensionId)
$manifestPath = Join-Path $InstallDir "com.ssdownloadmanager.json"
Set-Content -Path $manifestPath -Value $manifest -Encoding UTF8
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
Write-Host "Native host registered. Install the matching extension from browser/chromium or browser/firefox."
