; Inno Setup 6 script for ZOrbit, a radial brush menu for ZBrush.
; Build: ISCC.exe /DAppVersion=0.10.1 packaging\installer.iss   (packaging\build.ps1 does this after PyInstaller)
; Expects dist\ZOrbit\ (PyInstaller onedir output) relative to the repository root.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#define AppName "ZOrbit"
#define AppExe "ZOrbit.exe"
#define AppURL "https://github.com/combwizard/zorbit"
; Before the rename (0.7.0 and earlier) the app was Radial Menu for ZBrush, with the same AppId.
#define LegacyExe "RadialMenu.exe"
#define LegacyName "Radial Menu"

[Setup]
; Fixed GUID: identifies the app for upgrades and uninstall. Never change it.
AppId={{6F1B7C52-3D4A-4E8B-9A57-2C0E81D4B9A3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=combwizard
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
DefaultDirName={localappdata}\Programs\ZOrbit
; An upgrade from Radial Menu moves to the new folder; CleanUpLegacy removes the old one.
UsePreviousAppDir=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=Output
OutputBaseFilename=ZOrbitSetup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
CloseApplications=yes
CloseApplicationsFilter={#AppExe},{#LegacyExe}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
FinishedLabel=Setup has finished installing [name] on your computer.%n%nRestart ZBrush once so it loads the ZOrbit plugin.
FinishedLabelNoIcons=Setup has finished installing [name] on your computer.%n%nRestart ZBrush once so it loads the ZOrbit plugin.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\ZOrbit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\bridge\zorbit_bridge.py"; DestDir: "{app}\bridge"; Flags: ignoreversion

[InstallDelete]
; Left by Radial Menu when it was installed in this same folder, or its shortcuts.
Type: files; Name: "{app}\{#LegacyExe}"
Type: files; Name: "{app}\bridge\radial_menu_bridge.py"
Type: files; Name: "{autoprograms}\{#LegacyName} Studio.lnk"
Type: files; Name: "{autodesktop}\{#LegacyName} Studio.lnk"

[Icons]
Name: "{autoprograms}\ZOrbit Studio"; Filename: "{app}\{#AppExe}"; Parameters: "--studio"; WorkingDir: "{app}"; AppUserModelID: "ZOrbit.Studio"; Comment: "Edit radial menus for ZBrush"
Name: "{autoprograms}\ZOrbit Browser"; Filename: "{app}\{#AppExe}"; Parameters: "--popout --show"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\browser.ico"; AppUserModelID: "ZOrbit.Browser"; Comment: "Browse and tag ZBrush brushes, alphas, materials and textures"
Name: "{autodesktop}\ZOrbit Studio"; Filename: "{app}\{#AppExe}"; Parameters: "--studio"; WorkingDir: "{app}"; AppUserModelID: "ZOrbit.Studio"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--studio"; Description: "Open ZOrbit Studio"; Flags: nowait postinstall skipifsilent

[Code]
const
  EnvKey = 'Environment';
  EnvValue = 'ZBRUSH_PLUGIN_PATH';
  HKCU_HANDLE = $80000001;
  RRF_RT_ANY = $0000FFFF;
  RRF_NOEXPAND = $10000000;
  REG_EXPAND_SZ_TYPE = 2;
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F1B7C52-3D4A-4E8B-9A57-2C0E81D4B9A3}_is1';

var
  LegacyDir: String;                        { a Radial Menu install this setup replaces, or '' }

function RegGetValueW(hKey: Cardinal; lpSubKey, lpValue: String; dwFlags: Cardinal;
  var pdwType: Cardinal; pvData: Cardinal; var pcbData: Cardinal): Integer;
  external 'RegGetValueW@advapi32.dll stdcall';

{ ---- helpers ---------------------------------------------------------------------------------------- }

function AppBridgeDir: String;
begin
  Result := ExpandConstant('{app}\bridge');
end;

{ Normalised form for comparing path-list entries: trimmed, no trailing backslash, lower case. }
function NormEntry(S: String): String;
begin
  Result := Trim(S);
  while (Length(Result) > 0) and (Result[Length(Result)] = '\') do
    Delete(Result, Length(Result), 1);
  Result := Lowercase(Result);
end;

{ Splits a semicolon list into its non-empty (trimmed) entries. }
procedure SplitList(const List: String; var Parts: TArrayOfString);
var
  Rest, Item: String;
  P, N: Integer;
begin
  SetArrayLength(Parts, 0);
  Rest := List;
  while Rest <> '' do
  begin
    P := Pos(';', Rest);
    if P = 0 then
    begin
      Item := Rest;
      Rest := '';
    end else
    begin
      Item := Copy(Rest, 1, P - 1);
      Rest := Copy(Rest, P + 1, Length(Rest));
    end;
    Item := Trim(Item);
    if Item <> '' then
    begin
      N := GetArrayLength(Parts);
      SetArrayLength(Parts, N + 1);
      Parts[N] := Item;
    end;
  end;
end;

function ListHasEntry(const List, Entry: String): Boolean;
var
  Parts: TArrayOfString;
  I: Integer;
begin
  Result := False;
  SplitList(List, Parts);
  for I := 0 to GetArrayLength(Parts) - 1 do
    if NormEntry(Parts[I]) = NormEntry(Entry) then
    begin
      Result := True;
      Exit;
    end;
end;

function ListWithoutEntry(const List, Entry: String): String;
var
  Parts: TArrayOfString;
  I: Integer;
begin
  Result := '';
  SplitList(List, Parts);
  for I := 0 to GetArrayLength(Parts) - 1 do
    if NormEntry(Parts[I]) <> NormEntry(Entry) then
    begin
      if Result <> '' then
        Result := Result + ';';
      Result := Result + Parts[I];
    end;
end;

{ True if the user-level value exists and is REG_EXPAND_SZ. }
function EnvValueIsExpandSz: Boolean;
var
  ValType, Size: Cardinal;
begin
  ValType := 0;
  Size := 0;
  Result := (RegGetValueW(HKCU_HANDLE, EnvKey, EnvValue, RRF_RT_ANY or RRF_NOEXPAND, ValType, 0, Size) = 0)
    and (ValType = REG_EXPAND_SZ_TYPE);
end;

procedure WriteEnvValue(const Value: String; AsExpand: Boolean);
begin
  if AsExpand then
    RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Value)
  else
    RegWriteStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Value);
end;

{ Adds our bridge folder to the USER variable ZBRUSH_PLUGIN_PATH; every existing entry is kept as it is. }
procedure RegisterBridge;
var
  Current, Dir, Base: String;
  Expand: Boolean;
begin
  Dir := AppBridgeDir;
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Current) then
    Current := '';
  Expand := EnvValueIsExpandSz;
  if ListHasEntry(Current, Dir) then
    Exit;                                   { already there (upgrade install) }
  Base := Trim(Current);
  while (Length(Base) > 0) and (Base[Length(Base)] = ';') do
    Delete(Base, Length(Base), 1);
  if Base = '' then
    WriteEnvValue(Dir, Expand)
  else
    WriteEnvValue(Base + ';' + Dir, Expand);
