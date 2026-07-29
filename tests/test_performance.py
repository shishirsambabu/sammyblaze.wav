from handmusic.common.models import GestureFeatures
from handmusic.music.chord_engine import ChordSpec
from handmusic.music.performance import (
    HarmonicScaleEngine,
    LeadScaleMode,
    MelodyPerformanceEngine,
    VoiceLeadingEngine,
    midi_note_name,
)
from handmusic.music.progression import progression_for
from handmusic.music.scale import ScaleEngine, scale_for


def right_hand(
    *,
    x: float,
    y: float = 0.5,
    pinch: float = 1.0,
    velocity_y: float = 0.0,
) -> GestureFeatures:
    return GestureFeatures(
        "right",
        (False,) * 5,
        pinch,
        0.0,
        x,
        y,
        0.0,
        0.0,
        velocity_y,
        1.0,
        0,
    )


def test_voice_leading_keeps_pop_progression_compact_in_left_hand_register() -> None:
    progression = progression_for("pop")
    engine = VoiceLeadingEngine()
    voiced = [engine.voice(progression.current_notes)]
    for _ in range(3):
        progression.next()
        voiced.append(engine.voice(progression.current_notes))

    assert voiced == [
        (48, 52, 55),
        (48, 52, 57),
        (48, 53, 57),
        (50, 55, 59),
    ]
    assert all(43 <= note <= 67 for chord in voiced for note in chord)


def test_melody_hysteresis_prevents_pitch_jitter_at_scale_boundaries() -> None:
    engine = MelodyPerformanceEngine(ScaleEngine(scale_for("major"), octaves=1))

    assert engine.perform(right_hand(x=0.30)).note == 64
    assert engine.perform(right_hand(x=0.37)).note == 64
    assert engine.perform(right_hand(x=0.40)).note == 65


def test_right_hand_pinch_rearticulates_current_note_once() -> None:
    engine = MelodyPerformanceEngine(ScaleEngine(scale_for("major"), octaves=1))

    assert engine.perform(right_hand(x=0.5, pinch=1.0)).retrigger is False
    assert engine.perform(right_hand(x=0.5, pinch=0.2)).retrigger is True
    assert engine.perform(right_hand(x=0.5, pinch=0.2)).retrigger is False
    assert engine.perform(right_hand(x=0.5, pinch=1.0)).retrigger is False
    assert engine.perform(right_hand(x=0.5, pinch=0.2)).retrigger is True


def test_downward_strike_adds_velocity_without_exceeding_midi_range() -> None:
    engine = MelodyPerformanceEngine(ScaleEngine(scale_for("major"), octaves=1))

    gentle = engine.perform(right_hand(x=0.5, y=0.5, velocity_y=0.0))
    accented = engine.perform(right_hand(x=0.5, y=0.5, velocity_y=3.0))

    assert gentle.velocity == 77
    assert accented.velocity == 102


def test_midi_note_names_match_keyboard_octaves() -> None:
    assert midi_note_name(48) == "C3"
    assert midi_note_name(60) == "C4"
    assert midi_note_name(73) == "C#5"


def test_harmonic_scale_follows_chord_root_and_quality() -> None:
    engine = HarmonicScaleEngine(ChordSpec("C", "major7"))
    assert engine.label == "C Ionian"
    assert engine.notes[:4] == (60, 62, 64, 65)

    engine.set_chord(ChordSpec("A", "minor7"))
    assert engine.label == "A Aeolian"
    assert engine.notes[:4] == (69, 71, 72, 74)


def test_scale_mode_cycle_selects_quality_aware_color() -> None:
    engine = HarmonicScaleEngine(ChordSpec("G", "dominant7"))

    assert engine.cycle_mode() is LeadScaleMode.COLOR
    assert engine.label == "G Altered"
    assert {67, 71, 74, 77}.issubset(set(engine.notes))
