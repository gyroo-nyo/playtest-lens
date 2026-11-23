; Playtest Lens installer (Inno Setup 6). Built by .github/workflows/release.yml from the repo root:
;   iscc /DMyVersion=0.1.0 packaging\windows\setup.iss
#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif

[Setup]
AppId={{6B0E2C1A-6F3D-4B8E-9A51-7C2D4E8F1A30}
AppName=Playtest Lens
AppVersion={#MyVersion}
AppPublisher=gyroo-nyo
AppPublisherURL=https://github.com/gyroo-nyo/playtest-lens
SourceDir=..\..
DefaultDirName={localappdata}\Programs\Playtest Lens
DefaultGroupName=Playtest Lens
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=PlaytestLens-Setup
SetupIconFile=packaging\windows\lens.ico
UninstallDisplayIcon={app}\PlaytestLens.exe
LicenseFile=LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\PlaytestLens\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Playtest Lens"; Filename: "{app}\PlaytestLens.exe"
Name: "{group}\Playtest Lens (saved bugs, no phone)"; Filename: "{app}\PlaytestLens.exe"; Parameters: "ui"
Name: "{group}\Uninstall Playtest Lens"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Playtest Lens"; Filename: "{app}\PlaytestLens.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PlaytestLens.exe"; Description: "Start Playtest Lens now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; adb leaves a server running, which would keep adb.exe locked
Filename: "{app}\tools\adb.exe"; Parameters: "kill-server"; Flags: runhidden; RunOnceId: "KillAdb"
