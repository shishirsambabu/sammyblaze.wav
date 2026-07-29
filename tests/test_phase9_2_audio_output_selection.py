from __future__ import annotations

import pytest

from handmusic.music import audio_output


class _NativeOutput:
    pass


class _FallbackOutput:
    pass


def test_selector_prefers_native_output(monkeypatch: pytest.MonkeyPatch) -> None:
    native = _NativeOutput()
    monkeypatch.setattr(
        audio_output,
        "NativeAudioCoreOutput",
        lambda **_kwargs: native,
    )

    selection = audio_output.create_builtin_audio_output(12)

    assert selection.output is native
    assert selection.backend_label == "Native C++ audio core"
    assert selection.warning is None


def test_development_selector_reports_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback = _FallbackOutput()

    def unavailable(**_kwargs):
        raise RuntimeError("DLL absent")

    monkeypatch.setattr(audio_output, "NativeAudioCoreOutput", unavailable)
    monkeypatch.setattr(
        audio_output,
        "BuiltinSynthOutput",
        lambda **_kwargs: fallback,
    )

    selection = audio_output.create_builtin_audio_output(4, require_native=False)

    assert selection.output is fallback
    assert selection.backend_label == "Python compatibility synth"
    assert selection.warning is not None
    assert "DLL absent" in selection.warning


def test_packaged_selector_never_silently_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(**_kwargs):
        raise RuntimeError("ABI mismatch")

    monkeypatch.setattr(audio_output, "NativeAudioCoreOutput", unavailable)
    monkeypatch.setattr(
        audio_output,
        "BuiltinSynthOutput",
        lambda **_kwargs: pytest.fail("fallback must not be constructed"),
    )

    with pytest.raises(RuntimeError, match="requires its native audio core"):
        audio_output.create_builtin_audio_output(0, require_native=True)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("off", False),
    ],
)
def test_native_requirement_environment_override(
    configured: str,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAMMYBLAZE_REQUIRE_NATIVE_AUDIO", configured)
    monkeypatch.setattr(audio_output.sys, "frozen", True, raising=False)

    assert audio_output.native_audio_required() is expected
