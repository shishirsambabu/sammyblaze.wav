# Windows release packaging

The Windows pipeline produces two distinct staged payloads:

- a PyInstaller `standalone/SammyBlaze/` bundle containing
  `SammyBlazeAudioCore.dll`, the MediaPipe hand model, and the Python/Qt runtime;
- a separately installable `VST3/SammyBlaze.vst3` bundle.

`stage-release.ps1` assembles the deterministic input tree, manifest, and checksums.
Phase 9.5 adds an Inno Setup development installer around that verified tree. Public distribution
still requires signing, clean-machine validation, legal metadata, and release approval.

## One-command build and stage

Once the native `SammyBlazeAudioCore` CMake target exists:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-release.ps1 `
  -ProductVersion 0.4.0 `
  -ValidateNative
```

Defaults use the existing D:-drive workstation:

```text
Python:        D:\Python312\python.exe
VST3 SDK:     D:\SammyBlazeDeps\vst3sdk
Build root:   D:\SammyBlazeBuild\native
Audio DLL:    D:\SammyBlazeBuild\native\bin\Release\SammyBlazeAudioCore.dll
VST3 bundle:  D:\SammyBlazeBuild\native\VST3\Release\SammyBlaze.vst3
```

Every tool, build, artifact, output, and staging path can be overridden. For example:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-release.ps1 `
  -ProductVersion 0.4.0 `
  -Python D:\Python312\python.exe `
  -Vst3SdkRoot D:\deps\vst3sdk `
  -NativeBuildDirectory D:\build\sammyblaze-native `
  -AudioCoreDllPath D:\build\sammyblaze-native\bin\Release\SammyBlazeAudioCore.dll `
  -Vst3BundlePath D:\build\sammyblaze-native\VST3\Release\SammyBlaze.vst3 `
  -StandaloneOutputRoot D:\build\sammyblaze-standalone `
  -StageRoot D:\releases\SammyBlaze-0.4.0 `
  -ValidateNative
```

Inspect the resolved native target and path contract without building:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-release.ps1 `
  -ProductVersion 0.4.0 `
  -DryRun
```

Dry-run mode is a plan only because the audio-core target may not yet exist. Real build and
staging runs fail immediately when required tools, the model, DLL, VST3 bundle, or VST3 binary
are missing.

## Individual steps

Build the native audio-core DLL and VST3:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-native.ps1 -Validate
```

If CMake uses a different target or output path:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-native.ps1 `
  -AudioCoreTarget SammyBlazeAudioCore `
  -AudioCoreDllPath D:\custom-build\Release\SammyBlazeAudioCore.dll `
  -Vst3Target SammyBlazeVST3 `
  -Vst3BundlePath D:\custom-build\VST3\Release\SammyBlaze.vst3
```

Build only the standalone bundle from an existing DLL:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1 `
  -Python D:\Python312\python.exe `
  -AudioCoreDllPath D:\SammyBlazeBuild\native\bin\Release\SammyBlazeAudioCore.dll
```

Stage already-built artifacts:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/stage-release.ps1 `
  -ProductVersion 0.4.0 `
  -StandaloneBundlePath artifacts\windows\SammyBlaze `
  -Vst3BundlePath D:\SammyBlazeBuild\native\VST3\Release\SammyBlaze.vst3 `
  -StageRoot D:\SammyBlazeRelease\0.4.0
```

The staging tree is:

```text
SammyBlazeRelease\0.4.0\
├── standalone\
│   └── SammyBlaze\
│       ├── SammyBlaze.exe
│       └── _internal\
│           ├── SammyBlazeAudioCore.dll
│           └── models\hand_landmarker.task
├── VST3\
│   └── SammyBlaze.vst3\
├── manifest.json
└── SHA256SUMS.txt
```

`manifest.json` contains no wall-clock timestamp. Files are sorted and checksummed by relative
path, so staging the same source bytes, version, and Git revision produces identical metadata.
The script validates all source artifacts before replacing an existing stage.

## Build and test the development installer

Install Inno Setup on the build workstation, then run:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-installer.ps1 `
  -StageRoot D:\SammyBlazeRelease\0.4.0-phase9.5-rc1 `
  -ProductVersion 0.4.0-phase9.5-rc1 `
  -InstallerFileVersion 0.4.0.0 `
  -OutputRoot D:\SammyBlazeRelease\Installers\0.4.0-phase9.5-rc1
```

The builder re-verifies every staged payload hash before compilation and records payload and
installer-source revisions separately. Run isolated install/repair/uninstall acceptance with:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/test-installer.ps1 `
  -InstallerPath D:\SammyBlazeRelease\Installers\0.4.0-phase9.5-rc1\SammyBlaze-Setup-0.4.0-phase9.5-rc1-windows-x64.exe `
  -AllowMachineMutation
```

The workstation harness uses unique product-owned QA roots and refuses the real `D:\VST3`,
Program Files, Common Files, and drive roots.

## Current distribution status

An unsigned development installer now exists and its isolated current-user install, payload,
runtime, repair, and uninstall matrix passes. Commercial distribution still requires an
installer-tool commercial license, code-signing certificate, public legal identity, genuine
version-to-version upgrade/rollback tests, clean-machine testing, antivirus reputation checks,
DAW-host acceptance, and release approval.
