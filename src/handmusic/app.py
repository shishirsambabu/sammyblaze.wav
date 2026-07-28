from __future__ import annotations

import argparse
import atexit
import signal
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from time import monotonic

from handmusic.calibration import CalibrationSession, PerformerPreset, PresetStore
from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.diagnostics import collect_diagnostics, render_diagnostics
from handmusic.gestures.features import extract_features
from handmusic.gestures.state_machine import GestureConfig, GestureStateMachine
from handmusic.ml.session import record_camera_session
from handmusic.music.chord_engine import ChordSpec
from handmusic.music.expression import ExpressionController
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput
from handmusic.music.note_manager import NoteManager
from handmusic.music.progression import Progression
from handmusic.music.standalone_synth import FluidSynthOutput
from handmusic.telemetry import (
    PerformanceTelemetry,
    TelemetrySnapshot,
    render_telemetry,
    save_telemetry,
)
from handmusic.tracking.camera import frames
from handmusic.tracking.hand_tracker import MediaPipeHandTracker
from handmusic.ui.overlay import draw_landmarks, draw_status


@dataclass(slots=True)
class InstrumentRuntime:
    progression: Progression
    notes: NoteManager
    gestures: GestureStateMachine
    armed: bool = False
    arpeggiator_enabled: bool = False
    last_gesture: str = GestureKind.NO_GESTURE.value
    expression: ExpressionController = field(default_factory=ExpressionController)

    @property
    def chord_label(self) -> str:
        chord = self.progression.current
        return f"{chord.root} {chord.quality}"

    def handle_features(self, features: GestureFeatures) -> int:
        event_count = 0
        for control, value in self.expression.controls(features):
            self.notes.control_change(control, value)
        for event in self.gestures.process(features):
            event_count += 1
            self.last_gesture = event.kind.value
            if event.kind is GestureKind.ARM:
                self.armed = True
                self.notes.play_chord(self.progression.current_notes)
            elif event.kind is GestureKind.STOP_ALL:
                self.armed = False
                self.notes.stop_all()
            elif event.kind is GestureKind.NEXT_CHORD:
                self.progression.next()
                if self.armed:
                    self.notes.play_chord(self.progression.current_notes)
            elif event.kind is GestureKind.PREVIOUS_CHORD:
                self.progression.previous()
                if self.armed:
                    self.notes.play_chord(self.progression.current_notes)
            elif event.kind is GestureKind.TOGGLE_ARPEGGIATOR:
                self.arpeggiator_enabled = not self.arpeggiator_enabled
        return event_count

    def close(self) -> None:
        self.notes.close()

    def stop_for_tracking_loss(self) -> None:
        self.armed = False
        self.notes.stop_all()


def default_runtime(
    output: object | None = None,
    preset: PerformerPreset | None = None,
) -> tuple[InstrumentRuntime, object]:
    output = output or MemoryMidiOutput()
    progression = Progression(
        [
            ChordSpec("C", "major"),
            ChordSpec("A", "minor"),
            ChordSpec("F", "major"),
            ChordSpec("G", "major"),
        ]
    )
    expression = ExpressionController(
        smoothing=preset.expression_smoothing if preset else 0.2,
        neutral_center_x=preset.neutral_center_x if preset else 0.5,
        neutral_center_y=preset.neutral_center_y if preset else 0.5,
        sensitivity=preset.sensitivity if preset else 1.0,
    )
    gesture_config = GestureConfig(confidence=preset.gesture_confidence) if preset else None
    return InstrumentRuntime(
        progression,
        NoteManager(output),
        GestureStateMachine(gesture_config),
        expression=expression,
    ), output


