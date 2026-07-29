from handmusic.music.midi_output import MemoryMidiOutput
from handmusic.music.transport import LoopEvent, LoopTransport


def test_transport_records_and_replays_a_bounded_loop() -> None:
    now = [1000]
    sink = MemoryMidiOutput()
    transport = LoopTransport(sink, clock_ms=lambda: now[0])

    transport.start_recording()
    transport.note_on(60, 100)
    now[0] = 1250
    transport.note_off(60)
    now[0] = 1500
    assert transport.stop_recording() is True
    assert transport.events == (
        LoopEvent(0, "note_on", 60, 100),
        LoopEvent(250, "note_off", 60, 0),
    )

    assert transport.start_playback(2000) is True
    assert transport.tick(2000) == 1
    assert transport.tick(2250) == 1
    assert transport.tick(2500) == 1
    assert sink.messages[-3:] == [
        ("note_on", 60, 100),
        ("note_off", 60, None),
        ("note_on", 60, 100),
    ]


def test_recording_captures_a_chord_already_held_at_record_start() -> None:
    now = [0]
    sink = MemoryMidiOutput()
    transport = LoopTransport(sink, clock_ms=lambda: now[0])

    transport.note_on(48, 92)
    transport.start_recording()
    now[0] = 800
    assert transport.stop_recording() is True

    assert transport.events == (
        LoopEvent(0, "note_on", 48, 92),
        LoopEvent(800, "note_off", 48, 0),
    )


def test_live_and_loop_note_ownership_prevents_accidental_note_cutoff() -> None:
    sink = MemoryMidiOutput()
    transport = LoopTransport(sink)
    transport._events = [
        LoopEvent(0, "note_on", 60, 90),
        LoopEvent(100, "note_off", 60),
    ]
    transport._loop_length_ms = 500

    transport.note_on(60, 110)
    transport.start_playback(0)
    transport.tick(0)
    transport.tick(100)

    assert sink.messages == [("note_on", 60, 110)]
    transport.note_off(60)
    assert sink.messages[-1] == ("note_off", 60, None)


def test_clear_releases_loop_notes_and_resets_transport() -> None:
    sink = MemoryMidiOutput()
    transport = LoopTransport(sink)
    transport._events = [LoopEvent(0, "note_on", 67, 96)]
    transport._loop_length_ms = 500
    transport.start_playback(0)
    transport.tick(0)

    transport.clear()

    assert sink.messages[-1] == ("note_off", 67, None)
    assert transport.snapshot().as_dict() == {
        "recording": False,
        "playing": False,
        "event_count": 0,
        "loop_length_ms": 0,
    }


def test_program_changes_are_recorded_and_replayed() -> None:
    now = [0]
    sink = MemoryMidiOutput()
    transport = LoopTransport(sink, clock_ms=lambda: now[0])

    transport.start_recording()
    now[0] = 100
    transport.program_change(37)
    now[0] = 600
    assert transport.stop_recording()
    assert transport.start_playback(600)
    transport.tick(700)

    assert sink.messages.count(("program", 37, None)) == 2
