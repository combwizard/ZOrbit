; Inno Setup 6 script for ZOrbit, a radial brush menu for ZBrush.
; Build: ISCC.exe /DAppVersion=0.11.0 packaging\installer.iss   (packaging\build.ps1 does this after PyInstaller)
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
; DefDir (see [Code]) offers the folder of the current ZOrbit install, so an update keeps a custom folder, and the
; default folder otherwise.
DefaultDirName={code:DefDir}
; UsePreviousAppDir=yes would also offer the folder of a Radial Menu install (same AppId, 0.7.0 and earlier) and put
; ZOrbit there. DefDir does the same job but only accepts a folder that holds ZOrbit.exe, so a Radial Menu install
; moves to the new folder and CleanUpLegacy removes the old one.
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
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Each build replaces the onedir contents as a whole, so files an older build had must not stay behind. Only in a
; folder that already holds ZOrbit (or Radial Menu), so a folder picked by hand is never emptied of other programs'
; files. {app}\bridge is left alone: ZBrush keeps its __pycache__ there and has the folder registered.
Type: filesandordirs; Name: "{app}\_internal"; Check: HoldsOurApp
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

[UninstallDelete]
; Files made after install (ZBrush compiles the bridge into __pycache__), so the folders can go.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\bridge\__pycache__"
Type: dirifempty; Name: "{app}\bridge"
Type: dirifempty; Name: "{app}"

[Code]
const
  EnvKey = 'Environment';
  EnvValue = 'ZBRUSH_PLUGIN_PATH';
  MachineEnvKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  HKCU_HANDLE = $80000001;
  HKLM_HANDLE = $80000002;
  RRF_RT_ANY = $0000FFFF;
  RRF_NOEXPAND = $10000000;
  REG_EXPAND_SZ_TYPE = 2;
  { Mutexes that mean a Studio is open (it can hold unsaved edits): ZOrbit's, and Radial Menu's from before the
    rename. The app itself holds Local\ZOrbit and the browser Local\ZOrbitPopout; neither has anything unsaved. }
  StudioMutexes = 'Local\ZOrbitStudio,Local\RadialMenuStudio';
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F1B7C52-3D4A-4E8B-9A57-2C0E81D4B9A3}_is1';

var
  LegacyDir: String;                        { a Radial Menu install this setup replaces, or '' }
  PluginLeftovers: String;                  { ZBrush folders whose plugin could not be removed, one per line }

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

{ True if ZBRUSH_PLUGIN_PATH exists under Root\Key and is REG_EXPAND_SZ. }
function ValueIsExpandSz(Root: Cardinal; const Key: String): Boolean;
var
  ValType, Size: Cardinal;
begin
  ValType := 0;
  Size := 0;
  Result := (RegGetValueW(Root, Key, EnvValue, RRF_RT_ANY or RRF_NOEXPAND, ValType, 0, Size) = 0)
    and (ValType = REG_EXPAND_SZ_TYPE);
end;

procedure WriteEnvValue(const Value: String; AsExpand: Boolean);
begin
  if AsExpand then
    RegWriteExpandStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Value)
  else
    RegWriteStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Value);
end;

{ Adds our bridge folder to the USER variable ZBRUSH_PLUGIN_PATH; every existing entry is kept as it is.
  Windows uses the user value of this variable and ignores the machine one. So when the user has no value yet, the
  new one starts from the machine entries (if there are any) followed by ours. The machine value is only read. }
procedure RegisterBridge;
var
  Current, Dir, Base: String;
  Expand: Boolean;
begin
  Dir := AppBridgeDir;
  if RegQueryStringValue(HKEY_CURRENT_USER, EnvKey, EnvValue, Current) then
    Expand := ValueIsExpandSz(HKCU_HANDLE, EnvKey)
  else
  begin
    if not RegQueryStringValue(HKEY_LOCAL_MACHINE, MachineEnvKey, EnvValue, Current) then
      Current := '';
    Expand := ValueIsExpandSz(HKLM_HANDLE, MachineEnvKey);
  end;
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
    WriteEnvValue(NewValue, ValueIsExpandSz(HKCU_HANDLE, EnvKey));
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

