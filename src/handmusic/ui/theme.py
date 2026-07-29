"""SammyBlaze's reusable futuristic dark-cyan visual system.

The module deliberately contains no Qt imports.  Theme tokens can therefore be
used by non-UI code and imported on installations that do not include PySide6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Named colors used throughout the performer and plug-in interfaces."""

    background: str = "#020A0F"
    background_alt: str = "#051219"
    surface: str = "#071820"
    surface_raised: str = "#0A202A"
    surface_hover: str = "#0D2A35"
    panel: str = "rgba(5, 20, 28, 232)"
    panel_border: str = "#123541"
    panel_border_soft: str = "#0B2731"
    accent: str = "#00E5E5"
    accent_bright: str = "#52FFFF"
    accent_dim: str = "#087F8A"
    accent_muted: str = "#0E5661"
    accent_glow: str = "rgba(0, 229, 229, 96)"
    blue: str = "#2D5BFF"
    success: str = "#48EE63"
    warning: str = "#FFBD4A"
    danger: str = "#FF4966"
    text: str = "#E5F7FA"
    text_secondary: str = "#A9C2C9"
    text_muted: str = "#66828A"
    disabled: str = "#40545A"
    track: str = "#142D35"
    shadow: str = "rgba(0, 0, 0, 150)"


@dataclass(frozen=True, slots=True)
class ThemeMetrics:
    """Shared sizing values in device-independent pixels."""

    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 18
    spacing_xl: int = 24
    radius_sm: int = 5
    radius_md: int = 9
    radius_lg: int = 14
    field_height: int = 36
    control_height: int = 42
    nav_width: int = 86
    border_width: int = 1


COLORS = ThemeColors()
METRICS = ThemeMetrics()

# Convenient aliases for custom painting code and lightweight integrations.
BACKGROUND = COLORS.background
SURFACE = COLORS.surface
PANEL = COLORS.panel
PANEL_BORDER = COLORS.panel_border
CYAN = COLORS.accent
CYAN_BRIGHT = COLORS.accent_bright
TEXT_PRIMARY = COLORS.text
TEXT_SECONDARY = COLORS.text_secondary
TEXT_MUTED = COLORS.text_muted
DANGER = COLORS.danger
SUCCESS = COLORS.success

FONT_FAMILY = '"Segoe UI"'
MONO_FONT_FAMILY = '"Consolas"'


