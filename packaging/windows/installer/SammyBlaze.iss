#ifndef StageRoot
  #error StageRoot must be supplied by build-installer.ps1
#endif
#ifndef ProductVersion
  #error ProductVersion must be supplied by build-installer.ps1
#endif
#ifndef InstallerFileVersion
  #error InstallerFileVersion must be supplied by build-installer.ps1
#endif
#ifndef OutputRoot
  #error OutputRoot must be supplied by build-installer.ps1
#endif

#define ProductName "SammyBlaze"
#define PublisherName "SammyBlaze"
#define ProductUrl "https://github.com/shishirsambabu/sammyblaze.wav"
#define StandaloneSource StageRoot + "\standalone\SammyBlaze"
#define Vst3Source StageRoot + "\VST3\SammyBlaze.vst3"
#define InstallerBaseName "SammyBlaze-Setup-" + ProductVersion + "-windows-x64"

[Setup]
AppId={{057B9837-B038-4693-8376-0F1EB7FE6524}
AppName={#ProductName}
AppVersion={#ProductVersion}
AppVerName={#ProductName} {#ProductVersion}
AppPublisher={#PublisherName}
AppPublisherURL={#ProductUrl}
AppSupportURL={#ProductUrl}
AppUpdatesURL={#ProductUrl}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\SammyBlaze
DefaultGroupName=SammyBlaze
DisableProgramGroupPage=yes
OutputDir={#OutputRoot}
OutputBaseFilename={#InstallerBaseName}
VersionInfoVersion={#InstallerFileVersion}
VersionInfoTextVersion={#ProductVersion}
VersionInfoCompany={#PublisherName}
VersionInfoDescription=SammyBlaze standalone and VST3 installer
VersionInfoProductName={#ProductName}
VersionInfoProductVersion={#InstallerFileVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
MinVersion=10.0.17763
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\SammyBlaze.exe
UninstallDisplayName={#ProductName} {#ProductVersion}
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
#ifdef SignInstaller
SignTool=sammyblaze
SignedUninstaller=yes
#else
SignedUninstaller=no
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "vst3"; Description: "Install the VST3 instrument"; GroupDescription: "Components:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\release-metadata"
Type: filesandordirs; Name: "{code:GetVst3BundleDir}"; Check: ShouldInstallVst3

[Files]
Source: "{#StandaloneSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Vst3Source}\*"; DestDir: "{code:GetVst3BundleDir}"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: vst3
Source: "{#StageRoot}\manifest.json"; DestDir: "{app}\release-metadata"; Flags: ignoreversion
Source: "{#StageRoot}\SHA256SUMS.txt"; DestDir: "{app}\release-metadata"; Flags: ignoreversion

[Icons]
Name: "{group}\SammyBlaze Performer"; Filename: "{app}\SammyBlaze.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall SammyBlaze"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SammyBlaze Performer"; Filename: "{app}\SammyBlaze.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\SammyBlaze"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKA; Subkey: "Software\SammyBlaze"; ValueType: string; ValueName: "VST3Dir"; ValueData: "{code:GetVst3Dir}"; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: vst3
Root: HKA; Subkey: "Software\SammyBlaze"; ValueType: string; ValueName: "Version"; ValueData: "{#ProductVersion}"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
Filename: "{app}\SammyBlaze.exe"; Description: "Launch SammyBlaze Performer"; Flags: nowait postinstall skipifsilent

[Code]
var
  Vst3DirPage: TInputDirWizardPage;
  PreviousVst3Dir: String;

function InstallRegistryRoot: Integer;
begin
  if IsAdminInstallMode then
    Result := HKLM
  else
    Result := HKCU;
end;

function RequestedVst3Dir: String;
var
  CommandLineValue: String;
begin
  CommandLineValue := ExpandConstant('{param:VST3DIR|}');
  if CommandLineValue <> '' then
    Result := CommandLineValue
  else
    Result := ExpandConstant('{commoncf64}\VST3');
end;

function ShouldInstallVst3: Boolean;
begin
  Result := WizardIsTaskSelected('vst3');
end;

function GetVst3Dir(Param: String): String;
begin
  if Assigned(Vst3DirPage) then
    Result := Vst3DirPage.Values[0]
  else
    Result := RequestedVst3Dir;
end;

function GetVst3BundleDir(Param: String): String;
begin
  Result := AddBackslash(GetVst3Dir('')) + 'SammyBlaze.vst3';
end;

function IsSafeVst3Root(Candidate: String): Boolean;
var
  Expanded: String;
  Drive: String;
begin
  Expanded := ExpandFileName(Trim(Candidate));
  Drive := ExtractFileDrive(Expanded);
  Result :=
    (Trim(Candidate) <> '') and
    (Drive <> '') and
    (CompareText(AddBackslash(Expanded), AddBackslash(Drive)) <> 0);
end;

procedure InitializeWizard;
var
  RememberedVst3Dir: String;
begin
  PreviousVst3Dir := '';
  RegQueryStringValue(
    InstallRegistryRoot,
    'Software\SammyBlaze',
    'VST3Dir',
    PreviousVst3Dir);

  RememberedVst3Dir := GetPreviousData('VST3Dir', RequestedVst3Dir);
  Vst3DirPage := CreateInputDirPage(
    wpSelectTasks,
    'VST3 plug-in folder',
    'Choose where the VST3 instrument will be installed.',
    'Use the standard Common Files VST3 directory unless your DAW scans a custom folder.',
    False,
    '');
  Vst3DirPage.Add('');
  Vst3DirPage.Values[0] := RememberedVst3Dir;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = Vst3DirPage.ID) and not ShouldInstallVst3;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = Vst3DirPage.ID) and ShouldInstallVst3 then
  begin
    if not IsSafeVst3Root(Vst3DirPage.Values[0]) then
    begin
      MsgBox(
        'Choose an absolute VST3 folder below a drive or network root.',
        mbError,
        MB_OK);
      Result := False;
    end;
  end;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if ShouldInstallVst3 then
    SetPreviousData(PreviousDataKey, 'VST3Dir', GetVst3Dir(''));
end;

procedure RemovePreviousVst3IfMoved;
var
  OldBundle: String;
  NewBundle: String;
begin
  if (PreviousVst3Dir = '') or not ShouldInstallVst3 then
    Exit;

  OldBundle := AddBackslash(PreviousVst3Dir) + 'SammyBlaze.vst3';
  NewBundle := GetVst3BundleDir('');
  if CompareText(OldBundle, NewBundle) <> 0 then
    DelTree(OldBundle, True, True, True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemovePreviousVst3IfMoved;
end;
