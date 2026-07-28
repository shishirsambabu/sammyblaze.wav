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
