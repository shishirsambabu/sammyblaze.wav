from __future__ import annotations


class FluidSynthOutput:
    """Optional SoundFont adapter; it shares the NoteSink contract with MIDI."""

    def __init__(self, soundfont_path: str, program: int = 0) -> None:
        try:
            import fluidsynth
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "Install the [audio] extra and FluidSynth to use standalone audio"
            ) from exc
        self._synth = fluidsynth.Synth()
        self._synth.start()
        self._synth.sfload(soundfont_path)
        self._synth.program_select(0, 0, 0, program)

    def note_on(self, note: int, velocity: int) -> None:
        self._synth.noteon(0, note, velocity)

    def note_off(self, note: int) -> None:
        self._synth.noteoff(0, note)

    def control_change(self, control: int, value: int) -> None:
        self._synth.cc(0, control, value)

    def close(self) -> None:
        self._synth.delete()
