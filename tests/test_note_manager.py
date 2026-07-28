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
