#define MyAppName "ffupscale"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Kian Young"
#define MyAppURL "https://github.com/kianyng/ffupscale"
#define MyAppExeName "ffupscale.exe"

[Setup]
AppId={{eccb0d6b-746c-4606-bc95-0986f8c1d130}

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}

AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

LicenseFile=LICENSE

SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

OutputDir=installer-output
OutputBaseFilename=ffupscale-v{#MyAppVersion}-setup

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

PrivilegesRequired=admin

VersionInfoVersion=1.0.1.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=ffupscale Windows installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
    Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; \
    Flags: unchecked

[Files]
Source: "release-folder\ffupscale\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

Source: "LICENSE"; \
    DestDir: "{app}"; \
    Flags: ignoreversion

Source: "THIRD_PARTY_NOTICES.md"; \
    DestDir: "{app}"; \
    Flags: ignoreversion

Source: "licenses\*"; \
    DestDir: "{app}\licenses"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"

Name: "{autodesktop}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent