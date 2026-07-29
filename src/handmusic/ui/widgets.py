"""Reusable PySide6 controls for the SammyBlaze performer interface."""

from __future__ import annotations

from math import cos, pi, sin
from typing import Any

from handmusic.ui.theme import COLORS, METRICS

try:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontMetrics,
        QLinearGradient,
        QPainter,
        QPen,
        QRadialGradient,
    )
    from PySide6.QtWidgets import (
        QDial,
        QFrame,
        QGraphicsDropShadowEffect,
        QLabel,
        QPushButton,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError as _PYSIDE6_ERROR:  # pragma: no cover - optional UI dependency
    PYSIDE6_AVAILABLE = False
    _QT_IMPORT_ERROR = _PYSIDE6_ERROR

    class _QtUnavailable:
        """Placeholder that keeps this module importable without the UI extra."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError(
                "PySide6 is required for SammyBlaze UI widgets; install the [ui] extra"
            ) from _QT_IMPORT_ERROR

    class NeonPanel(_QtUnavailable):
        pass

    class SectionTitle(_QtUnavailable):
        pass

    class MetricTile(_QtUnavailable):
        pass

    class NavButton(_QtUnavailable):
        pass

    class ParameterKnob(_QtUnavailable):
        pass

    def style_compact_field(widget: Any) -> Any:
        """Raise the same useful dependency error as the widget placeholders."""

        del widget
        raise RuntimeError(
            "PySide6 is required for SammyBlaze UI widgets; install the [ui] extra"
        ) from _QT_IMPORT_ERROR

else:
    PYSIDE6_AVAILABLE = True

    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    class NeonPanel(QFrame):
        """A dark translucent instrument panel with an optional cyan glow."""

        def __init__(
            self,
            parent: QWidget | None = None,
            *,
            accent: bool = False,
            glow: bool = False,
        ) -> None:
            super().__init__(parent)
            self.setObjectName("neonPanel")
            self.setProperty("neonPanel", True)
            self.setProperty("accent", accent)
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._glow_enabled = False
            self.set_glow(glow)

        def set_accent(self, enabled: bool) -> None:
            """Toggle the brighter cyan border."""

            self.setProperty("accent", bool(enabled))
            _repolish(self)

        def set_glow(self, enabled: bool) -> None:
            """Toggle a restrained cyan shadow around the panel."""

            enabled = bool(enabled)
            if enabled == self._glow_enabled:
                return
            self._glow_enabled = enabled
            if enabled:
                shadow = QGraphicsDropShadowEffect(self)
                shadow.setBlurRadius(24)
                shadow.setOffset(0, 0)
                shadow.setColor(QColor(0, 229, 229, 72))
                self.setGraphicsEffect(shadow)
            else:
                self.setGraphicsEffect(None)

        @property
        def glow_enabled(self) -> bool:
            return self._glow_enabled

    class SectionTitle(QLabel):
        """Compact uppercase heading used inside instrument panels."""

        def __init__(
            self,
            text: str,
            parent: QWidget | None = None,
            *,
            accent: bool = False,
        ) -> None:
            super().__init__(text.upper(), parent)
            self.setProperty("sectionTitle", True)
            self.setProperty("accent", accent)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.setAccessibleName(text)

        def set_accent(self, enabled: bool) -> None:
            self.setProperty("accent", bool(enabled))
            _repolish(self)

    class MetricTile(QFrame):
        """Small telemetry tile with label, primary value, and optional detail."""

        def __init__(
            self,
            label: str,
            value: str | int | float = "—",
            detail: str = "",
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setObjectName("metricTile")
            self.setProperty("metricTile", True)
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.setMinimumWidth(112)
            self.setAccessibleName(label)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(
                METRICS.spacing_md,
                METRICS.spacing_sm,
                METRICS.spacing_md,
                METRICS.spacing_sm,
            )
            layout.setSpacing(2)

            self.label_widget = QLabel(label.upper(), self)
            self.label_widget.setProperty("metricLabel", True)
            self.value_widget = QLabel(str(value), self)
            self.value_widget.setProperty("metricValue", True)
            self.detail_widget = QLabel(detail, self)
            self.detail_widget.setProperty("metricDetail", True)
            self.detail_widget.setVisible(bool(detail))

            layout.addWidget(self.label_widget)
            layout.addWidget(self.value_widget)
            layout.addWidget(self.detail_widget)

        @property
        def value_text(self) -> str:
            return self.value_widget.text()

        def set_value(self, value: str | int | float) -> None:
            """Update the prominent telemetry value."""

            self.value_widget.setText(str(value))

        def set_detail(self, detail: str) -> None:
            """Update or hide the supporting detail line."""

            self.detail_widget.setText(detail)
            self.detail_widget.setVisible(bool(detail))

    class NavButton(QPushButton):
        """Checkable sidebar button with optional icon-like glyph above its label."""

        def __init__(
            self,
            text: str,
            parent: QWidget | None = None,
            *,
            glyph: str = "",
        ) -> None:
            display_text = f"{glyph}\n{text.upper()}" if glyph else text.upper()
            super().__init__(display_text, parent)
            self.label = text
            self.glyph = glyph
            self.setProperty("navButton", True)
            self.setCheckable(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setMinimumWidth(METRICS.nav_width)
            self.setAccessibleName(text)

        def set_active(self, active: bool) -> None:
            """Semantic alias for selecting a navigation destination."""

            self.setChecked(active)

    class ParameterKnob(QDial):
        """Hardware-style dial that presents a logical float or integer value.

        QDial is integer-based internally.  This control maps that internal
        position to ``minimum``/``maximum`` and emits logical values through
        :attr:`value_changed`.  Call :meth:`set_value` (or ``setValue``) with
        the real parameter value; callers never need to handle raw dial steps.
        """

        value_changed = Signal(float)

        def __init__(
            self,
            label: str,
            parent: QWidget | None = None,
            *,
            minimum: float = 0.0,
            maximum: float = 100.0,
            value: float = 0.0,
            decimals: int = 0,
            unit: str = "",
        ) -> None:
            if maximum <= minimum:
                raise ValueError("maximum must be greater than minimum")
            if decimals < 0 or decimals > 6:
                raise ValueError("decimals must be between 0 and 6")

            super().__init__(parent)
            self._label = str(label)
            self._logical_minimum = float(minimum)
            self._logical_maximum = float(maximum)
            self._decimals = int(decimals)
            self._unit = str(unit)
            self._tick_count = 11
            self._resolution = self._resolution_for_range()

            super().setRange(0, self._resolution)
            super().setNotchesVisible(False)
            super().setWrapping(False)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setMinimumSize(104, 132)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.setAccessibleName(self._label)
            self.valueChanged.connect(self._emit_logical_value)
            self.set_value(value)

        def _resolution_for_range(self) -> int:
            span = self._logical_maximum - self._logical_minimum
            requested = round(span * (10**self._decimals))
            return max(1, min(1_000_000, requested))

        def _logical_from_raw(self, raw: int) -> float:
            ratio = raw / self._resolution
            value = self._logical_minimum + ratio * (self._logical_maximum - self._logical_minimum)
            return round(value, self._decimals)

        def _raw_from_logical(self, value: float) -> int:
            clamped = min(self._logical_maximum, max(self._logical_minimum, float(value)))
            ratio = (clamped - self._logical_minimum) / (
                self._logical_maximum - self._logical_minimum
            )
            return round(ratio * self._resolution)

        def _emit_logical_value(self, _raw: int) -> None:
            self.update()
            self.setAccessibleDescription(self.formatted_value())
            self.value_changed.emit(float(self.value()))

        def minimum(self) -> float | int:
            """Return the logical minimum rather than QDial's raw minimum."""

            return self._coerce_type(self._logical_minimum)

        def maximum(self) -> float | int:
            """Return the logical maximum rather than QDial's raw maximum."""

            return self._coerce_type(self._logical_maximum)

        def value(self) -> float | int:
            """Return the current logical value."""

            return self._coerce_type(self._logical_from_raw(super().value()))

        def _coerce_type(self, value: float) -> float | int:
            return int(round(value)) if self._decimals == 0 else float(value)

        def setValue(self, value: float) -> None:  # noqa: N802 - Qt-compatible API
            """Set the logical parameter value and clamp it to the configured range."""

            super().setValue(self._raw_from_logical(value))
            self.setAccessibleDescription(self.formatted_value())
            self.update()

        def set_value(self, value: float) -> None:
            """Snake-case alias for :meth:`setValue`."""

            self.setValue(value)

        def setRange(  # noqa: N802 - Qt-compatible API
            self,
            minimum: float,
            maximum: float,
        ) -> None:
            """Set the logical range while retaining the closest current value."""

            self.set_range(minimum, maximum)

        def set_range(
            self,
            minimum: float,
            maximum: float,
            *,
            decimals: int | None = None,
        ) -> None:
            """Reconfigure the logical range and optionally its display precision."""

            if maximum <= minimum:
                raise ValueError("maximum must be greater than minimum")
            if decimals is not None and (decimals < 0 or decimals > 6):
                raise ValueError("decimals must be between 0 and 6")
            previous = float(self.value())
            self._logical_minimum = float(minimum)
            self._logical_maximum = float(maximum)
            if decimals is not None:
                self._decimals = int(decimals)
            self._resolution = self._resolution_for_range()
            super().setRange(0, self._resolution)
            self.set_value(previous)

        def setMinimum(self, minimum: float) -> None:  # noqa: N802
            self.set_range(minimum, self._logical_maximum)

        def setMaximum(self, maximum: float) -> None:  # noqa: N802
            self.set_range(self._logical_minimum, maximum)

        @property
        def label(self) -> str:
            return self._label

        def set_label(self, label: str) -> None:
            self._label = str(label)
            self.setAccessibleName(self._label)
            self.update()

        @property
        def unit(self) -> str:
            return self._unit

        def set_unit(self, unit: str) -> None:
            self._unit = str(unit)
            self.setAccessibleDescription(self.formatted_value())
            self.update()

        @property
        def decimals(self) -> int:
            return self._decimals

        def formatted_value(self) -> str:
            number = f"{float(self.value()):.{self._decimals}f}"
            return f"{number}{self._unit}"

        def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
            return QSize(124, 148)

        def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
            del event
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            width = float(self.width())
            dial_size = min(width - 20.0, float(self.height()) - 50.0, 100.0)
            dial_size = max(58.0, dial_size)
            center = QPointF(width / 2.0, 16.0 + dial_size / 2.0)
            radius = dial_size / 2.0
            arc_rect = QRectF(
                center.x() - radius + 7.0,
                center.y() - radius + 7.0,
                (radius - 7.0) * 2.0,
                (radius - 7.0) * 2.0,
            )

            self._paint_ticks(painter, center, radius)

            painter.setPen(QPen(QColor(COLORS.track), 5.0, Qt.PenStyle.SolidLine))
            painter.drawArc(arc_rect, -225 * 16, 270 * 16)

            ratio = super().value() / max(self._resolution, 1)
            active_pen = QPen(QColor(COLORS.accent), 5.0, Qt.PenStyle.SolidLine)
            active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(active_pen)
            painter.drawArc(arc_rect, -225 * 16, round(270 * 16 * ratio))

            body_rect = QRectF(
                center.x() - radius + 12.0,
                center.y() - radius + 12.0,
                (radius - 12.0) * 2.0,
                (radius - 12.0) * 2.0,
            )
            body_gradient = QRadialGradient(
                center.x() - radius * 0.25,
                center.y() - radius * 0.28,
                radius,
            )
            body_gradient.setColorAt(0.0, QColor("#19343D"))
            body_gradient.setColorAt(0.55, QColor("#0A1A21"))
            body_gradient.setColorAt(1.0, QColor("#02090D"))
            painter.setBrush(body_gradient)
            painter.setPen(QPen(QColor(COLORS.panel_border), 1.2))
            painter.drawEllipse(body_rect)

            inner_rect = body_rect.adjusted(7.0, 7.0, -7.0, -7.0)
            highlight = QLinearGradient(
                inner_rect.left(),
                inner_rect.top(),
                inner_rect.right(),
                inner_rect.bottom(),
            )
            highlight.setColorAt(0.0, QColor(255, 255, 255, 18))
            highlight.setColorAt(0.5, QColor(0, 0, 0, 0))
            highlight.setColorAt(1.0, QColor(0, 0, 0, 80))
            painter.setBrush(highlight)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(inner_rect)

            self._paint_pointer(painter, center, radius, ratio)
            self._paint_text(painter, center, radius)

            if self.hasFocus():
                focus_pen = QPen(QColor(COLORS.accent_bright), 1.0, Qt.PenStyle.DotLine)
                painter.setPen(focus_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 6, 6)
            painter.end()

        def _paint_ticks(self, painter: QPainter, center: QPointF, radius: float) -> None:
            for index in range(self._tick_count):
                ratio = index / (self._tick_count - 1)
                angle = (135.0 + ratio * 270.0) * pi / 180.0
                outer = radius - 1.5
                inner = outer - (5.0 if index in (0, self._tick_count - 1) else 3.0)
                start = QPointF(
                    center.x() + cos(angle) * inner,
                    center.y() + sin(angle) * inner,
                )
                end = QPointF(
                    center.x() + cos(angle) * outer,
                    center.y() + sin(angle) * outer,
                )
                current = super().value() / max(self._resolution, 1)
                color = COLORS.accent if ratio <= current else COLORS.text_muted
                painter.setPen(QPen(QColor(color), 1.1))
                painter.drawLine(start, end)

        def _paint_pointer(
            self,
            painter: QPainter,
            center: QPointF,
            radius: float,
            ratio: float,
        ) -> None:
            angle = (135.0 + ratio * 270.0) * pi / 180.0
            inner = radius * 0.20
            outer = radius * 0.55
            start = QPointF(
                center.x() + cos(angle) * inner,
                center.y() + sin(angle) * inner,
            )
            end = QPointF(
                center.x() + cos(angle) * outer,
                center.y() + sin(angle) * outer,
            )
            glow_pen = QPen(QColor(0, 229, 229, 60), 6.0)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.drawLine(start, end)
            pointer_pen = QPen(QColor(COLORS.accent_bright), 2.2)
            pointer_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pointer_pen)
            painter.drawLine(start, end)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS.accent_bright))
            painter.drawEllipse(QRectF(center.x() - 2.2, center.y() - 2.2, 4.4, 4.4))

        def _paint_text(self, painter: QPainter, center: QPointF, radius: float) -> None:
            label_font = QFont(self.font())
            label_font.setPixelSize(10)
            label_font.setWeight(QFont.Weight.DemiBold)
            label_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
            painter.setFont(label_font)
            painter.setPen(QColor(COLORS.text_secondary))
            label_rect = QRectF(4.0, center.y() + radius + 1.0, self.width() - 8.0, 18.0)
            elided = QFontMetrics(label_font).elidedText(
                self._label.upper(),
                Qt.TextElideMode.ElideRight,
                round(label_rect.width()),
            )
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, elided)

            value_font = QFont(self.font())
            value_font.setPixelSize(12)
            value_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(value_font)
            painter.setPen(QColor(COLORS.accent_bright))
            value_rect = QRectF(4.0, label_rect.bottom() - 1.0, self.width() - 8.0, 20.0)
            painter.drawText(
                value_rect,
                Qt.AlignmentFlag.AlignCenter,
                self.formatted_value(),
            )

    def style_compact_field(widget: QWidget) -> QWidget:
        """Mark a standard Qt input as a compact SammyBlaze field."""

        widget.setProperty("compactField", True)
        widget.setMinimumHeight(30)
        _repolish(widget)
        return widget


__all__ = [
    "MetricTile",
    "NavButton",
    "NeonPanel",
    "PYSIDE6_AVAILABLE",
    "ParameterKnob",
    "SectionTitle",
    "style_compact_field",
]