@contextmanager
def _shutdown_guard(runtime: InstrumentRuntime) -> Iterator[None]:
    """Release active notes for normal exits, uncaught exceptions, and Ctrl+C/SIGTERM."""

    cleanup = runtime.close
    atexit.register(cleanup)
    previous_handlers: dict[int, signal.Handlers] = {}

    def handle_signal(signum: int, frame: object) -> None:
        runtime.close()
        raise KeyboardInterrupt(f"received shutdown signal {signum}")

    try:
        for signal_name in ("SIGINT", "SIGTERM"):
            signum = getattr(signal, signal_name, None)
            if signum is not None:
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, handle_signal)
        yield
    finally:
        atexit.unregister(cleanup)
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)


def calibrate_camera(
    output_path: str,
    camera_index: int,
    hand_model: str,
    sample_target: int,
) -> PerformerPreset:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the [vision] extra to calibrate a camera") from exc

    from handmusic.tracking.hand_tracker import TrackerConfig

    tracker = MediaPipeHandTracker(TrackerConfig(model_path=hand_model))
    session = CalibrationSession()
    try:
        for frame, timestamp_ms in frames(camera_index):
            observations = tracker.process(frame, timestamp_ms)
            for observation in observations:
                feature = extract_features(observation)
                if session.add(feature):
                    break
            cv2.putText(
                frame,
                f"Calibration: {session.sample_count}/{sample_target} | Esc cancels",
                (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (50, 220, 50),
                2,
            )
            cv2.imshow("SammyBlaze.wav calibration", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                raise RuntimeError("calibration cancelled")
            if session.sample_count >= sample_target:
                break
    finally:
        tracker.close()
        cv2.destroyAllWindows()
    preset_name = Path(output_path).stem or "performer"
    preset = session.finalize(preset_name, camera_index=camera_index)
    PresetStore.save(output_path, preset)
    print(f"Saved calibration preset to {output_path}")
    return preset


def run_camera(
    runtime: InstrumentRuntime,
    camera_index: int,
    max_frames: int | None = None,
    hand_model: str = "models/hand_landmarker.task",
    telemetry: PerformanceTelemetry | None = None,
    stop_event: Event | None = None,
    telemetry_callback: Callable[[TelemetrySnapshot], None] | None = None,
) -> None:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the [vision] extra to use a camera") from exc

    from handmusic.tracking.hand_tracker import TrackerConfig

    tracker = MediaPipeHandTracker(TrackerConfig(model_path=hand_model))
    previous: dict[str, GestureFeatures] = {}
    frame_times: deque[float] = deque(maxlen=30)
    last_observation_ms: int | None = None
    frame_count = 0
    telemetry = telemetry or PerformanceTelemetry()
    try:
        for frame, timestamp_ms in frames(camera_index):
            if stop_event is not None and stop_event.is_set():
                break
            frame_count += 1
            telemetry.record_frame(timestamp_ms)
            frame_times.append(monotonic())
            observations = tracker.process(frame, timestamp_ms)
            if observations:
                last_observation_ms = timestamp_ms
            elif (
                runtime.armed
                and last_observation_ms is not None
                and timestamp_ms - last_observation_ms >= 500
            ):
                runtime.stop_for_tracking_loss()
            for observation in observations:
                prior = previous.get(observation.handedness)
                feature = extract_features(observation, prior)
                previous[observation.handedness] = feature
                telemetry.record_hand()
                for _ in range(runtime.handle_features(feature)):
                    telemetry.record_gesture(feature.timestamp_ms)
            frame = draw_landmarks(frame, observations)
            elapsed = frame_times[-1] - frame_times[0] if len(frame_times) > 1 else 0.0
            fps = (len(frame_times) - 1) / elapsed if elapsed > 0 else 0.0
            frame = draw_status(
                frame,
                armed=runtime.armed,
                chord=runtime.chord_label,
                gesture=runtime.last_gesture,
                fps=fps,
                hands=len(observations),
            )
            if telemetry_callback is not None:
                telemetry_callback(telemetry.snapshot())
            cv2.imshow("SammyBlaze.wav", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break
            if max_frames is not None and frame_count >= max_frames:
                break
    finally:
        tracker.close()
        cv2.destroyAllWindows()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SammyBlaze.wav hand-controlled instrument")
    parser.add_argument(
        "--dry-run", action="store_true", help="start without camera or external output"
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="print a support-safe environment report without opening hardware",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="launch the desktop performer control surface",
    )
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--output", choices=("midi", "standalone", "null"), default="midi")
    parser.add_argument("--midi-port", default=None, help="MIDI output port name")
    parser.add_argument("--soundfont", default=None, help="SoundFont path for standalone output")
    parser.add_argument(
        "--hand-model",
        default="models/hand_landmarker.task",
        help="MediaPipe hand_landmarker.task path",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="exit after this many frames (useful for a hardware smoke test)",
    )
    parser.add_argument("--preset", default=None, help="load a performer preset JSON")
    parser.add_argument(
        "--calibrate",
        default=None,
        metavar="PATH",
        help="collect camera samples and save a performer preset JSON",
    )
    parser.add_argument(
        "--calibration-samples",
        type=int,
        default=60,
        help="number of confident samples required for calibration",
    )
    parser.add_argument("--record", default=None, help="append a labeled feature session to JSONL")
    parser.add_argument("--label", default=None, help="gesture label for --record")
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=10.0,
        help="recording duration for --record",
    )
    parser.add_argument(
        "--telemetry-json",
        default=None,
        metavar="PATH",
        help="save end-of-session performance telemetry as JSON",
    )
    args = parser.parse_args(argv)
    if args.ui:
        if args.dry_run or args.calibrate or args.record:
            parser.error("--ui cannot be combined with --dry-run, --calibrate, or --record")
        if args.output == "standalone":
            parser.error("--ui currently supports --output midi or --output null")
        from handmusic.ui.desktop import launch_ui

        return launch_ui(args.camera or 0, args.midi_port, args.output)
    if args.diagnostics:
        print(render_diagnostics(collect_diagnostics(args.hand_model)))
        return 0
    preset = PresetStore.load(args.preset) if args.preset else None
    camera_index = (
        args.camera if args.camera is not None else (preset.camera_index if preset else 0)
    )
    if args.calibrate:
        if args.dry_run:
            parser.error("--calibrate cannot be combined with --dry-run")
        if args.calibration_samples <= 0:
            parser.error("--calibration-samples must be positive")
        calibrate_camera(
            args.calibrate,
            camera_index,
            args.hand_model,
            args.calibration_samples,
        )
        return 0
    if args.record:
        if not args.label:
            parser.error("--label is required with --record")
        if args.dry_run:
            parser.error("--record cannot be combined with --dry-run")
        record_camera_session(
            args.record,
            args.label,
            camera_index,
            args.hand_model,
            args.record_seconds,
        )
        return 0
    midi_port = (
        args.midi_port if args.midi_port is not None else (preset.midi_port if preset else None)
    )
    soundfont = (
        args.soundfont if args.soundfont is not None else (preset.soundfont if preset else None)
    )
    if args.dry_run or args.output == "null":
        output = MemoryMidiOutput()
    elif args.output == "midi":
        output = MidoOutput(midi_port)
    else:
        if not soundfont:
            parser.error("--soundfont is required with --output standalone")
        output = FluidSynthOutput(soundfont)
    runtime, output = default_runtime(output, preset)
    telemetry = PerformanceTelemetry()
    try:
        with _shutdown_guard(runtime):
            if args.dry_run:
                print("SammyBlaze.wav dry-run ready: C major -> A minor -> F major -> G major")
                return 0
            run_camera(
                runtime,
                camera_index,
                max_frames=args.max_frames,
                hand_model=args.hand_model,
                telemetry=telemetry,
            )
            return 0
    finally:
        try:
            runtime.close()
        finally:
            if telemetry.frames_seen:
                snapshot = telemetry.snapshot()
                print(render_telemetry(snapshot))
                if args.telemetry_json:
                    save_telemetry(args.telemetry_json, snapshot)
