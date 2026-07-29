from __future__ import annotations

import sys
from dataclasses import asdict, replace
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock
from typing import Any

from handmusic import __version__
from handmusic.app import default_runtime, run_camera
from handmusic.music.builtin_synth import BuiltinSynthOutput
from handmusic.music.midi_output import MemoryMidiOutput, MidoOutput, PluginBridgeOutput
from handmusic.music.presets import (
    FILTER_TYPES,
    WAVEFORMS,
    Preset,
    category_names,
    get_preset,
    presets_by_category,
)
from handmusic.music.progression import progression_names
from handmusic.music.scale import scale_names
from handmusic.music.user_presets import (
    UserPreset,
    delete_user_preset,
    list_user_presets,
    save_user_preset,
)
from handmusic.telemetry import PerformanceTelemetry, TelemetrySnapshot


def list_midi_output_ports() -> list[str]:
    """Return available output names without opening a port for writing."""

    try:
        import mido

        return list(mido.get_output_names())
    except Exception:  # pragma: no cover - depends on optional host MIDI drivers
        return []


try:
    from PySide6.QtCore import Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QComboBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as _PY_SIDE_ERROR:  # pragma: no cover - depends on optional UI extra
    _UI_IMPORT_ERROR = _PY_SIDE_ERROR

    def launch_ui(
        camera_index: int = 0,
        midi_port: str | None = None,
        output_mode: str = "synth",
        progression_name: str = "pop",
        scale_name: str = "major",
        sound_program: int = 0,
    ) -> int:
        raise RuntimeError(
            "Install the [ui] extra to use the desktop performer UI"
        ) from _UI_IMPORT_ERROR

