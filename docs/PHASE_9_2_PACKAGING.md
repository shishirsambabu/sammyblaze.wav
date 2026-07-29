# Phase 9.2: Windows native release staging

## Packaging contract

Phase 9.2 separates the product into two installer payloads:

1. `standalone/SammyBlaze/` is the complete PyInstaller onedir application. The
   `SammyBlazeAudioCore.dll` shared native renderer is bundled into PyInstaller's `_internal`
   runtime directory with `hand_landmarker.task`.
2. `VST3/SammyBlaze.vst3` remains a complete VST3 directory bundle. It is staged beside the
   standalone application and is never embedded inside it.

The future installer may therefore install the standalone under `Program Files` and the VST3
under the system VST3 directory without unpacking or inferring either payload.

## Native target handoff

The source branch did not expose an audio-core CMake target when this packaging slice started.
Packaging defines the expected contract explicitly:

```text
CMake target:  SammyBlazeAudioCore
DLL output:    <native-build>\bin\<Configuration>\SammyBlazeAudioCore.dll
VST3 target:   SammyBlazeVST3
VST3 output:   <native-build>\VST3\<Configuration>\SammyBlaze.vst3
```

`build-native.ps1` accepts `-AudioCoreTarget`, `-AudioCoreDllPath`, `-Vst3Target`, and
`-Vst3BundlePath` overrides. The native implementation can either honor the expected default
layout or provide its actual target and path to the release pipeline without another packaging
change.

## Release gates

A Phase 9.2 staging run fails when any of these are absent:

- Visual Studio compiler environment, CMake, Ninja, or VST3 SDK;
- the configured audio-core CMake target or resulting DLL;
- the configured VST3 target, bundle, or x86-64 Windows plug-in binary;
- `models/hand_landmarker.task`;
- `SammyBlaze.exe`, the bundled audio-core DLL, or bundled model.

Validation occurs before an existing stage is replaced. Staging uses a temporary sibling folder,
generates metadata, and then promotes the completed tree.

## Deterministic metadata

`manifest.json` records the version, platform, configuration, source Git revision, sorted
relative paths, byte sizes, and SHA-256 hashes. It intentionally excludes build time, staging
location, and absolute workstation paths.

`SHA256SUMS.txt` covers every payload file plus `manifest.json`. It does not checksum itself.
Given identical source bytes, version, and source revision, both metadata files are
byte-for-byte reproducible.

## Commands

Inspect the pipeline without invoking CMake or PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-release.ps1 `
  -ProductVersion 0.4.0 `
  -DryRun
```

Build, validate, package, and stage after the native target lands:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-release.ps1 `
  -ProductVersion 0.4.0 `
  -ValidateNative
```

No `.exe` installer is produced in this phase.
