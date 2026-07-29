from __future__ import annotations

import handmusic.desktop_entry as desktop_entry


def test_desktop_entry_launches_ui_without_arguments(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        desktop_entry,
        "launch_ui",
        lambda: calls.append("ui") or 7,
    )
    monkeypatch.setattr(
        desktop_entry,
        "application_main",
        lambda arguments: calls.append(arguments) or 9,
    )

    assert desktop_entry.main([]) == 7
    assert calls == ["ui"]


def test_desktop_entry_forwards_bounded_hardware_arguments(monkeypatch) -> None:
    calls: list[object] = []
    arguments = ["--camera", "0", "--output", "synth", "--max-frames", "8"]
    monkeypatch.setattr(
        desktop_entry,
        "launch_ui",
        lambda: calls.append("ui") or 7,
    )
    monkeypatch.setattr(
        desktop_entry,
        "application_main",
        lambda received: calls.append(received) or 9,
    )

    assert desktop_entry.main(arguments) == 9
    assert calls == [arguments]
