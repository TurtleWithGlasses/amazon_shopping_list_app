; Inno Setup script for Price Tracker.
; Build the app first (build.bat), then compile this with Inno Setup:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\PriceTracker.iss
; Output: installer\Output\PriceTracker-Setup.exe

#define AppName "Price Tracker"
#define AppVersion "0.2.0"
#define AppExe "PriceTracker.exe"

[Setup]
; A stable AppId keeps upgrades/uninstall consistent across versions.
AppId={{8B3F1C2A-7E54-4D9B-9A21-2C6F0E5D4B10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Price Tracker
DefaultDirName={autopf}\PriceTracker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PriceTracker-Setup
SetupIconFile=..\assets\icons\cart.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Per-user install: no admin elevation, avoids UAC and reduces SmartScreen friction.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Bundles the entire one-folder PyInstaller build.
Source: "..\dist\PriceTracker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
