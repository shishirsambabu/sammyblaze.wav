from __future__ import annotations

import sys
from threading import Event
from typing import Any

from handmusic.app import default_runtime, run_camera
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput
from handmusic.telemetry import PerformanceTelemetry, TelemetrySnapshot


def list_midi_output_ports() -> list[str]:
    """Return available output names without opening a port for writing."""

    try:
        import mido

        return list(mido.get_output_names())
    except Exception:  # pragma: no cover - depends on optional host MIDI drivers
        return []


try:
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
except ImportError as _PY_SIDE_ERROR:  # pragma: no cover - depends on optional UI extra
    _UI_IMPORT_ERROR = _PY_SIDE_ERROR

    def launch_ui(
        camera_index: int = 0,
        midi_port: str | None = None,
        output_mode: str = "midi",
    ) -> int:
        raise RuntimeError(
            "Install the [ui] extra to use the desktop performer UI"
        ) from _UI_IMPORT_ERROR

else:

    class SessionWorker(QThread):
        state_changed = Signal(str)
        telemetry_updated = Signal(object)
        failed = Signal(str)

        def __init__(self, camera_index: int, output_mode: str, midi_port: str | None) -> None:
            super().__init__()
            self.camera_index = camera_index
            self.output_mode = output_mode
            self.midi_port = midi_port
            self.stop_event = Event()

        def request_stop(self) -> None:
            self.stop_event.set()

        def _publish_telemetry(self, snapshot: TelemetrySnapshot) -> None:
            self.telemetry_updated.emit(snapshot.as_dict())

        def run(self) -> None:  # pragma: no cover - requires a desktop and camera
            runtime = None
            telemetry = PerformanceTelemetry()
            error_message: str | None = None
            try:
                if self.output_mode == "midi":
                    self.state_changed.emit("Connecting MIDI...")
                    output: Any = MidoOutput(self.midi_port)
                else:
                    self.state_changed.emit("Starting camera...")
                    output = MemoryMidiOutput()
                runtime, _ = default_runtime(output)
                self.state_changed.emit("Running")
                run_camera(
                    runtime,
                    self.camera_index,
                    telemetry=telemetry,
                    stop_event=self.stop_event,
                    telemetry_callback=self._publish_telemetry,
                )
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                self.failed.emit(error_message)
            finally:
                if runtime is not None:
                    runtime.close()
                self.telemetry_updated.emit(telemetry.snapshot().as_dict())
                if error_message is None:
                    self.state_changed.emit("Stopped")


    class PerformerWindow(QMainWindow):
        def __init__(
            self,
            camera_index: int = 0,
            midi_port: str | None = None,
            output_mode: str = "midi",
        ) -> None:
            super().__init__()
            self.setWindowTitle("SammyBlaze.wav Performer")
            self.resize(560, 300)
            self.worker: SessionWorker | None = None
            self._preferred_midi_port = midi_port

            central = QWidget()
            layout = QVBoxLayout(central)
            form = QFormLayout()

            self.camera = QSpinBox()
            self.camera.setRange(0, 9)
            self.camera.setValue(camera_index)
            form.addRow("Camera index", self.camera)

            self.output = QComboBox()
            self.output.addItem("MIDI", "midi")
            self.output.addItem("Null output", "null")
            requested_mode = output_mode if output_mode in ("midi", "null") else "midi"
            self.output.setCurrentIndex(self.output.findData(requested_mode))
            form.addRow("Output", self.output)

            self.midi_port = QComboBox()
            form.addRow("MIDI output", self.midi_port)
            layout.addLayout(form)

            self.refresh_button = QPushButton("Refresh MIDI ports")
            self.refresh_button.clicked.connect(self.refresh_ports)
            layout.addWidget(self.refresh_button)

            self.status = QLabel("Ready")
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.telemetry = QLabel("No performance telemetry yet")
            self.telemetry.setWordWrap(True)
            layout.addWidget(self.telemetry)

            buttons = QHBoxLayout()
            self.start_button = QPushButton("Start performer")
            self.start_button.clicked.connect(self.start_session)
            buttons.addWidget(self.start_button)
            self.stop_button = QPushButton("Stop")
            self.stop_button.clicked.connect(self.stop_session)
            self.stop_button.setEnabled(False)
            buttons.addWidget(self.stop_button)
            layout.addLayout(buttons)

            self.setCentralWidget(central)
            self.output.currentIndexChanged.connect(self._update_port_enabled)
            self.refresh_ports()

        def refresh_ports(self) -> None:
            selected = self.midi_port.currentData() or self._preferred_midi_port
            ports = list_midi_output_ports()
            self.midi_port.clear()
            for port in ports:
                self.midi_port.addItem(port, port)
            if not ports:
                self.midi_port.addItem("No MIDI ports detected", None)
            if selected:
                index = self.midi_port.findData(selected)
                if index >= 0:
                    self.midi_port.setCurrentIndex(index)
            self._update_port_enabled()

        def _update_port_enabled(self) -> None:
            self.midi_port.setEnabled(self.output.currentData() == "midi")

        def _set_controls_enabled(self, enabled: bool) -> None:
            self.camera.setEnabled(enabled)
            self.output.setEnabled(enabled)
            self.refresh_button.setEnabled(enabled)
            self.start_button.setEnabled(enabled)
            self.stop_button.setEnabled(not enabled)
            self._update_port_enabled()

        def start_session(self) -> None:
            if self.worker is not None and self.worker.isRunning():
                return
            self.worker = SessionWorker(
                camera_index=self.camera.value(),
                output_mode=self.output.currentData(),
                midi_port=self.midi_port.currentData(),
            )
            self.worker.state_changed.connect(self.status.setText)
            self.worker.telemetry_updated.connect(self.update_telemetry)
            self.worker.failed.connect(self.status.setText)
            self.worker.finished.connect(lambda: self._set_controls_enabled(True))
            self._set_controls_enabled(False)
            self.status.setText("Starting...")
            self.worker.start()

        def stop_session(self) -> None:
            if self.worker is not None and self.worker.isRunning():
                self.status.setText("Stopping...")
                self.worker.request_stop()

        def update_telemetry(self, payload: object) -> None:
            report = payload if isinstance(payload, dict) else {}
            self.telemetry.setText(
                "Frames: "
                f"{report.get('frames_seen', 0)} | dropped: "
                f"{report.get('dropped_frames', 0)} | "
                f"FPS: {float(report.get('effective_fps', 0.0)):.1f}\n"
                "Frame age p95: "
                f"{float(report.get('p95_frame_age_ms', 0.0)):.1f} ms | "
                "Gesture latency p95: "
                f"{float(report.get('p95_gesture_latency_ms', 0.0)):.1f} ms"
            )

        def closeEvent(self, event: object) -> None:
            self.stop_session()
            if self.worker is not None and self.worker.isRunning():
                self.worker.wait(5000)
            event.accept()


    def launch_ui(
        camera_index: int = 0,
        midi_port: str | None = None,
        output_mode: str = "midi",
    ) -> int:
        app = QApplication.instance() or QApplication(sys.argv)
        window = PerformerWindow(camera_index, midi_port, output_mode)
        window.show()
        return app.exec()


__all__ = ["list_midi_output_ports", "launch_ui"]
