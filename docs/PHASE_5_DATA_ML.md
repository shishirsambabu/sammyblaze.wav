# Phase 5 data collection and gesture ML

Record labeled landmark features without persisting camera frames:

```powershell
python -m handmusic --record data/recordings/swipe_right.jsonl --label swipe_right --record-seconds 10 --camera 0
python -m handmusic --record data/recordings/no_gesture.jsonl --label no_gesture --record-seconds 10 --camera 0
```

The JSONL schema stores session ID, timestamp, handedness, normalized feature values, label, and minimal metadata. `no_gesture` is a required negative class. Keep sessions consented and do not commit recordings to Git.

Use `split_by_session` from `handmusic.ml.recording` for train/validation/test splits. Never split adjacent frames randomly: that leaks nearly identical movement into every dataset partition.

The optional baseline is intentionally not wired into the live runtime:

```powershell
python -m pip install -e ".[ml]"
```

Benchmark any classifier against the deterministic rule engine before considering it for production. Store model artifacts under `models/` and add a model/data card before shipping.
