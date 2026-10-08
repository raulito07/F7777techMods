; Inno Setup — F7777techMods 0.1.0
; Privilegios de usuario; no toca Steam/Vortex; conserva datos al desinstalar.

#define MyAppName "F7777techMods"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Four Seven Tech"
#define MyAppAuthor "Raul Ruano Gil"
#define MyAppExeName "F7777techMods.exe"

[Setup]
AppId=FourSevenTech.F7777techMods
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright (c) 2026 Raul Ruano Gil
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
InfoBeforeFile=..\packaging\INFO_BEFORE.txt
OutputDir=..\dist\release
OutputBaseFilename=F7777techMods_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupLogging=yes
CloseApplications=no
RestartIfNeededByRun=no
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; Los datos en %LOCALAPPDATA%\FourSevenTech\F7777techMods NO se borran al desinstalar

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\F7777techMods\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\README_DISTRIBUCION.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
