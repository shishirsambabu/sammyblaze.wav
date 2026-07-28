# Windows performer bundle

The supported packaging path creates a Windows onedir bundle for the desktop performer UI.
It keeps the hand-landmarker model beside the executable and includes the optional runtime
dependencies required for camera tracking, Qt, and native MIDI.

From the repository root:

```powershell
python packaging/windows/build.ps1
```

With the D: performer environment used for native MIDI:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1 -Python D:\Python312\python.exe
```

The script expects `models/hand_landmarker.task` to exist and writes the bundle to
`artifacts/windows/SammyBlaze/`. Use `-SkipInstall` when the current interpreter already has
the `[package,vision,midi-native,ui]` extras installed.

This is an unsigned development bundle. Production distribution still needs a code-signing
certificate, installer wrapper, and a release artifact review before publishing.

## Native VST3

The native instrument uses Visual Studio Build Tools, Ninja Multi-Config, and the Steinberg VST3
SDK. On the D:-based workstation:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-native.ps1 -Validate
```

The script imports the x64 compiler environment, builds outside the repository at
`D:\SammyBlazeBuild\native`, and optionally runs both the validator self-test and full plug-in
suite. The valid bundle is:

```text
D:\SammyBlazeBuild\native\VST3\Release\SammyBlaze.vst3
```

Copy the complete directory to `C:\Program Files\Common Files\VST3\`, or install it under
`D:\VST3\` and add that folder to FL Studio's plug-in search paths. Rescan, then run
`D:\Python312\python.exe -m handmusic --ui`, choose `FL Studio / VST3 bridge`, and start the
performer. The bridge is loopback-only on UDP port `18736`.
