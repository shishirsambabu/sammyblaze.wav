from __future__ import annotations

import argparse
from dataclasses import dataclass

from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.gestures.features import extract_features
from handmusic.gestures.state_machine import GestureStateMachine
from handmusic.music.chord_engine import ChordSpec
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput
from handmusic.music.note_manager import NoteManager
from handmusic.music.progression import Progression
from handmusic.music.standalone_synth import FluidSynthOutput
from handmusic.tracking.camera import frames
from handmusic.tracking.hand_tracker import MediaPipeHandTracker
from handmusic.ui.overlay import draw_status


@dataclass(slots=True)
class InstrumentRuntime:
    progression: Progression
    notes: NoteManager
    gestures: GestureStateMachine
    armed: bool = False
    arpeggiator_enabled: bool = False
    last_gesture: str = GestureKind.NO_GESTURE.value

    def handle_features(self, features: GestureFeatures) -> None:
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


def run_camera(runtime: InstrumentRuntime, camera_index: int) -> None:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the [vision] extra to use a camera") from exc

    tracker = MediaPipeHandTracker()
    previous: dict[str, GestureFeatures] = {}
    try:
        for frame, timestamp_ms in frames(camera_index):
            observations = tracker.process(frame, timestamp_ms)
            for observation in observations:
                prior = previous.get(observation.handedness)
                feature = extract_features(observation, prior)
                previous[observation.handedness] = feature
                runtime.handle_features(feature)
            frame = draw_status(frame, armed=runtime.armed, gesture=runtime.last_gesture, fps=0.0)
            cv2.imshow("SammyBlaze.wav", frame)
            if cv2.waitKey(1) & 0xFF == 27:
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
    parser.add_argument("--output", choices=("midi", "standalone"), default="midi")
    parser.add_argument("--midi-port", default=None, help="MIDI output port name")
    parser.add_argument("--soundfont", default=None, help="SoundFont path for standalone output")
    args = parser.parse_args(argv)
    if args.dry_run:
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
        run_camera(runtime, args.camera)
        return 0
    finally:
        runtime.close()
