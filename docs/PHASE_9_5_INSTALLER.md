# Phase 9.5: Windows installer foundation

## Purpose

Phase 9.5 converts the verified standalone and VST3 staging tree into one offline
Windows setup executable. The installer is a development release candidate, not
a public commercial release: signing, legal identity, clean-machine coverage,
forward-upgrade rollback, and DAW-host acceptance remain separate gates.

## Installer contract

- Inno Setup 6 compiles one x64 offline `.exe`.
- A permanently fixed application ID owns upgrade, repair, ARP, and uninstall
  identity.
- The default per-machine standalone destination is
  `C:\Program Files\SammyBlaze`.
- The default plug-in destination is
  `C:\Program Files\Common Files\VST3\SammyBlaze.vst3`.
- An advanced VST3 directory field supports a DAW-specific path such as
  `D:\VST3` without changing the standard default.
- VST3 and desktop-shortcut tasks are selectable; VST3 is selected by default.
- Upgrade cleanup removes only the managed `_internal`,
  `release-metadata`, and exact `SammyBlaze.vst3` trees. It never deletes the
  selected VST3 parent directory.
- User presets under local application data remain outside installer ownership.
- The complete release manifest and checksums are installed under
  `release-metadata` for support and audit.

## Clean-machine runtime policy

The distributed audio-core DLL and VST3 link the MSVC runtime statically. The
native release script inspects both product binaries with `dumpbin` and rejects
imports of `MSVCP*.dll` or `VCRUNTIME*.dll`. This avoids making a separately
installed Visual C++ redistributable an undeclared VST prerequisite.

Steinberg validation tools are not distributed. They use an isolated
dynamic-runtime build because Windows Smart App Control can block newly built
unsigned static test executables. The dynamic validator still exercises the
static product VST3 and passed all 47 tests.

## Input and build gates

`verify_release_stage.py` independently verifies:

1. schema, product, platform, version, and 40-character payload revision;
2. exact standalone, audio-core, hand-model, and VST3 artifact mappings;
3. every manifest size and SHA-256 value;
4. traversal-safe relative paths and duplicate rejection;
5. exact `SHA256SUMS.txt` coverage, including `manifest.json`.

`build-installer.ps1` refuses compilation unless the stage passes. Its generated
installer manifest records the payload revision and installer-source revision
separately, plus compiler version, input hashes, output size, SHA-256, and
Authenticode status.

## Development-machine evidence

The first candidate is:

```text
D:\SammyBlazeRelease\Installers\0.4.0-phase9.5-rc1\
  SammyBlaze-Setup-0.4.0-phase9.5-rc1-windows-x64.exe
```

Evidence:

- installer size: 98,622,886 bytes;
- installer SHA-256:
  `e0474a336a55fba92a8a3a79c0be9a9d5a90ed34c3d1768daff9cbe20119519a`;
- payload revision: `1094242cf32e1541daa4c684f650afe59d14721f`;
- compiled installer-source revision:
  `af0b078c10a1a0c847b2a5113efd76b47112dc2b`;
- 295 installed payload files verified by size and SHA-256;
- installed frozen dependency probe: `status=ok`, native audio ABI 1;
- installed physical camera plus strict-native synth smoke: passed;
- same-version repair restored a deliberately removed audio-core DLL;
- exactly one current-user ARP entry existed after install and repair;
- silent uninstall removed the managed standalone and VST3;
- uninstall preserved an unrelated neighboring VST sentinel;
- no QA installation or ARP entry remained after the run.

The final machine-readable acceptance evidence is stored under
`D:\SammyBlazeValidation\phase-9.5`.

## Commands

Build an installer:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-installer.ps1 `
  -StageRoot D:\SammyBlazeRelease\0.4.0-phase9.5-rc1 `
  -ProductVersion 0.4.0-phase9.5-rc1 `
  -InstallerFileVersion 0.4.0.0 `
  -OutputRoot D:\SammyBlazeRelease\Installers\0.4.0-phase9.5-rc1
```

Run the isolated workstation acceptance matrix:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/test-installer.ps1 `
  -InstallerPath D:\SammyBlazeRelease\Installers\0.4.0-phase9.5-rc1\SammyBlaze-Setup-0.4.0-phase9.5-rc1-windows-x64.exe `
  -AllowMachineMutation
```

The harness refuses mutation without the explicit switch and refuses the real
`D:\VST3`, drive roots, Program Files, and Common Files as workstation QA roots.

## Remaining release blockers

- The setup, uninstaller, standalone EXE, native DLL, and VST3 are not signed.
- Inno Setup 6.7.3 reports a non-commercial compiler license on this
  workstation; public commercial use requires the appropriate installer-tool
  license or a deliberate migration.
- No clean Windows 10/11 VM has tested the elevated default Program
  Files/Common Files install without Python, Visual Studio, or prior runtimes.
- Forward upgrade, downgrade rejection, failure rollback, locked-file handling,
  and interrupted installation require versioned installers and VM snapshots.
- FL Studio scan, playback, automation, state recall, and uninstall-rescan
  behavior remain blocked because FL Studio is not installed.
- Publisher identity, support email, EULA/license, dependency notices, privacy
  notice, and release signing policy are unresolved.

These blockers keep the release decision at
`development-pass-release-blocked`.
