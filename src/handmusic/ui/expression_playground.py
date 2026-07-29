from __future__ import annotations

from collections import deque
from math import cos, sin

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ExpressionPlayground(QWidget):
    """Software-rendered 3D view of the right hand's musical expression space."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 270)
        self._state: dict[str, float | int] = {
            "x": 0.5,
            "y": 0.5,
            "z": 0.5,
            "motion": 0.0,
            "vibrato": 0,
            "expression": 64,
            "brightness": 64,
            "volume": 96,
            "reverb": 0,
            "delay": 0,
            "chorus": 0,
        }
        self._trail: deque[tuple[float, float, float]] = deque(maxlen=36)

    def update_state(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        for key in self._state:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                self._state[key] = value
        point = (
            float(self._state["x"]) * 2.0 - 1.0,
            1.0 - float(self._state["y"]) * 2.0,
            float(self._state["z"]) * 2.0 - 1.0,
        )
        self._trail.append(point)
        self.update()

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#081120"))
        gradient.setColorAt(0.55, QColor("#10152b"))
        gradient.setColorAt(1.0, QColor("#170d26"))
        painter.fillRect(self.rect(), gradient)

        cube = [
            (-1.0, -1.0, -1.0),
            (1.0, -1.0, -1.0),
            (1.0, 1.0, -1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, 1.0),
            (-1.0, 1.0, 1.0),
        ]
        edges = (
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 0),
            (4, 5),
            (5, 6),
            (6, 7),
            (7, 4),
            (0, 4),
            (1, 5),
            (2, 6),
            (3, 7),
        )
        projected = [self._project(*point) for point in cube]
        painter.setPen(QPen(QColor(70, 130, 190, 105), 1.2))
        for start, end in edges:
            painter.drawLine(projected[start], projected[end])

        trail = [self._project(*point) for point in self._trail]
        for index in range(1, len(trail)):
            alpha = round(30 + 180 * index / max(len(trail), 1))
            painter.setPen(QPen(QColor(63, 215, 255, alpha), 1.0 + index / 16.0))
            painter.drawLine(trail[index - 1], trail[index])

        hand = self._project(
            float(self._state["x"]) * 2.0 - 1.0,
            1.0 - float(self._state["y"]) * 2.0,
            float(self._state["z"]) * 2.0 - 1.0,
        )
        vibrato = int(self._state["vibrato"])
        radius = 7.0 + vibrato / 18.0
        painter.setPen(QPen(QColor("#d9fbff"), 2.0))
        painter.setBrush(QColor(50, 225, 255, 210))
        painter.drawEllipse(QRectF(hand.x() - radius, hand.y() - radius, radius * 2, radius * 2))

        painter.setPen(QColor("#dce9ff"))
        painter.drawText(14, 24, "3D EXPRESSION PLAYGROUND")
        painter.setPen(QColor("#75cfff"))
        painter.drawText(14, self.height() - 16, "X NOTE  •  Y DYNAMICS  •  Z TIMBRE / DEPTH")
        self._draw_meter(painter, "VIBRATO", vibrato, 16)
        self._draw_meter(painter, "EXPRESSION", int(self._state["expression"]), 42)
        self._draw_meter(painter, "TIMBRE", int(self._state["brightness"]), 68)
        self._draw_meter(painter, "REVERB", int(self._state["reverb"]), 94)
        painter.end()

    def _project(self, x: float, y: float, z: float) -> QPointF:
        yaw = -0.65
        pitch = 0.38
        rotated_x = x * cos(yaw) - z * sin(yaw)
        rotated_z = x * sin(yaw) + z * cos(yaw)
        rotated_y = y * cos(pitch) - rotated_z * sin(pitch)
        depth = y * sin(pitch) + rotated_z * cos(pitch)
        perspective = 1.0 / max(0.45, 1.55 + depth * 0.28)
        scale = min(self.width() * 0.28, self.height() * 0.42)
        return QPointF(
            self.width() * 0.5 + rotated_x * scale * perspective,
            self.height() * 0.53 - rotated_y * scale * perspective,
        )

    def _draw_meter(self, painter: QPainter, label: str, value: int, y: int) -> None:
        x = max(14, self.width() - 142)
        painter.setPen(QColor(160, 183, 215))
        painter.drawText(x, y, f"{label} {value:03d}")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(35, 52, 78, 210))
        painter.drawRoundedRect(QRectF(x, y + 5, 118, 5), 2, 2)
        painter.setBrush(QColor("#9b68ff"))
        painter.drawRoundedRect(QRectF(x, y + 5, 118 * value / 127.0, 5), 2, 2)