else:
    from handmusic.ui.expression_playground import ExpressionPlayground
    from handmusic.ui.theme import COLORS, METRICS, apply_theme
    from handmusic.ui.widgets import (
        MetricTile,
        NavButton,
        NeonPanel,
        ParameterKnob,
        SectionTitle,
        style_compact_field,
    )

    class SessionWorker(QThread):
        state_changed = Signal(str)
        telemetry_updated = Signal(object)
        failed = Signal(str)
        frame_ready = Signal(object)
        camera_health = Signal(str)
        midi_health = Signal(str)
        audio_health = Signal(str)
        performance_state = Signal(str)
        expression_updated = Signal(object)
        transport_updated = Signal(object)
        camera_index_changed = Signal(int)

        def __init__(
            self,
            camera_index: int,
            output_mode: str,
            midi_port: str | None,
            progression_name: str = "pop",
            scale_name: str = "major",
            sound_program: int = 0,
            sound_patch: Preset | None = None,
            master_gain: float = 0.75,
            brightness: float = 0.5,
        ) -> None:
            super().__init__()
            self.camera_index = camera_index
            self.output_mode = output_mode
            self.midi_port = midi_port
            self.progression_name = progression_name
            self.scale_name = scale_name
            self.sound_program = sound_program
            self.sound_patch = sound_patch or get_preset(sound_program)
            self.master_gain = master_gain
            self.brightness = brightness
            self.stop_event = Event()
            self.runtime: Any | None = None
            self.output_target: Any | None = None
            self._camera_started = False
            self._commands: Queue[tuple[str, object | None]] = Queue(maxsize=32)
            self._patch_lock = Lock()
            self._pending_patch: tuple[int | None, Preset, float, float] | None = None

        def request_stop(self) -> None:
            self.stop_event.set()

        def _publish_telemetry(self, snapshot: TelemetrySnapshot) -> None:
            self._drain_runtime_commands()
            drain_reports = getattr(self.output_target, "drain_callback_reports", None)
            if drain_reports is not None:
                for report in drain_reports():
                    self.audio_health.emit(str(report))
            self.telemetry_updated.emit(snapshot.as_dict())

        def _publish_frame(self, frame: object) -> None:
            if not self._camera_started:
                self._camera_started = True
                self.state_changed.emit("Running")
            self.camera_health.emit("Camera: running")
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
            self._queue_command("toggle_recording")

        def toggle_playback(self) -> None:
            self._queue_command("toggle_playback")

        def clear_loop(self) -> None:
            self._queue_command("clear_loop")

        def toggle_sustain(self) -> None:
            self._queue_command("toggle_sustain")

        def panic(self) -> None:
            self._queue_command("panic")

        def select_sound(self, program: int) -> None:
            patch = get_preset(program)
            with self._patch_lock:
                self._pending_patch = (
                    program,
                    patch,
                    self.master_gain,
                    self.brightness,
                )

        def apply_sound_patch(
            self,
            preset: Preset,
            *,
            master_gain: float,
            brightness: float,
        ) -> None:
            """Queue the newest complete patch snapshot for the worker thread."""
            preset.validate()
            with self._patch_lock:
                pending_program = (
                    self._pending_patch[0] if self._pending_patch is not None else None
                )
                self._pending_patch = (
                    pending_program,
                    preset,
                    master_gain,
                    brightness,
                )

        def _apply_sound_patch_now(
            self,
            preset: Preset,
            *,
            master_gain: float,
            brightness: float,
        ) -> None:
            self.sound_patch = preset
            self.master_gain = master_gain
            self.brightness = brightness
            target = self.output_target
            apply_patch = getattr(target, "apply_sound_patch", None)
            if apply_patch is not None:
                apply_patch(
                    preset,
                    master_gain=master_gain,
                    brightness=brightness,
                )

        def _queue_command(self, command: str) -> None:
            try:
                self._commands.put_nowait((command, None))
            except Full:
                self.stop_event.set()
                self.failed.emit(
                    "Control queue overflow; the session was stopped to preserve note safety."
                )

        def _drain_runtime_commands(self) -> None:
            runtime = self.runtime
            if runtime is None:
                return
            with self._patch_lock:
                pending_patch = self._pending_patch
                self._pending_patch = None
            if pending_patch is not None:
                program, patch, master_gain, brightness = pending_patch
                if program is not None:
                    self.sound_program = program
                    runtime.select_sound(program)
                self._apply_sound_patch_now(
                    patch,
                    master_gain=master_gain,
                    brightness=brightness,
                )
                self._publish_state(runtime.status_label)
            while True:
                try:
                    command, _payload = self._commands.get_nowait()
                except Empty:
                    break
                if command == "toggle_recording":
                    self._publish_transport(runtime.toggle_recording())
                elif command == "toggle_playback":
                    self._publish_transport(runtime.toggle_playback())
                elif command == "clear_loop":
                    self._publish_transport(runtime.clear_loop())
                elif command == "toggle_sustain":
                    runtime.notes.set_sustain(not runtime.notes.sustain_enabled)
                    self._publish_state(runtime.status_label)
                elif command == "panic":
                    runtime.stop_for_tracking_loss()
                    self._publish_state(runtime.status_label)

        def run(self) -> None:  # pragma: no cover - requires a desktop and camera
            runtime = None
            telemetry = PerformanceTelemetry()
            error_message: str | None = None
            try:
                if self.output_mode == "synth":
                    self.state_changed.emit("Starting built-in audio engine...")
                    output: Any = BuiltinSynthOutput(self.sound_program)
                    self.midi_health.emit("Audio: built-in 120-sound synth")
                    self.audio_health.emit("Built-in synth ready")
                elif self.output_mode == "midi":
                    self.state_changed.emit("Connecting MIDI...")
                    output = MidoOutput(self.midi_port)
                    self.midi_health.emit(f"MIDI: connected ({self.midi_port or 'default'})")
                elif self.output_mode == "plugin":
                    self.state_changed.emit("Connecting VST3 bridge...")
                    output = PluginBridgeOutput()
                    self.midi_health.emit("VST3 bridge: localhost:18736")
                else:
                    self.state_changed.emit("Starting camera...")
                    output = MemoryMidiOutput()
                    self.midi_health.emit("Audio: null output")
                self.output_target = output
                runtime, _ = default_runtime(
                    output,
                    progression_name=self.progression_name,
                    scale_name=self.scale_name,
                )
                self.runtime = runtime
                runtime.select_sound(self.sound_program)
                self._apply_sound_patch_now(
                    self.sound_patch,
                    master_gain=self.master_gain,
                    brightness=self.brightness,
                )
                self._publish_state(runtime.status_label)
                self.state_changed.emit("Opening camera...")
                self.camera_health.emit(f"Camera {self.camera_index}: opening...")
                camera_kwargs = {
                    "telemetry": telemetry,
                    "stop_event": self.stop_event,
                    "telemetry_callback": self._publish_telemetry,
                    "frame_callback": self._publish_frame,
                    "state_callback": self._publish_state,
                    "expression_callback": self._publish_expression,
                    "transport_callback": self._publish_transport,
                    "display": False,
                }
                try:
                    run_camera(runtime, self.camera_index, **camera_kwargs)
                except RuntimeError as exc:
                    if self.stop_event.is_set():
                        return
                    if self.camera_index == 0 or "Could not read camera" not in str(exc):
                        raise
                    self.camera_health.emit(
                        f"Camera {self.camera_index} unavailable; retrying camera 0..."
                    )
                    self.camera_index_changed.emit(0)
                    run_camera(runtime, 0, **camera_kwargs)
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                self.camera_health.emit("Camera: error")
                self.failed.emit(error_message)
            finally:
                if runtime is not None:
                    runtime.close()
                self.runtime = None
                self.output_target = None
                self.telemetry_updated.emit(telemetry.snapshot().as_dict())
                if error_message is None:
                    self.camera_health.emit("Camera: stopped")
                    self.state_changed.emit("Stopped")

    class PerformerWindow(QMainWindow):
        def __init__(
            self,
            camera_index: int = 0,
            midi_port: str | None = None,
            output_mode: str = "synth",
            progression_name: str = "pop",
            scale_name: str = "major",
            sound_program: int = 0,
            *,
            preset_directory: str | Path | None = None,
        ) -> None:
            super().__init__()
            self.setWindowTitle("SammyBlaze.wav Performer")
            self.setMinimumSize(1100, 700)
            available = QApplication.primaryScreen().availableGeometry()
            self.resize(
                min(1500, max(1100, available.width() - 40)),
                min(940, max(700, available.height() - 40)),
            )
            self.worker: SessionWorker | None = None
            self._preferred_camera_index = camera_index
            self._preferred_output_mode = output_mode
            self._preferred_midi_port = midi_port
            self._preferred_progression = progression_name
            self._preferred_scale = scale_name
            self._preferred_sound_program = sound_program
            self._preset_directory = preset_directory
            self._last_frame: QImage | None = None
            self._loading_patch = False
            self._session_running = False
            self._current_patch = get_preset(sound_program)
            self._master_gain = 0.75
            self._brightness = 0.5
            self._parameter_knobs: dict[str, ParameterKnob] = {}

            self._patch_timer = QTimer(self)
            self._patch_timer.setSingleShot(True)
            self._patch_timer.setInterval(35)
            self._patch_timer.timeout.connect(self._apply_live_patch)

            root = QWidget(self)
            root.setObjectName("appRoot")
            root.setProperty("appRoot", True)
            root_layout = QHBoxLayout(root)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)
            root_layout.addWidget(self._build_sidebar())

            body = QWidget(root)
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(
                METRICS.spacing_xl,
                METRICS.spacing_lg,
                METRICS.spacing_xl,
                METRICS.spacing_lg,
            )
            body_layout.setSpacing(METRICS.spacing_md)
            body_layout.addWidget(self._build_header())
            body_layout.addWidget(self._build_router())

            self.pages = QStackedWidget(body)
            self.pages.addWidget(self._build_perform_page())
            self.pages.addWidget(self._build_sound_lab_page())
            self.pages.addWidget(self._build_midi_page())
            self.pages.addWidget(self._build_settings_page())
            body_layout.addWidget(self.pages, 1)
            root_layout.addWidget(body, 1)

            self.setCentralWidget(root)
            apply_theme(self)
            self.output.currentIndexChanged.connect(self._update_port_enabled)
            self.sound_category.currentIndexChanged.connect(self.refresh_sounds)
            self.sound.currentIndexChanged.connect(self.select_sound)
            self.waveform_a.currentIndexChanged.connect(self._patch_combo_changed)
            self.waveform_b.currentIndexChanged.connect(self._patch_combo_changed)
            self.filter_type.currentIndexChanged.connect(self._patch_combo_changed)
            self.user_presets.currentIndexChanged.connect(self._user_preset_selected)
            self.refresh_sounds()
            self.refresh_ports()
            self.refresh_user_presets()
            self._load_patch_into_controls(self._current_patch)
            self._show_page(0)

        def _build_sidebar(self) -> QWidget:
            sidebar = QFrame(self)
            sidebar.setFixedWidth(92)
            sidebar.setStyleSheet(
                f"background: {COLORS.background_alt}; "
                f"border-right: 1px solid {COLORS.panel_border};"
            )
            layout = QVBoxLayout(sidebar)
            layout.setContentsMargins(0, 14, 0, 14)
            layout.setSpacing(4)
            logo = QLabel("SB", sidebar)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setStyleSheet(
                f"color: {COLORS.accent_bright}; font-size: 27px; font-weight: 300; padding: 14px;"
            )
            layout.addWidget(logo)

            self.nav_group = QButtonGroup(self)
            self.nav_group.setExclusive(True)
            self.nav_buttons: list[NavButton] = []
            for index, (label, glyph) in enumerate(
                (
                    ("Perform", "◉"),
                    ("Sound Lab", "◌"),
                    ("MIDI", "▥"),
                    ("Settings", "⚙"),
                )
            ):
                button = NavButton(label, sidebar, glyph=glyph)
                button.clicked.connect(lambda _checked=False, page=index: self._show_page(page))
                self.nav_group.addButton(button, index)
                self.nav_buttons.append(button)
                layout.addWidget(button)
            layout.addStretch(1)
            self.cpu_sidebar = QLabel("CPU  —\nRAM  —", sidebar)
            self.cpu_sidebar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cpu_sidebar.setStyleSheet(
                f"color: {COLORS.accent}; font-family: Consolas; font-size: 10px;"
            )
            layout.addWidget(self.cpu_sidebar)
            return sidebar

        def _build_header(self) -> QWidget:
            header = QWidget(self)
            layout = QHBoxLayout(header)
            layout.setContentsMargins(0, 0, 0, 0)
            brand = QLabel(
                "SAMMYBLAZE\n<span style='letter-spacing:3px'>PERFORMER</span>",
                header,
            )
            brand.setTextFormat(Qt.TextFormat.RichText)
            brand.setStyleSheet("font-size: 18px; font-weight: 700; line-height: 90%;")
            layout.addWidget(brand)
            version = QLabel(f"v{__version__}", header)
            version.setStyleSheet(f"color: {COLORS.accent}; font-weight: 700;")
            layout.addWidget(version)
            layout.addStretch(1)
            self.camera_badge = QLabel("●  CAMERA  IDLE", header)
            self.camera_badge.setStyleSheet(
                f"color: {COLORS.text_secondary}; border: 1px solid "
                f"{COLORS.panel_border}; border-radius: 8px; padding: 10px 16px;"
            )
            layout.addWidget(self.camera_badge)
            return header

        def _field(self, title: str, widget: QWidget) -> QWidget:
            container = QWidget(self)
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            label = QLabel(title.upper(), container)
            label.setStyleSheet(
                f"color: {COLORS.text_secondary}; font-size: 10px; letter-spacing: 1px;"
            )
            layout.addWidget(label)
            layout.addWidget(widget)
            return container

        def _build_router(self) -> QWidget:
            panel = NeonPanel(self, accent=True)
            grid = QGridLayout(panel)
            grid.setContentsMargins(14, 10, 14, 10)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)

            self.camera = style_compact_field(QSpinBox(panel))
            self.camera.setRange(0, 9)
            self.camera.setValue(self._preferred_camera_index)

            self.output = style_compact_field(QComboBox(panel))
            self.output.addItem("Built-in synth (120 sounds)", "synth")
            self.output.addItem("MIDI", "midi")
            self.output.addItem("FL Studio / VST3 bridge", "plugin")
            self.output.addItem("Null output", "null")
            requested_mode = (
                "synth"
                if self._preferred_output_mode not in {"synth", "midi", "plugin", "null"}
                else self._preferred_output_mode
            )
            self.output.setCurrentIndex(self.output.findData(requested_mode))

            self.midi_port = style_compact_field(QComboBox(panel))
            self.progression = style_compact_field(QComboBox(panel))
            for name in progression_names():
                self.progression.addItem(name.replace("_", " ").title(), name)
            index = self.progression.findData(self._preferred_progression)
            self.progression.setCurrentIndex(max(index, 0))

            self.scale = style_compact_field(QComboBox(panel))
            for name in scale_names():
                self.scale.addItem(name.replace("_", " ").title(), name)
            index = self.scale.findData(self._preferred_scale)
            self.scale.setCurrentIndex(max(index, 0))

            self.sound_category = style_compact_field(QComboBox(panel))
            for category in category_names():
                self.sound_category.addItem(category.replace("_", " ").title(), category)
            preferred = get_preset(self._preferred_sound_program)
            self.sound_category.setCurrentIndex(
                max(self.sound_category.findData(preferred.category), 0)
            )
            self.sound = style_compact_field(QComboBox(panel))

            fields = (
                ("Camera index", self.camera),
                ("Output", self.output),
                ("MIDI output", self.midi_port),
                ("Chord sequence", self.progression),
                ("Lead mode", self.scale),
                ("Sound category", self.sound_category),
                ("Factory sound", self.sound),
            )
            for widget in (
                self.output,
                self.midi_port,
                self.progression,
                self.scale,
                self.sound_category,
                self.sound,
            ):
                widget.setSizeAdjustPolicy(
                    QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
                )
                widget.setMinimumContentsLength(12)
                widget.setMinimumWidth(0)
                widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
            for position, (title, widget) in enumerate(fields):
                grid.addWidget(self._field(title, widget), position // 4, position % 4)
            self.refresh_button = QPushButton("REFRESH MIDI", panel)
            self.refresh_button.clicked.connect(self.refresh_ports)
            grid.addWidget(self.refresh_button, 1, 3)
            for column in range(4):
                grid.setColumnStretch(column, 1)
            return panel

        def _build_perform_page(self) -> QWidget:
            page = QWidget(self)
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)

            visual = QHBoxLayout()
            camera_panel = NeonPanel(page, accent=True)
            camera_layout = QVBoxLayout(camera_panel)
            camera_title = QHBoxLayout()
            camera_title.addWidget(SectionTitle("Live vision", camera_panel, accent=True))
            camera_title.addStretch(1)
            self.arm_badge = QLabel("DISARMED", camera_panel)
            self.arm_badge.setStyleSheet(f"color: {COLORS.danger}; font-weight: 700;")
            camera_title.addWidget(self.arm_badge)
            camera_layout.addLayout(camera_title)
            self.video = QLabel("CAMERA PREVIEW IDLE", camera_panel)
            self.video.setMinimumSize(520, 260)
            self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.video.setStyleSheet(
                f"background-color: #020507; color: {COLORS.text_muted}; "
                f"border: 1px solid {COLORS.panel_border_soft}; border-radius: 7px;"
            )
            camera_layout.addWidget(self.video, 1)
            camera_footer = QHBoxLayout()
            self.camera_health = QLabel("●  Camera: idle", camera_panel)
            self.camera_health.setStyleSheet(f"color: {COLORS.text_secondary};")
            camera_footer.addWidget(self.camera_health)
            camera_footer.addStretch(1)
            self.fps_overlay = QLabel("FPS 0.0", camera_panel)
            camera_footer.addWidget(self.fps_overlay)
            camera_layout.addLayout(camera_footer)
            visual.addWidget(camera_panel, 11)

            expression_panel = NeonPanel(page)
            expression_layout = QVBoxLayout(expression_panel)
            expression_layout.addWidget(SectionTitle("3D Expression Playground"))
            self.expression_playground = ExpressionPlayground(expression_panel)
            expression_layout.addWidget(self.expression_playground, 1)
            visual.addWidget(expression_panel, 9)
            layout.addLayout(visual, 1)

            guide = NeonPanel(page)
            guide_layout = QHBoxLayout(guide)
            guide_layout.setContentsMargins(14, 8, 14, 8)
            hand = QLabel("🖐", guide)
            hand.setStyleSheet(f"color: {COLORS.accent}; font-size: 28px;")
            guide_layout.addWidget(hand)
            self.instructions = QLabel(
                "LEFT HAND  chord shapes I–vii · hold to latch · fist panic · pinch changes "
                "mode     |     RIGHT HAND  X notes · Y dynamics · Z timbre/depth · motion "
                "vibrato · pinch re-articulates",
                guide,
            )
            self.instructions.setWordWrap(True)
            self.instructions.setStyleSheet(f"color: {COLORS.text_secondary};")
            guide_layout.addWidget(self.instructions, 1)
            layout.addWidget(guide)

            metric_row = QHBoxLayout()
            self.metric_audio = MetricTile("Audio", "120-sound synth", parent=page)
            self.metric_sound = MetricTile("Sound", self._current_patch.name, parent=page)
            self.metric_mode = MetricTile("Lead mode", "C Ionian", parent=page)
            self.metric_frames = MetricTile("Frames", "0", parent=page)
            self.metric_dropped = MetricTile("Dropped", "0", parent=page)
            self.metric_age = MetricTile("Frame age p95", "0.0 ms", parent=page)
            self.metric_latency = MetricTile("Gesture p95", "0.0 ms", parent=page)
            for tile in (
                self.metric_audio,
                self.metric_sound,
                self.metric_mode,
                self.metric_frames,
                self.metric_dropped,
                self.metric_age,
                self.metric_latency,
            ):
                metric_row.addWidget(tile)
            layout.addLayout(metric_row)

            transport = QHBoxLayout()
            self.record_button = self._transport_button("●  REC LOOP", self.toggle_recording)
            self.play_button = self._transport_button("▷  PLAY LOOP", self.toggle_playback)
            self.clear_button = self._transport_button("⌫  CLEAR LOOP", self.clear_loop)
            self.pedal_button = self._transport_button("♧  SUSTAIN PEDAL", self.toggle_sustain)
            self.pedal_button.setCheckable(True)
            self.panic_button = self._transport_button("⚠  PANIC", self.panic)
            self.panic_button.setProperty("variant", "danger")
            for button in (
                self.record_button,
                self.play_button,
                self.clear_button,
                self.pedal_button,
                self.panic_button,
            ):
                transport.addWidget(button)
            layout.addLayout(transport)

            bottom = NeonPanel(page)
            bottom_layout = QHBoxLayout(bottom)
            self.transport_state = QLabel("Loop: ready ●  |  0 events  |  0.00 seconds", bottom)
            self.transport_state.setStyleSheet(f"color: {COLORS.text_secondary};")
            bottom_layout.addWidget(self.transport_state, 2)
            self.start_button = QPushButton("START PERFORMER", bottom)
            self.start_button.setProperty("variant", "primary")
            self.start_button.clicked.connect(self.start_session)
            bottom_layout.addWidget(self.start_button, 3)
            self.stop_button = QPushButton("STOP", bottom)
            self.stop_button.clicked.connect(self.stop_session)
            self.stop_button.setEnabled(False)
            bottom_layout.addWidget(self.stop_button)
            layout.addWidget(bottom)
            return page

        def _build_sound_lab_page(self) -> QWidget:
            page = QWidget(self)
            outer = QVBoxLayout(page)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(10)

            preset_panel = NeonPanel(page, accent=True)
            preset_layout = QHBoxLayout(preset_panel)
            preset_layout.addWidget(SectionTitle("Sound Lab · User Presets", accent=True))
            self.user_presets = style_compact_field(QComboBox(preset_panel))
            self.user_presets.setMinimumWidth(240)
            preset_layout.addWidget(self.user_presets, 1)
            self.save_preset_button = QPushButton("SAVE AS", preset_panel)
            self.save_preset_button.clicked.connect(self.save_current_preset)
            preset_layout.addWidget(self.save_preset_button)
            self.delete_preset_button = QPushButton("DELETE", preset_panel)
            self.delete_preset_button.setProperty("variant", "danger")
            self.delete_preset_button.clicked.connect(self.delete_current_user_preset)
            preset_layout.addWidget(self.delete_preset_button)
            reset_button = QPushButton("RESET FACTORY", preset_panel)
            reset_button.clicked.connect(self.reset_factory_patch)
            preset_layout.addWidget(reset_button)
            outer.addWidget(preset_panel)

            self.patch_status = QLabel(
                "LIVE EDIT · changes are sent to standalone audio and the VST3 bridge",
                page,
            )
            self.patch_status.setStyleSheet(
                f"color: {COLORS.accent}; font-family: Consolas; font-size: 11px;"
            )
            outer.addWidget(self.patch_status)

            scroll = QScrollArea(page)
            scroll.setWidgetResizable(True)
            content = QWidget(scroll)
            lab = QVBoxLayout(content)
            lab.setContentsMargins(0, 0, 8, 0)
            lab.setSpacing(10)

            oscillator = self._parameter_panel(content, "Oscillators", "Dual-engine voice source")
            oscillator_layout = oscillator.layout()
            self.waveform_a = style_compact_field(QComboBox(oscillator))
            self.waveform_b = style_compact_field(QComboBox(oscillator))
            for waveform in sorted(WAVEFORMS):
                label = waveform.replace("_", " ").title()
                self.waveform_a.addItem(label, waveform)
                self.waveform_b.addItem(label, waveform)
            oscillator_layout.addWidget(self._field("Oscillator A", self.waveform_a))
            oscillator_layout.addWidget(self._field("Oscillator B", self.waveform_b))
            oscillator_layout.addWidget(self._knob("waveform_mix", "Osc Mix", 0, 100, 50, unit="%"))
            oscillator_layout.addWidget(
                self._knob("detune_cents", "Detune", 0, 100, 12, unit=" ct")
            )
            oscillator_layout.addWidget(self._knob("unison_voices", "Unison", 1, 16, 3, unit=" v"))
            lab.addWidget(oscillator)

            envelope = self._parameter_panel(content, "Amplifier Envelope", "Shape every note")
            envelope_layout = envelope.layout()
            envelope_layout.addWidget(self._knob("attack_ms", "Attack", 0, 20000, 10, unit=" ms"))
            envelope_layout.addWidget(self._knob("decay_ms", "Decay", 0, 20000, 250, unit=" ms"))
            envelope_layout.addWidget(self._knob("sustain", "Sustain", 0, 100, 75, unit="%"))
            envelope_layout.addWidget(
                self._knob("release_ms", "Release", 0, 30000, 600, unit=" ms")
            )
            lab.addWidget(envelope)

            filter_panel = self._parameter_panel(content, "Filter", "Moog-style tone shaping")
            filter_layout = filter_panel.layout()
            self.filter_type = style_compact_field(QComboBox(filter_panel))
            for filter_name in sorted(FILTER_TYPES):
                self.filter_type.addItem(
                    filter_name.replace("pass", "-pass").title(),
                    filter_name,
                )
            filter_layout.addWidget(self._field("Filter mode", self.filter_type))
            filter_layout.addWidget(
                self._knob("filter_cutoff_hz", "Cutoff", 20, 20000, 8000, unit=" Hz")
            )
            filter_layout.addWidget(
                self._knob("filter_resonance", "Resonance", 0, 100, 20, unit="%")
            )
            filter_layout.addWidget(
                self._knob("filter_envelope", "Envelope", -100, 100, 0, unit="%")
            )
            filter_layout.addWidget(self._knob("brightness", "Brightness", 0, 100, 50, unit="%"))
            lab.addWidget(filter_panel)

            modulation = self._parameter_panel(
                content, "Modulation", "Movement-ready performance character"
            )
            modulation_layout = modulation.layout()
            modulation_layout.addWidget(
                self._knob(
                    "vibrato_rate_hz",
                    "Vibrato Rate",
                    0,
                    15,
                    5,
                    decimals=1,
                    unit=" Hz",
                )
            )
            modulation_layout.addWidget(
                self._knob(
                    "vibrato_depth_semitones",
                    "Vibrato Depth",
                    0,
                    2,
                    0.2,
                    decimals=2,
                    unit=" st",
                )
            )
            modulation_layout.addStretch(1)
            lab.addWidget(modulation)

            effects = self._parameter_panel(
                content, "Master & Effects", "One performance-ready control surface"
            )
            effects_layout = effects.layout()
            effects_layout.addWidget(self._knob("master_gain", "Volume", 0, 100, 75, unit="%"))
            effects_layout.addWidget(self._knob("reverb_mix", "Reverb", 0, 100, 15, unit="%"))
            effects_layout.addWidget(self._knob("delay_mix", "Delay", 0, 100, 10, unit="%"))
            effects_layout.addWidget(
                self._knob("delay_time_ms", "Delay Time", 1, 2500, 360, unit=" ms")
            )
            effects_layout.addWidget(self._knob("chorus_mix", "Chorus", 0, 100, 15, unit="%"))
            lab.addWidget(effects)
            lab.addStretch(1)
            scroll.setWidget(content)
            outer.addWidget(scroll, 1)
            return page

        def _build_midi_page(self) -> QWidget:
            page = QWidget(self)
            layout = QVBoxLayout(page)
            panel = NeonPanel(page, accent=True)
            panel_layout = QVBoxLayout(panel)
            panel_layout.addWidget(SectionTitle("MIDI & DAW Routing", accent=True))
            self.midi_health = QLabel("Audio: not connected", panel)
            self.midi_health.setStyleSheet(
                f"color: {COLORS.accent}; font-size: 20px; font-weight: 600;"
            )
            panel_layout.addWidget(self.midi_health)
            text = QLabel(
                "Standalone synth: audio is generated inside SammyBlaze.\n\n"
                "MIDI: routes chords, melody, sustain, expression, timbre and effects to "
                "the selected Windows MIDI output.\n\n"
                "FL Studio / VST3 bridge: load SammyBlaze.vst3 in your DAW, then choose "
                "the bridge output above. Sound Lab edits and gestures stream directly "
                "to the plug-in on localhost.",
                panel,
            )
            text.setWordWrap(True)
            text.setStyleSheet(f"color: {COLORS.text_secondary}; font-size: 14px;")
            panel_layout.addWidget(text)
            panel_layout.addStretch(1)
            layout.addWidget(panel)
            return page

        def _build_settings_page(self) -> QWidget:
            page = QWidget(self)
            layout = QVBoxLayout(page)
            panel = NeonPanel(page)
            panel_layout = QVBoxLayout(panel)
            panel_layout.addWidget(SectionTitle("Performance System"))
            self.status = QLabel("READY · choose a sound, then start the performer", panel)
            self.status.setWordWrap(True)
            self.status.setStyleSheet(
                f"color: {COLORS.accent_bright}; font-size: 22px; font-weight: 500;"
            )
            panel_layout.addWidget(self.status)
            self.performance_state = QLabel(
                "Mode: chord + scale | Chord latch: ready | Pedal: off | Scale: Major",
                panel,
            )
            self.performance_state.setWordWrap(True)
            panel_layout.addWidget(self.performance_state)
            self.telemetry = QLabel("No performance telemetry yet", panel)
            self.telemetry.setWordWrap(True)
            self.telemetry.setStyleSheet(f"color: {COLORS.text_secondary}; font-family: Consolas;")
            panel_layout.addWidget(self.telemetry)
            panel_layout.addStretch(1)
            layout.addWidget(panel)
            return page

        def _parameter_panel(self, parent: QWidget, title: str, subtitle: str) -> NeonPanel:
            panel = NeonPanel(parent)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(16, 10, 16, 10)
            layout.setSpacing(10)
            title_box = QWidget(panel)
            title_box.setFixedWidth(155)
            title_layout = QVBoxLayout(title_box)
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.addWidget(SectionTitle(title, title_box, accent=True))
            description = QLabel(subtitle, title_box)
            description.setWordWrap(True)
            description.setStyleSheet(f"color: {COLORS.text_muted}; font-size: 10px;")
            title_layout.addWidget(description)
            title_layout.addStretch(1)
            layout.addWidget(title_box)
            return panel

        def _knob(
            self,
            key: str,
            label: str,
            minimum: float,
            maximum: float,
            value: float,
            *,
            decimals: int = 0,
            unit: str = "",
        ) -> ParameterKnob:
            knob = ParameterKnob(
                label,
                minimum=minimum,
                maximum=maximum,
                value=value,
                decimals=decimals,
                unit=unit,
            )
            knob.value_changed.connect(
                lambda changed, parameter=key: self._knob_changed(parameter, changed)
            )
            self._parameter_knobs[key] = knob
            return knob

        def _transport_button(self, text: str, callback: Any) -> QPushButton:
            button = QPushButton(text, self)
            button.clicked.connect(callback)
            button.setEnabled(False)
            return button

        def _show_page(self, index: int) -> None:
            self.pages.setCurrentIndex(index)
            for button_index, button in enumerate(self.nav_buttons):
                button.set_active(button_index == index)

        def refresh_sounds(self, _index: int = -1) -> None:
            selected = (
                self.sound.currentData() if self.sound.count() else self._preferred_sound_program
            )
            self.sound.blockSignals(True)
            self.sound.clear()
            for preset in presets_by_category(self.sound_category.currentData()):
                self.sound.addItem(preset.name, preset.program_id)
            index = self.sound.findData(selected)
            self.sound.setCurrentIndex(index if index >= 0 else 0)
            self.sound.blockSignals(False)
            self.select_sound()

        def select_sound(self, _index: int = -1) -> None:
            if self._loading_patch:
                return
            program = self.sound.currentData()
            if program is None:
                return
            preset = get_preset(int(program))
            self._current_patch = preset
            self._master_gain = 0.75
            self._brightness = 0.5
            self._load_patch_into_controls(preset)
            self.metric_sound.set_value(preset.name)
            self.status.setText(
                f"FACTORY SOUND {preset.program_id + 1}/120 · {preset.name.upper()} · "
                f"{preset.category.replace('_', ' ').upper()}"
            )
            self.patch_status.setText(f"FACTORY · {preset.name} · edit any control, then SAVE AS")
            if self.worker is not None and self.worker.isRunning():
                self.worker.select_sound(preset.program_id)
                self._apply_live_patch()

        def _load_patch_into_controls(
            self,
            preset: Preset,
            *,
            master_gain: float | None = None,
            brightness: float | None = None,
        ) -> None:
            self._loading_patch = True
            try:
                self.waveform_a.setCurrentIndex(max(self.waveform_a.findData(preset.waveform_a), 0))
                self.waveform_b.setCurrentIndex(max(self.waveform_b.findData(preset.waveform_b), 0))
                self.filter_type.setCurrentIndex(
                    max(self.filter_type.findData(preset.filter_type), 0)
                )
                values = {
                    "waveform_mix": preset.waveform_mix * 100,
                    "attack_ms": preset.attack_ms,
                    "decay_ms": preset.decay_ms,
                    "sustain": preset.sustain * 100,
                    "release_ms": preset.release_ms,
                    "filter_cutoff_hz": preset.filter_cutoff_hz,
                    "filter_resonance": preset.filter_resonance * 100,
                    "filter_envelope": preset.filter_envelope * 100,
                    "detune_cents": preset.detune_cents,
                    "unison_voices": preset.unison_voices,
                    "vibrato_rate_hz": preset.vibrato_rate_hz,
                    "vibrato_depth_semitones": preset.vibrato_depth_semitones,
                    "reverb_mix": preset.reverb_mix * 100,
                    "delay_mix": preset.delay_mix * 100,
                    "delay_time_ms": preset.delay_time_ms,
                    "chorus_mix": preset.chorus_mix * 100,
                    "master_gain": (self._master_gain if master_gain is None else master_gain)
                    * 100,
                    "brightness": (self._brightness if brightness is None else brightness) * 100,
                }
                for key, value in values.items():
                    self._parameter_knobs[key].set_value(value)
            finally:
                self._loading_patch = False

        def _patch_combo_changed(self, _index: int = -1) -> None:
            if self._loading_patch:
                return
            self._current_patch = replace(
                self._current_patch,
                waveform_a=str(self.waveform_a.currentData()),
                waveform_b=str(self.waveform_b.currentData()),
                filter_type=str(self.filter_type.currentData()),
            )
            self._mark_patch_edited()

        def _knob_changed(self, key: str, value: float) -> None:
            if self._loading_patch:
                return
            if key == "master_gain":
                self._master_gain = value / 100.0
            elif key == "brightness":
                self._brightness = value / 100.0
            else:
                normalized = (
                    value / 100.0
                    if key
                    in {
                        "waveform_mix",
                        "sustain",
                        "filter_resonance",
                        "filter_envelope",
                        "reverb_mix",
                        "delay_mix",
                        "chorus_mix",
                    }
                    else value
                )
                if key == "unison_voices":
                    normalized = int(round(value))
                self._current_patch = replace(self._current_patch, **{key: normalized})
            self._mark_patch_edited()

        def _mark_patch_edited(self) -> None:
            self.patch_status.setText(
                f"UNSAVED EDIT · {self._current_patch.name} · live engine update"
            )
            self._patch_timer.start()

        def _apply_live_patch(self) -> None:
            if self.worker is not None and self.worker.isRunning():
                self.worker.apply_sound_patch(
                    self._current_patch,
                    master_gain=self._master_gain,
                    brightness=self._brightness,
                )

        def refresh_user_presets(self, selected: str | None = None) -> None:
            self.user_presets.blockSignals(True)
            self.user_presets.clear()
            self.user_presets.addItem("Choose a saved sound...", None)
            try:
                presets = list_user_presets(directory=self._preset_directory)
                for preset in presets:
                    self.user_presets.addItem(preset.custom_name, preset.custom_name)
            except Exception as exc:
                self.patch_status.setText(f"PRESET LIBRARY ERROR · {exc}")
            if selected is not None:
                index = self.user_presets.findData(selected)
                self.user_presets.setCurrentIndex(max(index, 0))
            self.user_presets.blockSignals(False)
            self.delete_preset_button.setEnabled(self.user_presets.currentData() is not None)

        def _user_preset_selected(self, _index: int = -1) -> None:
            selected = self.user_presets.currentData()
            self.delete_preset_button.setEnabled(selected is not None)
            if selected is None:
                return
            preset = next(
                (
                    item
                    for item in list_user_presets(directory=self._preset_directory)
                    if item.custom_name == selected
                ),
                None,
            )
            if preset is None:
                return
            self._current_patch = preset.patch
            self._master_gain = preset.master_gain
            self._brightness = preset.brightness
            self._select_factory_in_router(preset.source_factory_program_id)
            self._load_patch_into_controls(
                self._current_patch,
                master_gain=self._master_gain,
                brightness=self._brightness,
            )
            self.metric_sound.set_value(preset.custom_name)
            self.patch_status.setText(f"USER PRESET · {preset.custom_name} · LIVE")
            self._apply_live_patch()

        def _select_factory_in_router(self, program: int) -> None:
            factory = get_preset(program)
            self._loading_patch = True
            try:
                category_index = self.sound_category.findData(factory.category)
                self.sound_category.setCurrentIndex(max(category_index, 0))
                self.sound.clear()
                for preset in presets_by_category(factory.category):
                    self.sound.addItem(preset.name, preset.program_id)
                self.sound.setCurrentIndex(max(self.sound.findData(program), 0))
            finally:
                self._loading_patch = False
            if self.worker is not None and self.worker.isRunning():
                self.worker.select_sound(program)

        def save_current_preset(self, name: str | None = None) -> None:
            if isinstance(name, bool):
                name = None
            if name is None:
                name, accepted = QInputDialog.getText(
                    self,
                    "Save user sound",
                    "Preset name:",
                    text=f"{self._current_patch.name} Custom",
                )
                if not accepted:
                    return
            try:
                preset = UserPreset(
                    **asdict(self._current_patch),
                    source_factory_program_id=self._current_patch.program_id,
                    custom_name=name,
                    master_gain=self._master_gain,
                    brightness=self._brightness,
                )
                overwrite = any(
                    existing.custom_name.casefold() == preset.custom_name.casefold()
                    for existing in list_user_presets(directory=self._preset_directory)
                )
                if overwrite:
                    choice = QMessageBox.question(
                        self,
                        "Replace preset?",
                        f"Replace the saved preset “{preset.custom_name}”?",
                    )
                    if choice != QMessageBox.StandardButton.Yes:
                        return
                path = save_user_preset(
                    preset,
                    directory=self._preset_directory,
                    overwrite=overwrite,
                )
                self.refresh_user_presets(preset.custom_name)
                self.patch_status.setText(f"SAVED · {preset.custom_name} · {path.parent}")
            except Exception as exc:
                QMessageBox.critical(self, "Could not save preset", str(exc))

        def delete_current_user_preset(self) -> None:
            selected = self.user_presets.currentData()
            if selected is None:
                return
            choice = QMessageBox.question(
                self,
                "Delete preset?",
                f"Delete the saved preset “{selected}”?",
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
            try:
                delete_user_preset(selected, directory=self._preset_directory)
                self.refresh_user_presets()
                self.patch_status.setText(f"DELETED · {selected}")
            except Exception as exc:
                QMessageBox.critical(self, "Could not delete preset", str(exc))

        def reset_factory_patch(self) -> None:
            program = int(self.sound.currentData() or 0)
            self._current_patch = get_preset(program)
            self._master_gain = 0.75
            self._brightness = 0.5
            self._load_patch_into_controls(self._current_patch)
            self.metric_sound.set_value(self._current_patch.name)
            self.patch_status.setText(f"FACTORY RESET · {self._current_patch.name}")
            if self.worker is not None and self.worker.isRunning():
                self.worker.select_sound(program)
                self._apply_live_patch()

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
            self.midi_port.setEnabled(
                self.output.currentData() == "midi" and not self._session_running
            )

        def _set_controls_enabled(self, enabled: bool) -> None:
            self._session_running = not enabled
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
                output_mode=str(self.output.currentData()),
                midi_port=self.midi_port.currentData(),
                progression_name=str(self.progression.currentData()),
                scale_name=str(self.scale.currentData()),
                sound_program=self._current_patch.program_id,
                sound_patch=self._current_patch,
                master_gain=self._master_gain,
                brightness=self._brightness,
            )
            self.worker.state_changed.connect(self._set_status)
            self.worker.telemetry_updated.connect(self.update_telemetry)
            self.worker.failed.connect(self._set_failure)
            self.worker.frame_ready.connect(self.update_frame)
            self.worker.camera_health.connect(self._set_camera_health)
            self.worker.camera_index_changed.connect(self.camera.setValue)
            self.worker.midi_health.connect(self.midi_health.setText)
            self.worker.audio_health.connect(self._set_audio_health)
            self.worker.performance_state.connect(self._set_performance_state)
            self.worker.expression_updated.connect(self.expression_playground.update_state)
            self.worker.transport_updated.connect(self.update_transport)
            self.worker.finished.connect(lambda: self._set_controls_enabled(True))
            self._set_controls_enabled(False)
            self._set_status("Starting...")
            self.worker.start()

        def _set_status(self, text: str) -> None:
            self.status.setText(text)

        def _set_failure(self, text: str) -> None:
            self._set_status(text)
            self._set_camera_health(f"Session error: {text}")

        def _set_audio_health(self, text: str) -> None:
            lowered = text.lower()
            if "failed" in lowered or "non-finite" in lowered:
                label = "AUDIO ERROR"
                self._set_status(text)
            elif "underflow" in lowered or "overflow" in lowered:
                label = "AUDIO XRUN"
                self._set_status(text)
            else:
                label = "SYNTH READY"
            self.metric_audio.set_value(label)
            self.metric_audio.setToolTip(text)

        def _set_performance_state(self, text: str) -> None:
            self.performance_state.setText(text)
            armed = text.startswith("ARMED")
            self.arm_badge.setText("ARMED" if armed else "DISARMED")
            color = COLORS.success if armed else COLORS.danger
            self.arm_badge.setStyleSheet(f"color: {color}; font-weight: 700;")
            sustain_enabled = "Pedal: on" in text
            self.pedal_button.blockSignals(True)
            self.pedal_button.setChecked(sustain_enabled)
            self.pedal_button.blockSignals(False)

        def _camera_health_changed(self, text: str) -> None:
            active = "running" in text.lower() or "active" in text.lower()
            self.camera_badge.setText("●  CAMERA  ON" if active else "●  CAMERA  IDLE")
            color = COLORS.success if active else COLORS.text_secondary
            self.camera_badge.setStyleSheet(
                f"color: {color}; border: 1px solid {COLORS.panel_border}; "
                "border-radius: 8px; padding: 10px 16px;"
            )

        def _set_camera_health(self, text: str) -> None:
            self.camera_health.setText(text)
            self._camera_health_changed(text)

        def stop_session(self) -> None:
            if self.worker is not None and self.worker.isRunning():
                self._set_status("Stopping...")
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
            self.record_button.setText("■  STOP REC" if recording else "●  REC LOOP")
            self.play_button.setText("■  STOP LOOP" if playing else "▷  PLAY LOOP")
            mode = "recording" if recording else "playing" if playing else "ready"
            self.transport_state.setText(
                f"Loop: {mode} ●  |  {events} events  |  {length_ms / 1000.0:.2f} seconds"
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
                self._set_status(f"Video error: {exc}")

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
            frames = int(report.get("frames_seen", 0))
            dropped = int(report.get("dropped_frames", 0))
            fps = float(report.get("effective_fps", 0.0))
            age = float(report.get("p95_frame_age_ms", 0.0))
            latency = float(report.get("p95_gesture_latency_ms", 0.0))
            self.metric_frames.set_value(frames)
            self.metric_dropped.set_value(dropped)
            self.metric_age.set_value(f"{age:.1f} ms")
            self.metric_latency.set_value(f"{latency:.1f} ms")
            self.fps_overlay.setText(f"FPS {fps:.1f}")
            self.telemetry.setText(
                f"Frames {frames} · dropped {dropped} · FPS {fps:.1f}\n"
                f"Frame age p95 {age:.1f} ms · gesture latency p95 {latency:.1f} ms"
            )

        def closeEvent(self, event: object) -> None:
            self.stop_session()
            if self.worker is not None and self.worker.isRunning():
                if not self.worker.wait(5000):
                    self._set_failure(
                        "Shutdown timed out; camera/audio cleanup is still running. "
                        "Wait a moment and close again."
                    )
                    event.ignore()
                    return
            event.accept()

    def launch_ui(
        camera_index: int = 0,
        midi_port: str | None = None,
        output_mode: str = "synth",
        progression_name: str = "pop",
        scale_name: str = "major",
        sound_program: int = 0,
    ) -> int:
        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("SammyBlaze.wav Performer")
        window = PerformerWindow(
            camera_index,
            midi_port,
            output_mode,
            progression_name,
            scale_name,
            sound_program,
        )
        window.show()
        return app.exec()


__all__ = ["PerformerWindow", "SessionWorker", "list_midi_output_ports", "launch_ui"]
