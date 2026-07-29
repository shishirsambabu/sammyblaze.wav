# Windows release packaging

The Phase 9.2 Windows pipeline produces two distinct deliverables:

- a PyInstaller `standalone/SammyBlaze/` bundle containing
  `SammyBlazeAudioCore.dll`, the MediaPipe hand model, and the Python/Qt runtime;
- a separately installable `VST3/SammyBlaze.vst3` bundle.

It does **not** create the final installer. `stage-release.ps1` assembles the deterministic input
tree, manifest, and checksums that a future signed installer will consume.

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

## Current distribution status

These remain unsigned development artifacts. Commercial distribution still requires an
installer authoring tool, code-signing certificate, upgrade/uninstall rules, clean-machine
testing, antivirus reputation checks, and release approval.
