import numpy as np

from handmusic.music.builtin_synth import SynthEngine


def test_builtin_synth_renders_finite_stereo_audio() -> None:
    synth = SynthEngine(sample_rate=48_000, program=0)
    synth.note_on(60, 100)

    audio = synth.render(4096)

    assert audio.shape == (4096, 2)
    assert audio.dtype == np.float32
    assert np.isfinite(audio).all()
    assert float(np.max(np.abs(audio))) > 0.001
    assert float(np.max(np.abs(audio))) <= 1.0


def test_factory_programs_produce_different_audio_signatures() -> None:
    keys = SynthEngine(sample_rate=48_000, program=0)
    bass = SynthEngine(sample_rate=48_000, program=12)
    keys.note_on(48, 110)
    bass.note_on(48, 110)

    keys_audio = keys.render(2048)
    bass_audio = bass.render(2048)

    assert not np.allclose(keys_audio, bass_audio)


def test_sustain_holds_then_releases_a_voice() -> None:
    synth = SynthEngine(sample_rate=1000, program=36)
    synth.note_on(60, 100)
    synth.render(100)
    synth.control_change(64, 127)
    synth.note_off(60)
    synth.render(1500)

    assert synth.voices

    synth.control_change(64, 0)
    synth.render(2000)
    assert not synth.voices


def test_program_change_loads_factory_effect_settings_and_panics() -> None:
    synth = SynthEngine(program=0)
    synth.note_on(60, 100)

    synth.program_change(84)

    assert synth.preset.name == "Distant Rainlight"
    assert synth.reverb_mix == synth.preset.reverb_mix
    assert synth.delay_mix == synth.preset.delay_mix
    assert not synth.voices
