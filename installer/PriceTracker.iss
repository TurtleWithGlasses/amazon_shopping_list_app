; Inno Setup script for Price Tracker.
; Build the app first (build.bat), then compile this with Inno Setup
; (ISCC.exe installer\PriceTracker.iss) to produce installer\Output\PriceTracker-Setup.exe

#define AppName "Price Tracker"
#define AppVersion "0.1.0"
#define AppExe "PriceTracker.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Price Tracker
DefaultDirName={autopf}\PriceTracker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PriceTracker-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern

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