end;

{ Removes only that entry; deletes the variable if nothing is left. }
procedure UnregisterBridgeDir(const Dir: String);
var
  Current, NewValue: String;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Current) then
    Exit;
  if not ListHasEntry(Current, Dir) then
    Exit;
  NewValue := ListWithoutEntry(Current, Dir);
  if NewValue = '' then
    RegDeleteValue(HKEY_CURRENT_USER, EnvKey, EnvValue)
  else
    WriteEnvValue(NewValue, EnvValueIsExpandSz);
end;

{ JSON string body: escapes backslash and quote; non-ASCII becomes \uXXXX so the file stays plain ASCII. }
function JsonEscape(const S: String): String;
var
  I, C: Integer;
  Hex: String;
begin
  Hex := '0123456789abcdef';
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := Ord(S[I]);
    if S[I] = '\' then
      Result := Result + '\\'
    else if S[I] = '"' then
      Result := Result + '\"'
    else if (C < 32) or (C > 126) then
      Result := Result + '\u' + Hex[((C shr 12) and 15) + 1] + Hex[((C shr 8) and 15) + 1]
        + Hex[((C shr 4) and 15) + 1] + Hex[(C and 15) + 1]
    else
      Result := Result + S[I];
  end;
end;

function LaunchFilePath: String;
begin
  Result := ExpandConstant('{userappdata}\ZOrbit\launch.json');
