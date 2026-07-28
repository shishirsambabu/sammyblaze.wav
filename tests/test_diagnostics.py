from handmusic.app import main
from handmusic.diagnostics import collect_diagnostics, render_diagnostics


def test_collect_diagnostics_reports_model_metadata(tmp_path) -> None:
    model = tmp_path / "hand_landmarker.task"
    model.write_bytes(b"model")

    report = collect_diagnostics(model)

    assert report["model"]["exists"] is True
    assert report["model"]["size_bytes"] == 5
    assert report["runtime"]["python"]
    assert report["dependencies"]["application"]


def test_render_diagnostics_is_copy_paste_friendly(tmp_path) -> None:
    report = collect_diagnostics(tmp_path / "missing.task")

    rendered = render_diagnostics(report)

    assert "SammyBlaze.wav diagnostics" in rendered
    assert "Hand model: MISSING" in rendered
    assert "Dependencies:" in rendered


def test_diagnostics_command_does_not_require_camera(capsys, tmp_path) -> None:
    assert main(["--diagnostics", "--hand-model", str(tmp_path / "missing.task")]) == 0

    assert "SammyBlaze.wav diagnostics" in capsys.readouterr().out
