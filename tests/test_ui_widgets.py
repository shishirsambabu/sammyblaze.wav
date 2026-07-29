from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox

from handmusic.ui.theme import APP_STYLESHEET, COLORS, apply_theme
from handmusic.ui.widgets import (
    PYSIDE6_AVAILABLE,
    MetricTile,
    NavButton,
    NeonPanel,
    ParameterKnob,
    SectionTitle,
    style_compact_field,
)


@pytest.fixture(scope="module")
def qt_app() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    yield app


def test_theme_exposes_complete_dark_cyan_stylesheet(qt_app: QApplication) -> None:
    assert COLORS.background in APP_STYLESHEET
    assert COLORS.accent in APP_STYLESHEET
    assert 'QFrame[neonPanel="true"]' in APP_STYLESHEET
    assert 'QPushButton[navButton="true"]' in APP_STYLESHEET

    assert apply_theme(qt_app) == APP_STYLESHEET
    assert qt_app.styleSheet() == APP_STYLESHEET


def test_panel_title_metric_and_navigation_components(qt_app: QApplication) -> None:
    assert PYSIDE6_AVAILABLE
    panel = NeonPanel(accent=True, glow=True)
    title = SectionTitle("Expression playground", panel, accent=True)
    metric = MetricTile("Gesture latency", 18.4, "p95 ms", panel)
    nav = NavButton("Perform", panel, glyph="◉")

    assert panel.property("neonPanel") is True
    assert panel.property("accent") is True
    assert panel.glow_enabled is True
    assert title.text() == "EXPRESSION PLAYGROUND"
    assert title.accessibleName() == "Expression playground"
    assert metric.value_text == "18.4"
    assert metric.detail_widget.text() == "p95 ms"

    metric.set_value("12.0")
    metric.set_detail("")
    nav.set_active(True)
    panel.set_glow(False)

    assert metric.value_text == "12.0"
    assert metric.detail_widget.isHidden()
    assert nav.isChecked()
    assert panel.graphicsEffect() is None
    qt_app.processEvents()


def test_integer_parameter_knob_clamps_formats_and_emits(qt_app: QApplication) -> None:
    knob = ParameterKnob(
        "Reverb",
        minimum=0,
        maximum=100,
        value=30,
        decimals=0,
        unit="%",
    )
    received: list[float] = []
    knob.value_changed.connect(received.append)

    assert knob.minimum() == 0
    assert knob.maximum() == 100
    assert knob.value() == 30
    assert knob.formatted_value() == "30%"

    knob.set_value(72)
    knob.setValue(500)

    assert received == [72.0, 100.0]
    assert knob.value() == 100
    assert knob.accessibleName() == "Reverb"
    assert knob.accessibleDescription() == "100%"
    qt_app.processEvents()


def test_float_parameter_knob_range_and_offscreen_paint(qt_app: QApplication) -> None:
    knob = ParameterKnob(
        "Delay time",
        minimum=20.0,
        maximum=2000.0,
        value=375.25,
        decimals=2,
        unit=" ms",
    )
    assert knob.value() == pytest.approx(375.25, abs=0.01)
    assert knob.formatted_value() == "375.25 ms"

    knob.set_range(-1.0, 1.0, decimals=2)
    knob.set_value(-0.35)
    knob.resize(knob.sizeHint())
    knob.show()
    qt_app.processEvents()
    rendered = knob.grab()

    assert knob.minimum() == pytest.approx(-1.0)
    assert knob.maximum() == pytest.approx(1.0)
    assert knob.value() == pytest.approx(-0.35, abs=0.01)
    assert not rendered.isNull()
    assert rendered.width() == knob.width()
    assert rendered.height() == knob.height()
    knob.close()


def test_parameter_knob_rejects_invalid_configuration(qt_app: QApplication) -> None:
    del qt_app
    with pytest.raises(ValueError, match="maximum"):
        ParameterKnob("Invalid", minimum=1, maximum=1)
    with pytest.raises(ValueError, match="decimals"):
        ParameterKnob("Invalid", decimals=7)


def test_compact_field_helper_marks_and_returns_widget(qt_app: QApplication) -> None:
    field = QComboBox()

    assert style_compact_field(field) is field
    assert field.property("compactField") is True
    assert field.minimumHeight() >= 30
    qt_app.processEvents()
