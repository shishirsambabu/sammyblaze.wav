from __future__ import annotations

import sys
from threading import Event
from typing import Any

from handmusic.app import default_runtime, run_camera
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput, PluginBridgeOutput
from handmusic.music.progression import progression_names
from handmusic.music.scale import scale_names
from handmusic.telemetry import PerformanceTelemetry, TelemetrySnapshot


def list_midi_output_ports() -> list[str]:
    """Return available output names without opening a port for writing."""

    try:
        import mido

        return list(mido.get_output_names())
    except Exception:  # pragma: no cover - depends on optional host MIDI drivers
        return []


try:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QImage, QPixmap
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
        progression_name: str = "pop",
        scale_name: str = "major",
    ) -> int:
        raise RuntimeError(
            "Install the [ui] extra to use the desktop performer UI"
        ) from _UI_IMPORT_ERROR

else:

    class SessionWorker(QThread):
        state_changed = Signal(str)
        telemetry_updated = Signal(object)
        failed = Signal(str)
        frame_ready = Signal(object)
        camera_health = Signal(str)
        midi_health = Signal(str)
        performance_state = Signal(str)
        expression_updated = Signal(object)
        transport_updated = Signal(object)

        def __init__(
            self,
            camera_index: int,
            output_mode: str,
            midi_port: str | None,
            progression_name: str = "pop",
            scale_name: str = "major",
        ) -> None:
            super().__init__()
            self.camera_index = camera_index
            self.output_mode = output_mode
            self.midi_port = midi_port
            self.progression_name = progression_name
            self.scale_name = scale_name
            self.stop_event = Event()
            self.runtime: Any | None = None

        def request_stop(self) -> None:
            self.stop_event.set()

        def _publish_telemetry(self, snapshot: TelemetrySnapshot) -> None:
            self.telemetry_updated.emit(snapshot.as_dict())

        def _publish_frame(self, frame: object) -> None:
            self.camera_health.emit("Camera: active")
            self.frame_ready.emit(frame)

        def _publish_state(self, state: str) -> None:
            self.performance_state.emit(state)

        def _publish_expression(self, state: object) -> None:
            as_dict = getattr(state, "as_dict", None)
            self.expression_updated.emit(as_dict() if as_dict is not None else {})

        def _publish_transport(self, snapshot: object) -> None:
            as_dict = getattr(snapshot, "as_dict", None)
            self.transport_updated.emit(as_dict() if as_dict is not None else {})

        def toggle_recording(self) -> None:
            if self.runtime is not None:
                self._publish_transport(self.runtime.toggle_recording())

        def toggle_playback(self) -> None:
            if self.runtime is not None:
                self._publish_transport(self.runtime.toggle_playback())

        def clear_loop(self) -> None:
            if self.runtime is not None:
                self._publish_transport(self.runtime.clear_loop())

        def toggle_sustain(self) -> None:
            if self.runtime is not None:
                self.runtime.notes.set_sustain(not self.runtime.notes.sustain_enabled)
                self._publish_state(self.runtime.status_label)

        def panic(self) -> None:
            if self.runtime is not None:
                self.runtime.stop_for_tracking_loss()
                self._publish_state(self.runtime.status_label)

        def run(self) -> None:  # pragma: no cover - requires a desktop and camera
            runtime = None
            telemetry = PerformanceTelemetry()
            error_message: str | None = None
            try:
                if self.output_mode == "midi":
                    self.state_changed.emit("Connecting MIDI...")
                    output: Any = MidoOutput(self.midi_port)
                    self.midi_health.emit(f"MIDI: connected ({self.midi_port or 'default'})")
                elif self.output_mode == "plugin":
                    self.state_changed.emit("Connecting plug-in bridge...")
                    output = PluginBridgeOutput()
                    self.midi_health.emit("VST3 bridge: localhost:18736")
                else:
                    self.state_changed.emit("Starting camera...")
                    output = MemoryMidiOutput()
                    self.midi_health.emit("MIDI: null output")
                runtime, _ = default_runtime(
                    output,
                    progression_name=self.progression_name,
                    scale_name=self.scale_name,
                )
                self.runtime = runtime
                self.state_changed.emit("Running")
                self.camera_health.emit("Camera: opening...")
                run_camera(
                    runtime,
                    self.camera_index,
                    telemetry=telemetry,
                    stop_event=self.stop_event,
                    telemetry_callback=self._publish_telemetry,
                    frame_callback=self._publish_frame,
                    state_callback=self._publish_state,
                    expression_callback=self._publish_expression,
                    transport_callback=self._publish_transport,
                    display=False,
                )
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                self.camera_health.emit("Camera: error")
                self.failed.emit(error_message)
            finally:
                if runtime is not None:
                    runtime.close()
                self.runtime = None
                self.telemetry_updated.emit(telemetry.snapshot().as_dict())
                if error_message is None:
                    self.camera_health.emit("Camera: stopped")
                    self.state_changed.emit("Stopped")


    class PerformerWindow(QMainWindow):
        def __init__(
            self,
            camera_index: int = 0,
            midi_port: str | None = None,
            output_mode: str = "midi",
            progression_name: str = "pop",
            scale_name: str = "major",
        ) -> None:
            super().__init__()
            self.setWindowTitle("SammyBlaze.wav Performer")
            self.resize(1180, 780)
            self.worker: SessionWorker | None = None
            self._preferred_midi_port = midi_port
            self._preferred_progression = progression_name
            self._preferred_scale = scale_name
            self._last_frame: QImage | None = None

            central = QWidget()
            layout = QVBoxLayout(central)
            form = QFormLayout()

            self.camera = QSpinBox()
            self.camera.setRange(0, 9)
            self.camera.setValue(camera_index)
            form.addRow("Camera index", self.camera)

            self.output = QComboBox()
            self.output.addItem("MIDI", "midi")
            self.output.addItem("FL Studio / VST3 bridge", "plugin")
            self.output.addItem("Null output", "null")
            requested_mode = output_mode if output_mode in ("midi", "plugin", "null") else "midi"
            self.output.setCurrentIndex(self.output.findData(requested_mode))
            form.addRow("Output", self.output)

            self.progression = QComboBox()
            for name in progression_names():
                self.progression.addItem(name.replace("_", " ").title(), name)
            progression_index = self.progression.findData(self._preferred_progression)
            if progression_index >= 0:
                self.progression.setCurrentIndex(progression_index)
            form.addRow("Chord sequence", self.progression)

            self.scale = QComboBox()
            for name in scale_names():
                self.scale.addItem(name.replace("_", " ").title(), name)
            scale_index = self.scale.findData(self._preferred_scale)
            if scale_index >= 0:
                self.scale.setCurrentIndex(scale_index)
            form.addRow("Starting lead mode", self.scale)

            self.midi_port = QComboBox()
            form.addRow("MIDI output", self.midi_port)
            layout.addLayout(form)

            self.refresh_button = QPushButton("Refresh MIDI ports")
            self.refresh_button.clicked.connect(self.refresh_ports)
            layout.addWidget(self.refresh_button)

            from handmusic.ui.expression_playground import ExpressionPlayground

            visual_row = QHBoxLayout()
            self.video = QLabel("Camera preview idle")
            self.video.setMinimumSize(480, 270)
            self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.video.setStyleSheet("background-color: #12151c; color: #aab4c3;")
            visual_row.addWidget(self.video, 3)
            self.expression_playground = ExpressionPlayground()
            visual_row.addWidget(self.expression_playground, 2)
            layout.addLayout(visual_row)

            health = QHBoxLayout()
            self.camera_health = QLabel("Camera: idle")
            self.midi_health = QLabel("MIDI: not connected")
            health.addWidget(self.camera_health)
            health.addWidget(self.midi_health)
            layout.addLayout(health)

            self.status = QLabel("Ready")
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.performance_state = QLabel(
                "Mode: chord + scale | Chord latch: ready | Pedal: off | Scale: Major"
            )
            self.performance_state.setWordWrap(True)
            layout.addWidget(self.performance_state)
            self.instructions = QLabel(
                "Left hand chord shapes: index=I, two=ii, three=iii, four=IV, open=V, "
                "shaka=vi, L-shape=vii. Hold a shape steadily; fist is panic. Left pinch cycles "
                "the chord-aware lead mode. Right X plays scale degrees, movement adds vibrato, "
                "Y shapes dynamics, Z shapes expression/timbre, and right pinch re-articulates."
            )
            self.instructions.setWordWrap(True)
            layout.addWidget(self.instructions)
            self.telemetry = QLabel("No performance telemetry yet")
            self.telemetry.setWordWrap(True)
            layout.addWidget(self.telemetry)

            transport = QHBoxLayout()
            self.record_button = QPushButton("Record loop")
            self.record_button.clicked.connect(self.toggle_recording)
            self.record_button.setEnabled(False)
            transport.addWidget(self.record_button)
            self.play_button = QPushButton("Play loop")
            self.play_button.clicked.connect(self.toggle_playback)
            self.play_button.setEnabled(False)
            transport.addWidget(self.play_button)
            self.clear_button = QPushButton("Clear loop")
            self.clear_button.clicked.connect(self.clear_loop)
            self.clear_button.setEnabled(False)
            transport.addWidget(self.clear_button)
            self.pedal_button = QPushButton("Sustain pedal")
            self.pedal_button.clicked.connect(self.toggle_sustain)
            self.pedal_button.setEnabled(False)
            transport.addWidget(self.pedal_button)
            self.panic_button = QPushButton("PANIC")
            self.panic_button.clicked.connect(self.panic)
            self.panic_button.setEnabled(False)
            transport.addWidget(self.panic_button)
            layout.addLayout(transport)
            self.transport_state = QLabel("Loop: empty")
            layout.addWidget(self.transport_state)

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
            self.progression.setEnabled(enabled)
            self.scale.setEnabled(enabled)
            self.refresh_button.setEnabled(enabled)
            self.start_button.setEnabled(enabled)
            self.stop_button.setEnabled(not enabled)
            for button in (
                self.record_button,
                self.play_button,
                self.clear_button,
                self.pedal_button,
                self.panic_button,
            ):
                button.setEnabled(not enabled)
            self._update_port_enabled()

        def start_session(self) -> None:
            if self.worker is not None and self.worker.isRunning():
                return
            self.worker = SessionWorker(
                camera_index=self.camera.value(),
                output_mode=self.output.currentData(),
                midi_port=self.midi_port.currentData(),
                progression_name=self.progression.currentData(),
                scale_name=self.scale.currentData(),
            )
            self.worker.state_changed.connect(self.status.setText)
            self.worker.telemetry_updated.connect(self.update_telemetry)
            self.worker.failed.connect(self.status.setText)
            self.worker.frame_ready.connect(self.update_frame)
            self.worker.camera_health.connect(self.camera_health.setText)
            self.worker.midi_health.connect(self.midi_health.setText)
            self.worker.performance_state.connect(self.performance_state.setText)
            self.worker.expression_updated.connect(self.expression_playground.update_state)
            self.worker.transport_updated.connect(self.update_transport)
            self.worker.finished.connect(lambda: self._set_controls_enabled(True))
            self._set_controls_enabled(False)
            self.status.setText("Starting...")
            self.worker.start()

        def stop_session(self) -> None:
            if self.worker is not None and self.worker.isRunning():
                self.status.setText("Stopping...")
                self.worker.request_stop()

        def toggle_recording(self) -> None:
            if self.worker is not None:
                self.worker.toggle_recording()

        def toggle_playback(self) -> None:
            if self.worker is not None:
                self.worker.toggle_playback()

        def clear_loop(self) -> None:
            if self.worker is not None:
                self.worker.clear_loop()

        def toggle_sustain(self) -> None:
            if self.worker is not None:
                self.worker.toggle_sustain()

        def panic(self) -> None:
            if self.worker is not None:
                self.worker.panic()

        def update_transport(self, payload: object) -> None:
            state = payload if isinstance(payload, dict) else {}
            recording = bool(state.get("recording", False))
            playing = bool(state.get("playing", False))
            events = int(state.get("event_count", 0))
            length_ms = int(state.get("loop_length_ms", 0))
            self.record_button.setText("Stop recording" if recording else "Record loop")
            self.play_button.setText("Stop loop" if playing else "Play loop")
            self.transport_state.setText(
                f"Loop: {'recording' if recording else 'playing' if playing else 'ready'} | "
                f"{events} events | {length_ms / 1000.0:.2f} seconds"
            )

        def update_frame(self, payload: object) -> None:
            try:
                import cv2

                frame = cv2.cvtColor(payload, cv2.COLOR_BGR2RGB)
                height, width, channels = frame.shape
                self._last_frame = QImage(
                    frame.data,
                    width,
                    height,
                    channels * width,
                    QImage.Format.Format_RGB888,
                ).copy()
                self._render_frame()
            except Exception as exc:
                self.status.setText(f"Video error: {exc}")

        def _render_frame(self) -> None:
            if self._last_frame is None:
                return
            pixmap = QPixmap.fromImage(self._last_frame).scaled(
                self.video.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.video.setPixmap(pixmap)

        def resizeEvent(self, event: object) -> None:
            self._render_frame()
            super().resizeEvent(event)

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
        progression_name: str = "pop",
        scale_name: str = "major",
    ) -> int:
        app = QApplication.instance() or QApplication(sys.argv)
        window = PerformerWindow(
            camera_index,
            midi_port,
            output_mode,
            progression_name,
            scale_name,
        )
        window.show()
        return app.exec()


__all__ = ["list_midi_output_ports", "launch_ui"]
