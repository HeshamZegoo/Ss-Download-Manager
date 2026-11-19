$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --clean --onefile --name ssdm-native-host --console --paths . ssdm/native_host.py
Write-Host "Native host built at dist/ssdm-native-host.exe"
