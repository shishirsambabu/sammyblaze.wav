from __future__ import annotations

from pathlib import Path


class FluidSynthOutput:
    """Optional SoundFont adapter; it shares the NoteSink contract with MIDI."""

    def __init__(self, soundfont_path: str, program: int = 0) -> None:
        if not Path(soundfont_path).is_file():
            raise FileNotFoundError(f"SoundFont not found: {soundfont_path}")
        try:
            import fluidsynth
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "Install the [audio] extra and FluidSynth to use standalone audio"
            ) from exc
        try:
            self._synth = fluidsynth.Synth()
            self._synth.start()
            self._synth.sfload(soundfont_path)
            self._synth.program_select(0, 0, 0, program)
        except OSError as exc:  # pragma: no cover - depends on native library
            raise RuntimeError(
                "FluidSynth native library unavailable. Install FluidSynth for your OS."
            ) from exc
        self._closed = False

    def note_on(self, note: int, velocity: int) -> None:
        self._synth.noteon(0, note, velocity)

    def note_off(self, note: int) -> None:
        self._synth.noteoff(0, note)

    def control_change(self, control: int, value: int) -> None:
        self._synth.cc(0, control, value)

    def program_change(self, program: int) -> None:
        from handmusic.music.presets import get_preset

        self._synth.program_change(0, get_preset(program).midi_program)

    def close(self) -> None:
        if not self._closed:
            self._synth.delete()
            self._closed = True
