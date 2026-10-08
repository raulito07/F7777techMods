#define MyAppName "F7777techMods"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Four Seven Tech"

[Setup]
AppId={{A7F77777-4F53-4E54-B0C0-F7777TECH0002}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist\release
OutputBaseFilename=F7777techMods_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
SetupLogging=yes

[Files]
Source: "..\dist\F7777techMods\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\F7777techMods.exe"

[Run]
Filename: "{app}\F7777techMods.exe"; Flags: nowait postinstall skipifsilent