{ Used by the _internal entry of [InstallDelete]: true when the install folder already holds ZOrbit or Radial Menu. }
function HoldsOurApp: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\{#AppExe}')) or FileExists(ExpandConstant('{app}\{#LegacyExe}'));
end;

{ Waits about a second. Exec keeps the wizard answering messages while it waits; Sleep would not. }
procedure PauseOneSecond;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\ping.exe'), '-n 2 127.0.0.1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function StudioIsOpen: Boolean;
begin
  Result := CheckForMutexes(StudioMutexes);
end;

{ Closes the running programs the way a user would, so a Studio with unsaved edits shows its own dialog first:
  taskkill without /F posts WM_CLOSE. Waits up to 15 seconds for Studio to go. If it is still open (the user
  has not answered, or chose to keep editing) nothing is killed and the result is False. Otherwise whatever is
  still running (the app, the browser; they hold nothing unsaved) is ended with /F and the result is True. }
function StopApp: Boolean;
var
  ResultCode, Waited: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExe} /IM {#LegacyExe}', '', SW_HIDE, ewWaitUntilTerminated,
    ResultCode);
  Waited := 0;
  while StudioIsOpen and (Waited < 15) do
  begin
    PauseOneSecond;
    Waited := Waited + 1;
  end;
  Result := not StudioIsOpen;
  if Result then
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe} /IM {#LegacyExe}', '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode);
    PauseOneSecond;                         { lets Windows release the exe and DLLs }
  end;
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

{ DefaultDirName: the folder of the ZOrbit install this setup updates (so a custom folder is kept), else the default
  one. The uninstall entry has the same AppId as Radial Menu's, so its folder is only taken when it holds ZOrbit.exe;
  a Radial Menu folder holds RadialMenu.exe and falls through to the default. }
function DefDir(Param: String): String;
var
  Prev: String;
begin
  Result := ExpandConstant('{localappdata}\Programs\ZOrbit');
  if RegQueryStringValue(HKEY_CURRENT_USER, UninstallKey, 'Inno Setup: App Path', Prev) then
  begin
    Prev := RemoveBackslashUnlessRoot(Prev);
    if (Prev <> '') and FileExists(Prev + '\{#AppExe}') then
      Result := Prev;
  end;
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
  Result := '';
  LegacyDir := FindLegacyDir;               { before the install rewrites the uninstall entry }
  { Close the running programs so an upgrade can replace the exe and its DLLs, but never kill a Studio that is
    still open (it may have unsaved edits): stop here instead. }
  if not StopApp then
    Result := 'Close ZOrbit Studio first (it may have unsaved changes), then run Setup again.';
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

{ Stops here, before anything is asked or removed, if a Studio is open: it may have unsaved edits. }
function InitializeUninstall: Boolean;
begin
  Result := not StudioIsOpen;
  if not Result then
    SuppressibleMsgBox('Close ZOrbit Studio first (it may have unsaved changes), then run the uninstaller again.',
      mbError, MB_OK, IDOK);
end;

{ Takes ZOrbit's ZScript plugin out of one ZBrush 2022 to 2025 folder (ZPlugs64). It lives under Program Files, so
  the app's own remover runs elevated (one UAC prompt). The result is judged by whether the file is gone. }
procedure RemoveZScriptPlugin(const ZPlugs: String);
var
  ResultCode: Integer;
begin
  ShellExec('runas', ExpandConstant('{app}\{#AppExe}'),
    '--zscript-remove "' + ExpandConstant('{app}\stage') + '" "' + ZPlugs + '"', '', SW_HIDE, ewWaitUntilTerminated,
    ResultCode);
  if FileExists(ZPlugs + '\ZOrbitBridge.zsc') then
    PluginLeftovers := PluginLeftovers + #13#10 + ZPlugs;
end;

{ Looks in every folder that matches Pattern (like C:\Program Files\Maxon ZBrush 20??) for our plugin. }
procedure FindAndRemoveZScriptPlugins(const Pattern: String);
var
  FindRec: TFindRec;
  ZPlugs: String;
begin
  if FindFirst(Pattern, FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          ZPlugs := ExtractFilePath(Pattern) + FindRec.Name + '\ZStartup\ZPlugs64';
          if FileExists(ZPlugs + '\ZOrbitBridge.zsc') then
            RemoveZScriptPlugin(ZPlugs);
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

{ Best effort, never fails the uninstall. Only the usual ZBrush folders are searched; a ZBrush the user added by
  hand in Studio is not found. Says so for any folder where the plugin is still there. }
procedure RemoveZScriptPlugins;
begin
  PluginLeftovers := '';
  FindAndRemoveZScriptPlugins(ExpandConstant('{commonpf}\Maxon ZBrush 20??'));
  FindAndRemoveZScriptPlugins(ExpandConstant('{commonpf}\Pixologic\ZBrush 20??'));
  FindAndRemoveZScriptPlugins(ExpandConstant('{commonpf}\Maxon\ZBrush 20??'));
  if PluginLeftovers <> '' then
    SuppressibleMsgBox('ZOrbit could not remove its plugin from these ZBrush folders:' + #13#10 + PluginLeftovers
      + #13#10#13#10 + 'To finish, delete ZOrbitBridge.zsc and the ZOrbitData folder from each of them.',
      mbInformation, MB_OK, IDOK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    StopApp;
    RemoveZScriptPlugins;                   { while ZOrbit.exe is still here to do it }
  end
  else if CurUninstallStep = usPostUninstall then
  begin
    UnregisterBridgeDir(AppBridgeDir);
    RemoveLaunchFileIfOurs;
  end;
end;
