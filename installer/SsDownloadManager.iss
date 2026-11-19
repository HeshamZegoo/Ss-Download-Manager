#define MyAppName "Ss Download Manager"
#define MyAppVersion "1.0.0"
#define MyPublisher "HeshamZegoo"
[Setup]
AppId={{6F81A59E-2D32-4B95-9D54-4D85E6A4A8B2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={localappdata}\Programs\Ss Download Manager
DefaultGroupName={#MyAppName}
SetupIconFile=..\dist\SsDownloadManager.ico
UninstallDisplayIcon={app}\SsDownloadManager.exe
OutputDir=..\dist
OutputBaseFilename=Ss-Download-Manager-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "browserhelper"; Description: "Prepare browser integration"; GroupDescription: "Browser integration:"; Flags: checkedonce
[Files]
Source: "..\dist\SsDownloadManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\ssdm-native-host.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\SsDownloadManager.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\browser\chromium\*"; DestDir: "{app}\browser\chromium"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\browser\firefox\*"; DestDir: "{app}\browser\firefox"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\tools\register-browser-host.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\COPYRIGHT.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Ss Download Manager"; Filename: "{app}\SsDownloadManager.exe"
Name: "{autodesktop}\Ss Download Manager"; Filename: "{app}\SsDownloadManager.exe"; Tasks: desktopicon
Name: "{group}\Browser setup instructions"; Filename: "{app}\Browser-Setup.txt"
[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\register-browser-host.ps1"""; StatusMsg: "Registering browser integration..."; Flags: runhidden waituntilterminated; Tasks: browserhelper
Filename: "{app}\SsDownloadManager.exe"; Description: "Launch Ss Download Manager"; Flags: postinstall nowait skipifsilent
