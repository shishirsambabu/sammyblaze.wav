# Phase 9.3: Windows standalone footprint

## Goal and baseline

The Phase 9.2 PyInstaller `onedir` bundle measured **1,047,945,803 bytes**
across **4,326 files** before release staging metadata. Its largest component
was a broad `--collect-all PySide6` payload: 664,544,584 bytes and 3,704 files.
Broad MediaPipe collection also included test and unrelated task code, pulling
in SciPy, Matplotlib, Pillow, and their native dependencies.

Phase 9.3 keeps the same runtime contract while replacing broad collection with
module-aware PyInstaller hooks:

- PySide6's built-in `QtCore`, `QtGui`, and `QtWidgets` hooks select the required
  Qt libraries and Windows platform plug-ins from actual imports.
- A project hook adds only MediaPipe's `tasks/c/libmediapipe.dll`; MediaPipe
  Python modules remain discoverable through ordinary import analysis.
- The app does not use MediaPipe's plotting helpers, so a runtime import stub
  preserves the public `mediapipe.tasks.vision` import while excluding
  Matplotlib and `mpl_toolkits`.
- SciPy, Pillow, notebook, test, TensorFlow, Torch, and JAX stacks are explicitly
  excluded. They are absent from SammyBlaze's performer runtime and are
  introduced only by broad collection or optional MediaPipe tooling.

OpenCV's core extension and video I/O DLLs are retained. SoundDevice's PortAudio
binary, python-rtmidi, the hand model, and `SammyBlazeAudioCore.dll` are also
hard post-build requirements.

## Release gates

`verify_bundle.py` fails the build unless all required binary/data paths and
frozen Python modules are present. It also rejects excluded module stacks,
requires the bundle to be no larger than **450,000,000 bytes** and **1,500
files**, and reports exact bytes and file count.

The opt-in packaged runtime probe performs these checks inside the frozen
process:

1. import PySide6 Widgets, OpenCV, MediaPipe, SoundDevice, mido-rtmidi, and
   python-rtmidi;
2. load PortAudio by querying devices;
3. create and close a MediaPipe Tasks `HandLandmarker` with the bundled model;
4. load the bundled native audio DLL, validate ABI v1, and create/destroy an
   engine instance.

The release smoke keeps the offscreen UI process alive for ten seconds after
the probe passes, then terminates that exact process.

## Isolated build command

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1 `
  -Python D:\Python312\python.exe `
  -OutputRoot D:\SammyBlazeBuild\phase-9.3-package `
  -AudioCoreDllPath D:\SammyBlazeBuild\native\bin\Release\SammyBlazeAudioCore.dll `
  -SkipInstall `
  -SmokeTest `
  -SmokeSeconds 10
```

This path is intentionally separate from the Phase 9.2 release and staging
directories. It does not overwrite the prior standalone, VST3, or manifest.
