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
from handmusic.music.builtin_synth import BuiltinSynthOutput
from handmusic.music.chord_engine import ChordSpec, chord_notes
from handmusic.music.expression import ExpressionController, ExpressionState
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput, PluginBridgeOutput
from handmusic.music.modes import PerformanceMode
from handmusic.music.note_manager import NoteManager
from handmusic.music.performance import (
    HarmonicScaleEngine,
    MelodyPerformanceEngine,
    VoiceLeadingEngine,
    lead_mode_for_scale_name,
    midi_note_name,
)
from handmusic.music.presets import get_preset
from handmusic.music.progression import (
    Progression,
    pose_chords_for,
    progression_for,
    progression_names,
)
from handmusic.music.scale import scale_names
from handmusic.music.standalone_synth import FluidSynthOutput
from handmusic.music.transport import LoopTransport, TransportSnapshot
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
    scale: HarmonicScaleEngine = field(
        default_factory=lambda: HarmonicScaleEngine(ChordSpec("C", "major7"))
    )
    chord_bank: tuple[ChordSpec, ...] = field(default_factory=lambda: pose_chords_for("pop"))
    transport: LoopTransport | None = None
    voice_leading: VoiceLeadingEngine = field(default_factory=VoiceLeadingEngine)
    melody: MelodyPerformanceEngine = field(init=False)
    mode: PerformanceMode = PerformanceMode.CHORD_SCALE
    active_chord: ChordSpec | None = None
    last_scale_note: int | None = None
    last_chord_notes: tuple[int, ...] = ()
    tracking_loss_grace_ms: int = 1500
    right_hand_loss_grace_ms: int = 250
    expression_state: ExpressionState = field(default_factory=ExpressionState)
    sound_program: int = 0
    _last_cc: dict[int, tuple[int, int]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.active_chord = self.active_chord or self.progression.current
        self.scale.set_chord(self.active_chord)
        self.melody = MelodyPerformanceEngine(self.scale)

    @property
    def chord_label(self) -> str:
        chord = self.active_chord or self.progression.current
        return f"{chord.root} {chord.quality}"

    @property
    def status_label(self) -> str:
        armed = "ARMED" if self.armed else "DISARMED"
        pedal = "on" if self.notes.sustain_enabled else "off"
        latch = "active" if self.last_chord_notes else "ready"
        chord_notes = " ".join(midi_note_name(note) for note in self.last_chord_notes) or "—"
        melody_note = (
            midi_note_name(self.last_scale_note) if self.last_scale_note is not None else "—"
        )
        return (
            f"{armed} | Mode: {self.mode.value} | Chord latch: {latch} | Pedal: {pedal} | "
            f"Chord: {chord_notes} | Melody: {melody_note} | "
            f"Lead: {self.scale.label} ({self.scale.mode.value}) | "
            f"Sound: {get_preset(self.sound_program).name}"
        )

    def handle_features(self, features: GestureFeatures) -> int:
        event_count = 0
        if features.handedness == "right":
            expression = self.expression.process(features)
            self.expression_state = expression.state
            self._send_expression_controls(expression.controls, features.timestamp_ms)
            self._handle_scale_position(features)
            return 0
        if features.handedness != "left":
            return 0
        for event in self.gestures.process(features):
            event_count += 1
            self.last_gesture = event.kind.value
            if event.kind is GestureKind.ARM:
                self.armed = True
                if self.mode.accepts_chords:
                    self._play_current_chord()
            elif event.kind is GestureKind.SELECT_CHORD:
                chord_index = int(event.value or 0) % len(self.chord_bank)
                self.active_chord = self.chord_bank[chord_index]
                self.armed = True
                if self.mode.accepts_chords:
                    self._play_current_chord()
            elif event.kind is GestureKind.STOP_ALL:
                self.armed = False
                self.notes.stop_all()
                self.last_scale_note = None
                self.last_chord_notes = ()
                self.melody.reset()
                self.voice_leading.reset()
            elif event.kind is GestureKind.NEXT_CHORD:
                self.active_chord = self.progression.next()
                if self.armed and self.mode.accepts_chords:
                    self._play_current_chord()
            elif event.kind is GestureKind.PREVIOUS_CHORD:
                self.active_chord = self.progression.previous()
                if self.armed and self.mode.accepts_chords:
                    self._play_current_chord()
            elif event.kind is GestureKind.TOGGLE_ARPEGGIATOR:
                self.arpeggiator_enabled = not self.arpeggiator_enabled
            elif event.kind is GestureKind.CYCLE_MODE:
                self._cycle_mode()
            elif event.kind is GestureKind.CYCLE_SCALE_MODE:
                self._cycle_scale_mode()
            elif event.kind is GestureKind.TOGGLE_SUSTAIN:
                self.notes.set_sustain(not self.notes.sustain_enabled)
        return event_count

    def _handle_scale_position(self, features: GestureFeatures) -> None:
        if not self.armed or not self.mode.accepts_scale:
            if self.last_scale_note is not None:
                self.notes.stop_melody_note()
                self.last_scale_note = None
                self.melody.reset()
            return
        decision = self.melody.perform(features)
        self.notes.play_melody_note(
            decision.note,
            decision.velocity,
            legato=True,
            retrigger=decision.retrigger,
        )
        self.last_scale_note = decision.note

    def _play_current_chord(self) -> None:
        chord = self.active_chord or self.progression.current
        self.scale.set_chord(chord)
        voiced = self.voice_leading.voice(chord_notes(chord))
        self.notes.play_chord(voiced, velocity=92)
        self.last_chord_notes = voiced
        retuned = self.melody.retuned_note()
        if (
            retuned is not None
            and self.last_scale_note is not None
            and self.mode.accepts_scale
        ):
            self.notes.play_melody_note(retuned, velocity=84, legato=True)
            self.last_scale_note = retuned

    def _cycle_scale_mode(self) -> None:
        self.scale.cycle_mode()
        retuned = self.melody.retuned_note()
        if retuned is not None and self.last_scale_note is not None and self.mode.accepts_scale:
            self.notes.play_melody_note(retuned, velocity=84, legato=True)
            self.last_scale_note = retuned

    def _cycle_mode(self) -> None:
        self.mode = self.mode.next()
        if not self.mode.accepts_chords:
            self.notes.stop_chord()
            self.last_chord_notes = ()
        elif self.armed:
            self._play_current_chord()
        if not self.mode.accepts_scale:
            self.notes.stop_melody_note()
            self.last_scale_note = None
            self.melody.reset()

    def close(self) -> None:
        self.notes.close()

    def toggle_recording(self, timestamp_ms: int | None = None) -> TransportSnapshot:
        if self.transport is None:
            return TransportSnapshot(False, False, 0, 0)
        if self.transport.snapshot().recording:
            if self.transport.stop_recording(timestamp_ms):
                self.transport.start_playback(timestamp_ms)
        else:
            self.transport.start_recording(timestamp_ms)
        return self.transport.snapshot()

    def toggle_playback(self, timestamp_ms: int | None = None) -> TransportSnapshot:
        if self.transport is None:
            return TransportSnapshot(False, False, 0, 0)
        if self.transport.snapshot().playing:
            self.transport.stop_playback()
        else:
            self.transport.start_playback(timestamp_ms)
        return self.transport.snapshot()

    def clear_loop(self) -> TransportSnapshot:
        if self.transport is None:
            return TransportSnapshot(False, False, 0, 0)
        self.transport.clear()
        return self.transport.snapshot()

    def select_sound(self, program: int) -> None:
        get_preset(program)
        self.sound_program = program
        self.notes.program_change(program)

    def release_melody_for_tracking_loss(self) -> None:
        self.notes.stop_melody_note()
        self.last_scale_note = None
        self.melody.reset()

    def stop_for_tracking_loss(self) -> None:
        self.armed = False
        self.notes.stop_all()
        self.last_scale_note = None
        self.last_chord_notes = ()
        self.melody.reset()
        self.voice_leading.reset()

    def _send_expression_controls(
        self,
        controls: tuple[tuple[int, int], ...],
        timestamp_ms: int,
    ) -> None:
        for control, value in controls:
            previous = self._last_cc.get(control)
            if (
                previous is None
                or abs(value - previous[0]) >= 2
                or timestamp_ms - previous[1] >= 50
            ):
                self.notes.control_change(control, value)
                self._last_cc[control] = (value, timestamp_ms)


def default_runtime(
    output: object | None = None,
    preset: PerformerPreset | None = None,
    progression_name: str = "pop",
    scale_name: str = "major",
) -> tuple[InstrumentRuntime, object]:
    output = output or MemoryMidiOutput()
    progression = progression_for(progression_name)
    transport = LoopTransport(output)
    expression = ExpressionController(
        smoothing=preset.expression_smoothing if preset else 0.2,
        neutral_center_x=preset.neutral_center_x if preset else 0.5,
        neutral_center_y=preset.neutral_center_y if preset else 0.5,
        neutral_depth=preset.neutral_depth if preset else 0.0,
        sensitivity=preset.sensitivity if preset else 1.0,
    )
    gesture_config = GestureConfig(confidence=preset.gesture_confidence) if preset else None
    return InstrumentRuntime(
        progression,
        NoteManager(transport),
        GestureStateMachine(gesture_config),
        expression=expression,
        scale=HarmonicScaleEngine(
            progression.current,
            mode=lead_mode_for_scale_name(scale_name),
        ),
        chord_bank=pose_chords_for(progression_name),
        transport=transport,
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
    frame_callback: Callable[[object], None] | None = None,
    state_callback: Callable[[str], None] | None = None,
    expression_callback: Callable[[ExpressionState], None] | None = None,
    transport_callback: Callable[[TransportSnapshot], None] | None = None,
    display: bool = True,
) -> None:
    if stop_event is not None and stop_event.is_set():
        return

    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the [vision] extra to use a camera") from exc

    from handmusic.tracking.hand_tracker import TrackerConfig

    tracker = MediaPipeHandTracker(TrackerConfig(model_path=hand_model))
    previous: dict[str, GestureFeatures] = {}
    frame_times: deque[float] = deque(maxlen=30)
    last_observation_ms: int | None = None
    last_hand_seen_ms: dict[str, int] = {}
    frame_count = 0
    last_state_label: str | None = None
    telemetry = telemetry or PerformanceTelemetry()
    try:
        if stop_event is not None and stop_event.is_set():
            return
        for frame, timestamp_ms in frames(camera_index, stop_event=stop_event):
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
                and timestamp_ms - last_observation_ms >= runtime.tracking_loss_grace_ms
            ):
                runtime.stop_for_tracking_loss()
            for observation in observations:
                last_hand_seen_ms[observation.handedness] = timestamp_ms
                prior = previous.get(observation.handedness)
                feature = extract_features(observation, prior)
                previous[observation.handedness] = feature
                telemetry.record_hand()
                for _ in range(runtime.handle_features(feature)):
                    telemetry.record_gesture(feature.timestamp_ms)
            right_seen = last_hand_seen_ms.get("right")
            if (
                runtime.last_scale_note is not None
                and right_seen is not None
                and timestamp_ms - right_seen >= runtime.right_hand_loss_grace_ms
            ):
                runtime.release_melody_for_tracking_loss()
                last_hand_seen_ms.pop("right", None)
            if runtime.transport is not None:
                runtime.transport.tick(timestamp_ms)
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
                mode=runtime.mode.value,
                sustain=runtime.notes.sustain_enabled,
                chord_notes=runtime.last_chord_notes,
                melody_note=runtime.last_scale_note,
            )
            if state_callback is not None and runtime.status_label != last_state_label:
                last_state_label = runtime.status_label
                state_callback(last_state_label)
            if expression_callback is not None:
                expression_callback(runtime.expression_state)
            if transport_callback is not None and runtime.transport is not None:
                transport_callback(runtime.transport.snapshot())
            if telemetry_callback is not None:
                telemetry_callback(telemetry.snapshot())
            if frame_callback is not None:
                frame_callback(frame)
            if display:
                cv2.imshow("SammyBlaze.wav", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
            if max_frames is not None and frame_count >= max_frames:
                break
    finally:
        tracker.close()
        if display:
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
    parser.add_argument(
        "--output",
        choices=("synth", "midi", "plugin", "standalone", "null"),
        default="synth",
    )
    parser.add_argument("--midi-port", default=None, help="MIDI output port name")
    parser.add_argument(
        "--progression",
        choices=progression_names(),
        default="pop",
        help="named chord progression",
    )
    parser.add_argument(
        "--scale",
        choices=scale_names(),
        default="major",
        help="right-hand scale mapping",
    )
    parser.add_argument(
        "--sound-program",
        type=int,
        choices=range(120),
        default=0,
        metavar="0-119",
        help="factory sound program (0-119)",
    )
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
            parser.error("--ui supports --output synth, midi, plugin, or null")
        from handmusic.ui.desktop import launch_ui

        return launch_ui(
            args.camera or 0,
            args.midi_port,
            args.output,
            args.progression,
            args.scale,
            args.sound_program,
        )
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
    elif args.output == "synth":
        output = BuiltinSynthOutput(args.sound_program)
    elif args.output == "midi":
        output = MidoOutput(midi_port)
    elif args.output == "plugin":
        output = PluginBridgeOutput()
    else:
        if not soundfont:
            parser.error("--soundfont is required with --output standalone")
        output = FluidSynthOutput(soundfont)
    runtime, output = default_runtime(output, preset, args.progression, args.scale)
    runtime.select_sound(args.sound_program)
    telemetry = PerformanceTelemetry()
    try:
        with _shutdown_guard(runtime):
            if args.dry_run:
                print(
                    "SammyBlaze.wav dry-run ready: "
                    f"{args.progression} progression, {args.scale} scale"
                )
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
