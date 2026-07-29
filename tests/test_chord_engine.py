import pytest

from handmusic.music.chord_engine import ChordSpec, chord_notes


def test_major_root_position_is_c4_e4_g4() -> None:
    assert chord_notes(ChordSpec("C", "major")) == (60, 64, 67)


def test_inversions_rotate_low_note_up_an_octave() -> None:
    assert chord_notes(ChordSpec("C", "major", inversion=1)) == (64, 67, 72)
    assert chord_notes(ChordSpec("C", "major", inversion=2)) == (67, 72, 76)


def test_seventh_and_open_voicing_are_supported() -> None:
    assert chord_notes(ChordSpec("G", "dominant7")) == (67, 71, 74, 77)
    assert chord_notes(ChordSpec("C", "major", open_voicing=True)) == (60, 67, 76)


@pytest.mark.parametrize(
    "spec",
    [
        ChordSpec("H"),
        ChordSpec("C", "unknown"),
        ChordSpec("C", inversion=3),
    ],
)
def test_invalid_specs_fail_clearly(spec: ChordSpec) -> None:
    with pytest.raises(ValueError):
        chord_notes(spec)
