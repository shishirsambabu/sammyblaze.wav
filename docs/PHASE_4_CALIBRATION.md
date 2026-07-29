# Phase 4 calibration and performer presets

Collect a neutral pose and save it as a versioned JSON preset:

```powershell
python -m handmusic --calibrate presets/my-performance.json --camera 0 --calibration-samples 60
```

Load the preset during performance:

```powershell
python -m handmusic --preset presets/my-performance.json --output null
```

The calibration flow uses confident tracked-hand samples and stores median neutral X/Y/depth values, sensitivity, smoothing, camera index, and optional routing fields. Presets are validated by schema version and written through atomic replacement so an interrupted save does not leave a partially written JSON file.

The preset is intentionally local and performer-specific. Camera frames are not persisted by calibration.
