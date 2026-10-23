; SWG Offline installer (Inno Setup 6). Built by Core3's "Windows build" workflow:
;   iscc /DAppVersion=0.1.0 /DLauncherExe=...\SWGOffline.exe /DServerDir=...\core3-windows installer.iss
;
; Installs per user (no admin): the launcher, and core3.exe with Core3's bin/ as "server".
; Never ships SOE files: it asks for the player's own SWG folder and the server reads the TREs there.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef LauncherExe
  #error Pass /DLauncherExe=path\to\SWGOffline.exe
#endif
#ifndef ServerDir
  #error Pass /DServerDir=path\to\core3-windows
#endif

[Setup]
AppId={{6E2C7B1D-3F4A-4C52-9B0E-5A1D7C8E2F31}
AppName=SWG Offline
AppVersion={#AppVersion}
AppPublisher=chinny-swg
AppPublisherURL=https://github.com/chinny-swg/swg-offline
DefaultDirName={localappdata}\Programs\SWG Offline
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=SWGOffline-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=installer-notice.txt
UninstallDisplayIcon={app}\SWGOffline.exe

[Files]
Source: "{#LauncherExe}"; DestDir: "{app}"; Flags: ignoreversion
; The server's own state (database, logs, launcher-written config) is never overwritten by an update
Source: "{#ServerDir}\*"; DestDir: "{app}\server"; Excludes: "conf\config-local.lua,conf\config-offline.lua,*-local.lua,databases\*,log\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\server\databases"
Name: "{app}\server\log"
Name: "{app}\server\log\admin"
Name: "{app}\server\navmeshes"

[Icons]
Name: "{autoprograms}\SWG Offline"; Filename: "{app}\SWGOffline.exe"
Name: "{autodesktop}\SWG Offline"; Filename: "{app}\SWGOffline.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Run]
Filename: "{app}\SWGOffline.exe"; Description: "Start SWG Offline"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Saved characters live in server\databases; they are kept unless the player deletes the folder
Type: files; Name: "{app}\install.json"
Type: files; Name: "{app}\server\conf\config-local.lua"
Type: files; Name: "{app}\server\conf\config-offline.lua"

[Code]
var
  SwgPage: TInputDirWizardPage;

const
  TreCount = 51;

function RequiredTre(I: Integer): String;
begin
  case I of
    0: Result := 'default_patch.tre';       1: Result := 'patch_sku1_14_00.tre';
    2: Result := 'patch_14_00.tre';         3: Result := 'patch_sku1_13_00.tre';
    4: Result := 'patch_13_00.tre';         5: Result := 'patch_sku1_12_00.tre';
    6: Result := 'patch_12_00.tre';         7: Result := 'patch_11_03.tre';
    8: Result := 'data_sku1_07.tre';        9: Result := 'patch_11_02.tre';
    10: Result := 'data_sku1_06.tre';       11: Result := 'patch_11_01.tre';
    12: Result := 'patch_11_00.tre';        13: Result := 'data_sku1_05.tre';
    14: Result := 'data_sku1_04.tre';       15: Result := 'data_sku1_03.tre';
    16: Result := 'data_sku1_02.tre';       17: Result := 'data_sku1_01.tre';
    18: Result := 'data_sku1_00.tre';       19: Result := 'patch_10.tre';
    20: Result := 'patch_09.tre';           21: Result := 'patch_08.tre';
    22: Result := 'patch_07.tre';           23: Result := 'patch_06.tre';
    24: Result := 'patch_05.tre';           25: Result := 'patch_04.tre';
    26: Result := 'patch_03.tre';           27: Result := 'patch_02.tre';
    28: Result := 'patch_01.tre';           29: Result := 'patch_00.tre';
    30: Result := 'data_other_00.tre';      31: Result := 'data_static_mesh_01.tre';
    32: Result := 'data_static_mesh_00.tre'; 33: Result := 'data_texture_07.tre';
    34: Result := 'data_texture_06.tre';    35: Result := 'data_texture_05.tre';
    36: Result := 'data_texture_04.tre';    37: Result := 'data_texture_03.tre';
    38: Result := 'data_texture_02.tre';    39: Result := 'data_texture_01.tre';
    40: Result := 'data_texture_00.tre';    41: Result := 'data_skeletal_mesh_01.tre';
    42: Result := 'data_skeletal_mesh_00.tre'; 43: Result := 'data_animation_00.tre';
    44: Result := 'data_sample_04.tre';     45: Result := 'data_sample_03.tre';
    46: Result := 'data_sample_02.tre';     47: Result := 'data_sample_01.tre';
    48: Result := 'data_sample_00.tre';     49: Result := 'data_music_00.tre';
    50: Result := 'bottom.tre';
  end;
end;

function MissingFromSwgFolder(Dir: String): String;
var
  I, Missing: Integer;
begin
  Result := '';
  if not FileExists(AddBackslash(Dir) + 'SWGEmu.exe') then
    Result := 'SWGEmu.exe';
  Missing := 0;
  for I := 0 to TreCount - 1 do
    if not FileExists(AddBackslash(Dir) + RequiredTre(I)) then begin
      if Missing < 3 then begin
        if Result <> '' then Result := Result + ', ';
        Result := Result + RequiredTre(I);
      end;
      Missing := Missing + 1;
    end;
  if Missing > 3 then
    Result := Result + Format(' and %d more TRE files', [Missing - 3]);
end;

procedure InitializeWizard;
begin
  SwgPage := CreateInputDirPage(wpSelectDir,
    'Your Star Wars Galaxies client',
    'Where is your SWGEmu-patched Pre-CU 14.1 client?',
    'Pick the folder that holds SWGEmu.exe and the .tre files. Nothing is copied from it: ' +
    'the game and the offline server both read it in place.',
    False, '');
  SwgPage.Add('');
  SwgPage.Values[0] := GetPreviousData('SwgDir', 'C:\SWGEmu');
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'SwgDir', SwgPage.Values[0]);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Missing: String;
begin
  Result := True;
  if CurPageID = SwgPage.ID then begin
    Missing := MissingFromSwgFolder(SwgPage.Values[0]);
    if Missing <> '' then begin
      MsgBox('That folder is missing ' + Missing + '.' + #13#10#13#10 +
        'Choose the folder of your own SWGEmu client (Pre-CU 14.1).', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function JsonEscape(S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\install.json'),
      '{"swg_dir": "' + JsonEscape(SwgPage.Values[0]) + '"}', False);
end;
