#define AppName "Analyse PME"
#define AppVersion "1.0.0"

[Setup]
AppId={{36A8C56A-0C4F-4F47-A64C-663C73427E0C}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Analyse PME
DefaultGroupName={#AppName}
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\Installateur
OutputBaseFilename=AnalysePME-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AnalysePME.exe

[Files]
Source: "dist\AnalysePME\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "build\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\AnalysePME.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AnalysePME.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis supplémentaires :"; Flags: unchecked

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installation du composant WebView2..."; Flags: runhidden waituntilterminated
Filename: "{app}\AnalysePME.exe"; Description: "Lancer Analyse PME"; Flags: postinstall nowait skipifsilent