end;

{ Tells the ZBrush bridge how to start this installation (the app also refreshes this file on every start). }
procedure WriteLaunchFile;
var
  Exe, Json: String;
begin
  Exe := JsonEscape(ExpandConstant('{app}\{#AppExe}'));
  ForceDirectories(ExtractFilePath(LaunchFilePath));
  Json := '{' + #13#10 +
    '  "app": ["' + Exe + '", "--exit-with-zbrush"],' + #13#10 +
    '  "studio": ["' + Exe + '", "--studio"],' + #13#10 +
    '  "version": "{#AppVersion}",' + #13#10 +
    '  "frozen": true' + #13#10 +
    '}' + #13#10;
  SaveStringToFile(LaunchFilePath, Json, False);
end;

{ Removes launch.json only if it still points at this installation. The user's menus are left alone. }
procedure RemoveLaunchFileIfOurs;
var
  Text: AnsiString;
begin
  if LoadStringFromFile(LaunchFilePath, Text) then
    if Pos(Lowercase(JsonEscape(ExpandConstant('{app}\{#AppExe}'))), Lowercase(String(Text))) > 0 then
      DeleteFile(LaunchFilePath);
end;

procedure StopApp;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe} /IM {#LegacyExe}', '', SW_HIDE, ewWaitUntilTerminated,
    ResultCode);
end;

{ ---- upgrade from Radial Menu ----------------------------------------------------------------------- }

{ Where Radial Menu is installed, from the uninstall entry this setup is about to take over (same AppId). }
function FindLegacyDir: String;
begin
  Result := '';
  if not RegQueryStringValue(HKEY_CURRENT_USER, UninstallKey, 'Inno Setup: App Path', Result) then
    Result := ExpandConstant('{localappdata}\Programs\{#LegacyName}');
  Result := RemoveBackslashUnlessRoot(Result);
  if not FileExists(Result + '\{#LegacyExe}') then
    Result := '';
end;

{ Removes what Radial Menu installed in its own folder (only the files it put there) and its ZBrush plugin path
  entry, plus its launch.json. The user's menus stay in its data folders; the app copies them on first start. }
procedure CleanUpLegacy;
var
  OldLaunch: String;
  Text: AnsiString;
begin
  OldLaunch := ExpandConstant('{userappdata}\RadialMenu\launch.json');
  if LoadStringFromFile(OldLaunch, Text) and (Pos(Lowercase('{#LegacyExe}'), Lowercase(String(Text))) > 0) then
    DeleteFile(OldLaunch);
  if (LegacyDir = '') or (NormEntry(LegacyDir) = NormEntry(ExpandConstant('{app}'))) then
    Exit;                                   { same folder: [InstallDelete] took care of it }
  UnregisterBridgeDir(LegacyDir + '\bridge');
  DelTree(LegacyDir + '\_internal', True, True, True);
  DelTree(LegacyDir + '\bridge', True, True, True);
  DeleteFile(LegacyDir + '\{#LegacyExe}');
  DeleteFile(LegacyDir + '\unins000.exe');
  DeleteFile(LegacyDir + '\unins000.dat');
  RemoveDir(LegacyDir);                     { only if nothing else is left in it }
end;

{ ---- setup events ----------------------------------------------------------------------------------- }

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  LegacyDir := FindLegacyDir;               { before the install rewrites the uninstall entry }
  StopApp;                                  { so an upgrade can replace the running exe and its DLLs }
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CleanUpLegacy;
    RegisterBridge;
    WriteLaunchFile;
  end;
end;

{ ---- uninstall events ------------------------------------------------------------------------------- }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopApp
  else if CurUninstallStep = usPostUninstall then
  begin
    UnregisterBridgeDir(AppBridgeDir);
    RemoveLaunchFileIfOurs;
  end;
end;
