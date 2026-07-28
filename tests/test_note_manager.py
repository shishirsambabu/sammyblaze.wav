from handmusic.music.midi_output import MemoryMidiOutput
from handmusic.music.note_manager import NoteManager


def test_playing_a_new_chord_releases_the_old_chord() -> None:
    sink = MemoryMidiOutput()
    manager = NoteManager(sink)
    manager.play_chord((60, 64, 67), velocity=100)
    manager.play_chord((57, 60, 64))
    assert manager.active_notes == {57, 60, 64}
    assert sink.messages[:3] == [("note_on", 60, 100), ("note_on", 64, 100), ("note_on", 67, 100)]
    assert ("note_off", 60, None) in sink.messages
    assert ("note_off", 67, None) in sink.messages


def test_stop_all_is_idempotent_and_cleans_everything() -> None:
    sink = MemoryMidiOutput()
    manager = NoteManager(sink)
    manager.play_chord((60, 64))
    manager.stop_all()
    manager.stop_all()
    assert manager.active_notes == set()
    assert sink.messages.count(("note_off", 60, None)) == 1


def test_close_is_idempotent_and_releases_notes_once() -> None:
    sink = MemoryMidiOutput()
    manager = NoteManager(sink)
    manager.play_chord((60, 64))

    manager.close()
    manager.close()

    assert manager.active_notes == set()
    assert sink.messages.count(("note_off", 60, None)) == 1


def test_melody_changes_are_legato_and_can_retrigger_same_note() -> None:
    sink = MemoryMidiOutput()
    manager = NoteManager(sink)

    manager.play_melody_note(72, velocity=90)
    manager.play_melody_note(74, velocity=100)
    manager.play_melody_note(74, velocity=110, retrigger=True)

    assert sink.messages == [
        ("note_on", 72, 90),
        ("note_on", 74, 100),
        ("note_off", 72, None),
        ("note_off", 74, None),
        ("note_on", 74, 110),
    ]


def test_melody_can_rearticulate_a_note_shared_with_latched_chord() -> None:
    sink = MemoryMidiOutput()
    manager = NoteManager(sink)

    manager.play_chord((60, 64, 67))
    manager.play_melody_note(60, velocity=105)
    manager.play_melody_note(60, velocity=118, retrigger=True)

    assert sink.messages.count(("note_on", 60, 96)) == 1
    assert sink.messages[-1] == ("note_on", 60, 118)
    assert manager.active_notes == {60, 64, 67}
