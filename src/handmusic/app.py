from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
from time import monotonic

from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.gestures.features import extract_features
from handmusic.gestures.state_machine import GestureStateMachine
from handmusic.music.chord_engine import ChordSpec
from handmusic.music.expression import ExpressionController
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput
from handmusic.music.note_manager import NoteManager
from handmusic.music.progression import Progression
from handmusic.music.standalone_synth import FluidSynthOutput
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

    def handle_features(self, features: GestureFeatures) -> None:
        for control, value in self.expression.controls(features):
            self.notes.control_change(control, value)
        for event in self.gestures.process(features):
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

    def close(self) -> None:
        self.notes.close()

    def stop_for_tracking_loss(self) -> None:
        self.armed = False
        self.notes.stop_all()


def default_runtime(output: object | None = None) -> tuple[InstrumentRuntime, object]:
    output = output or MemoryMidiOutput()
    progression = Progression(
        [
            ChordSpec("C", "major"),
            ChordSpec("A", "minor"),
            ChordSpec("F", "major"),
            ChordSpec("G", "major"),
        ]
    )
    return InstrumentRuntime(progression, NoteManager(output), GestureStateMachine()), output


def run_camera(
    runtime: InstrumentRuntime,
    camera_index: int,
    max_frames: int | None = None,
    hand_model: str = "models/hand_landmarker.task",
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
    try:
        for frame, timestamp_ms in frames(camera_index):
            frame_count += 1
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
                runtime.handle_features(feature)
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
    parser.add_argument("--camera", type=int, default=0)
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
    args = parser.parse_args(argv)
    if args.dry_run or args.output == "null":
        output = MemoryMidiOutput()
    elif args.output == "midi":
        output = MidoOutput(args.midi_port)
    else:
        if not args.soundfont:
            parser.error("--soundfont is required with --output standalone")
        output = FluidSynthOutput(args.soundfont)
    runtime, output = default_runtime(output)
    try:
        if args.dry_run:
            print("SammyBlaze.wav dry-run ready: C major -> A minor -> F major -> G major")
            return 0
        run_camera(
            runtime,
            args.camera,
            max_frames=args.max_frames,
            hand_model=args.hand_model,
        )
        return 0
    finally:
        runtime.close()
