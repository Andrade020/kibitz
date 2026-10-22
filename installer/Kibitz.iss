; Instalador do Kibitz (Inno Setup 6). Uso: iscc /DAppVersion=0.1.0-beta.1 /DFileVersion=0.1.0.1 Kibitz.iss
#ifndef AppVersion
  #define AppVersion "0.1.0-beta.1"
#endif
#ifndef FileVersion
  #define FileVersion "0.1.0.1"
#endif
#define AppName "Kibitz"
#define AppExe "Kibitz.exe"

[Setup]
AppId={{7D3A5C61-2B4E-4F0A-9E5B-6C1A0F2D8B34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Lucas Rafael de Andrade
AppPublisherURL=https://github.com/Andrade020/kibitz
AppSupportURL=https://github.com/Andrade020/kibitz/issues
AppUpdatesURL=https://github.com/Andrade020/kibitz/releases
VersionInfoVersion={#FileVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription=Instalador do {#AppName}
; instalação por usuário: não pede administrador (menos telas de permissão) e instala em %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Kibitz
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\build\installer
OutputBaseFilename=Kibitz-{#AppVersion}-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
InfoBeforeFile=NOTICE.txt
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installclaude"; Description: "Instalar o Claude Code (necessário para jogar com a sua conta do Claude; dispensável se for usar uma chave de API)"; GroupDescription: "Componentes:"; Check: WingetAvailable

[Files]
Source: "..\build\dist\Kibitz\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\stockfish_pkg\*"; DestDir: "{app}\bin"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{cmd}"; Parameters: "/c winget install --id Anthropic.ClaudeCode --exact --source winget --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando o Claude Code (pode levar alguns minutos)..."; Flags: runhidden; Tasks: installclaude
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function WingetAvailable: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/c winget --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Kibitz');
    if DirExists(DataDir) then
      if SuppressibleMsgBox('Remover também as suas partidas e configurações?' + #13#10 + DataDir + #13#10#13#10 +
                '(Escolha "Não" para guardá-las caso reinstale depois.)', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