APP_STYLESHEET = f"""
/* SammyBlaze Performer — dark cyan instrument surface */
QWidget {{
    color: {COLORS.text};
    font-family: {FONT_FAMILY};
    font-size: 13px;
    selection-background-color: {COLORS.accent_dim};
    selection-color: {COLORS.text};
}}

QMainWindow,
QWidget#appRoot,
QWidget[appRoot="true"] {{
    background-color: {COLORS.background};
}}

QFrame#neonPanel,
QFrame[neonPanel="true"] {{
    background-color: {COLORS.panel};
    border: 1px solid {COLORS.panel_border};
    border-radius: {METRICS.radius_md}px;
}}

QFrame#neonPanel[accent="true"],
QFrame[neonPanel="true"][accent="true"] {{
    border-color: {COLORS.accent_dim};
}}

QFrame#metricTile,
QFrame[metricTile="true"] {{
    background-color: rgba(7, 24, 32, 205);
    border: 1px solid {COLORS.panel_border_soft};
    border-radius: {METRICS.radius_sm}px;
}}

QLabel[sectionTitle="true"] {{
    color: {COLORS.text};
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 1px;
}}

QLabel[sectionTitle="true"][accent="true"] {{
    color: {COLORS.accent};
}}

QLabel[metricLabel="true"] {{
    color: {COLORS.accent};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}}

QLabel[metricValue="true"] {{
    color: {COLORS.text};
    font-size: 17px;
    font-weight: 600;
}}

QLabel[metricDetail="true"] {{
    color: {COLORS.text_muted};
    font-size: 10px;
}}

QPushButton {{
    min-height: {METRICS.control_height}px;
    padding: 0 {METRICS.spacing_lg}px;
    color: {COLORS.text_secondary};
    background-color: rgba(7, 24, 32, 220);
    border: 1px solid {COLORS.panel_border};
    border-radius: {METRICS.radius_sm}px;
    font-weight: 600;
}}

QPushButton:hover {{
    color: {COLORS.text};
    background-color: {COLORS.surface_hover};
    border-color: {COLORS.accent_dim};
}}

QPushButton:pressed {{
    color: {COLORS.accent_bright};
    background-color: {COLORS.background_alt};
    border-color: {COLORS.accent};
}}

QPushButton:checked,
QPushButton[active="true"] {{
    color: {COLORS.accent_bright};
    background-color: rgba(0, 229, 229, 22);
    border-color: {COLORS.accent};
}}

QPushButton:disabled {{
    color: {COLORS.disabled};
    background-color: rgba(5, 18, 24, 150);
    border-color: {COLORS.panel_border_soft};
}}

QPushButton[navButton="true"] {{
    min-width: {METRICS.nav_width}px;
    min-height: 74px;
    padding: {METRICS.spacing_sm}px;
    border: 0;
    border-left: 2px solid transparent;
    border-radius: 0;
    color: {COLORS.text_muted};
    background: transparent;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton[navButton="true"]:hover {{
    color: {COLORS.text};
    background-color: rgba(0, 229, 229, 10);
    border-left-color: {COLORS.accent_dim};
}}

QPushButton[navButton="true"]:checked {{
    color: {COLORS.accent_bright};
    background-color: rgba(0, 229, 229, 18);
    border-left-color: {COLORS.accent};
}}

QPushButton[variant="primary"] {{
    color: #F2FFFF;
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #008E9B, stop:0.48 #00B9C5, stop:1 {COLORS.blue}
    );
    border: 1px solid {COLORS.accent};
    font-size: 15px;
}}

QPushButton[variant="danger"] {{
    color: {COLORS.danger};
    background-color: rgba(255, 73, 102, 12);
    border-color: #8D2739;
}}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {{
    min-height: {METRICS.field_height}px;
    padding: 0 {METRICS.spacing_md}px;
    color: {COLORS.text};
    background-color: rgba(2, 12, 17, 225);
    border: 1px solid {COLORS.panel_border};
    border-radius: {METRICS.radius_sm}px;
}}

QLineEdit[compactField="true"],
QComboBox[compactField="true"],
QSpinBox[compactField="true"],
QDoubleSpinBox[compactField="true"] {{
    min-height: 30px;
    padding-left: {METRICS.spacing_sm}px;
    padding-right: {METRICS.spacing_sm}px;
    font-size: 12px;
}}

QLineEdit:hover,
QComboBox:hover,
QAbstractSpinBox:hover {{
    border-color: {COLORS.accent_dim};
}}

QLineEdit:focus,
QComboBox:focus,
QAbstractSpinBox:focus {{
    border-color: {COLORS.accent};
}}

QComboBox::drop-down {{
    width: 28px;
    border: 0;
}}

QComboBox::down-arrow {{
    width: 7px;
    height: 7px;
    border-right: 1px solid {COLORS.text_secondary};
    border-bottom: 1px solid {COLORS.text_secondary};
}}

QComboBox QAbstractItemView {{
    color: {COLORS.text};
    background-color: {COLORS.surface};
    border: 1px solid {COLORS.accent_dim};
    outline: 0;
    selection-background-color: {COLORS.accent_dim};
    padding: {METRICS.spacing_xs}px;
}}

QCheckBox,
QRadioButton {{
    spacing: {METRICS.spacing_sm}px;
    color: {COLORS.text_secondary};
}}

QCheckBox::indicator,
QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    background-color: {COLORS.background_alt};
    border: 1px solid {COLORS.panel_border};
}}

QCheckBox::indicator {{
    border-radius: 3px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {{
    background-color: {COLORS.accent};
    border-color: {COLORS.accent_bright};
}}

QSlider::groove:horizontal {{
    height: 5px;
    background: {COLORS.track};
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {COLORS.accent};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    background: {COLORS.accent_bright};
    border: 2px solid {COLORS.accent_dim};
    border-radius: 7px;
}}

QProgressBar {{
    height: 6px;
    color: transparent;
    background-color: {COLORS.track};
    border: 0;
    border-radius: 3px;
}}

QProgressBar::chunk {{
    background-color: {COLORS.accent};
    border-radius: 3px;
}}

QTabWidget::pane {{
    border: 1px solid {COLORS.panel_border};
    background-color: {COLORS.background_alt};
}}

QTabBar::tab {{
    min-width: 90px;
    padding: {METRICS.spacing_md}px {METRICS.spacing_lg}px;
    color: {COLORS.text_muted};
    background: transparent;
    border-bottom: 2px solid transparent;
}}

QTabBar::tab:selected {{
    color: {COLORS.accent};
    border-bottom-color: {COLORS.accent};
}}

QScrollArea {{
    border: 0;
    background: transparent;
}}

QScrollBar:vertical {{
    width: 9px;
    margin: 0;
    background: {COLORS.background};
}}

QScrollBar::handle:vertical {{
    min-height: 28px;
    background: {COLORS.accent_muted};
    border-radius: 4px;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}

QToolTip {{
    color: {COLORS.text};
    background-color: {COLORS.surface_raised};
    border: 1px solid {COLORS.accent_dim};
    padding: {METRICS.spacing_sm}px;
}}
""".strip()

DARK_STYLESHEET = APP_STYLESHEET


class _StyleTarget(Protocol):
    def setStyleSheet(self, stylesheet: str) -> None:  # noqa: N802 - Qt naming
        """Apply a Qt stylesheet."""


def application_stylesheet() -> str:
    """Return the complete application stylesheet."""

    return APP_STYLESHEET


def apply_theme(target: _StyleTarget) -> str:
    """Apply the SammyBlaze theme to a QApplication or widget and return it."""

    target.setStyleSheet(APP_STYLESHEET)
    return APP_STYLESHEET
