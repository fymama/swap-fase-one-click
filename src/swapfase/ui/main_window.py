"""Guided, window-first interface for the local face-swap app."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Preview and controls; camera/model work is owned by the app controller."""

    frame_ready = Signal(object)
    load_photo_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    retry_requested = Signal()
    camera_scan_requested = Signal()
    device_changed = Signal(int)
    mirror_changed = Signal(bool)
    swap_changed = Signal(bool)
    virtual_camera_changed = Signal(bool)
    camera_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Swap-Fase")
        self.resize(900, 650)
        self._running = False
        self._setup_busy = False

        self._preview = QLabel("Starting local setup…")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(480, 320)
        self._preview.setStyleSheet(
            "background-color: #111; color: #ddd; font-size: 16px;"
        )

        self.status_label = QLabel("Preparing the local app…")
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)

        self.photo_label = QLabel("No target photo selected")
        self.load_button = QPushButton("Choose target photo…")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self.load_photo_requested.emit)

        self.device_combo = QComboBox()
        self.device_combo.addItem("Checking for cameras after setup…", None)
        self.device_combo.currentIndexChanged.connect(self._device_selected)
        self.rescan_button = QPushButton("Scan cameras")
        self.rescan_button.setEnabled(False)
        self.rescan_button.clicked.connect(self.camera_scan_requested.emit)

        self.start_button = QPushButton("Start")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.retry_button = QPushButton("Retry setup")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self.retry_requested.emit)

        self.mirror_check = QCheckBox("Mirror preview")
        self.mirror_check.setChecked(True)
        self.mirror_check.toggled.connect(self.mirror_changed.emit)
        self.swap_check = QCheckBox("Swap face")
        self.swap_check.setChecked(True)
        self.swap_check.toggled.connect(self.swap_changed.emit)
        self.virtual_camera_check = QCheckBox("Also output to virtual camera")
        self.virtual_camera_check.toggled.connect(self.virtual_camera_changed.emit)

        self.provider_label = QLabel("Provider: checking…")
        self.fps_label = QLabel("FPS: —")

        controls = QHBoxLayout()
        controls.addWidget(self.load_button)
        controls.addWidget(self.photo_label, 1)
        controls.addWidget(self.device_combo)
        controls.addWidget(self.rescan_button)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)

        toggles = QHBoxLayout()
        toggles.addWidget(self.mirror_check)
        toggles.addWidget(self.swap_check)
        toggles.addWidget(self.virtual_camera_check)
        toggles.addStretch(1)
        toggles.addWidget(self.provider_label)
        toggles.addWidget(self.fps_label)

        layout = QVBoxLayout()
        layout.addWidget(self._preview, 1)
        layout.addLayout(controls)
        layout.addLayout(toggles)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.retry_button)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)
        self.frame_ready.connect(self.on_frame)

    def _device_selected(self, index: int) -> None:
        device = self.device_combo.itemData(index)
        if device is not None:
            self.device_changed.emit(int(device))

    def set_status(self, message: str, busy: bool = False) -> None:
        self.status_label.setText(message)
        self.progress.setVisible(busy)

    def show_setup_progress(self, message: str) -> None:
        self._setup_busy = True
        self.set_status(message, busy=True)

    def set_setup_failed(self, message: str) -> None:
        self.set_status(message)
        self.retry_button.setVisible(True)
        self.retry_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._setup_busy = True

    def setup_thread_finished(self) -> None:
        self._setup_busy = False
        self.progress.hide()
        if self.retry_button.isVisible():
            self.retry_button.setEnabled(True)

    def set_ready(self, provider: str, devices: list[int]) -> None:
        self.retry_button.setVisible(False)
        self.progress.hide()
        self.provider_label.setText(f"Provider: {self._provider_text(provider)}")
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        if devices:
            for device in devices:
                self.device_combo.addItem(f"Camera {device}", device)
        else:
            self.device_combo.addItem("No camera found", None)
        self.device_combo.setEnabled(bool(devices))
        self.device_combo.blockSignals(False)
        if devices:
            self.device_changed.emit(devices[0])
            self.rescan_button.setText("Scan cameras")
            self.rescan_button.setEnabled(True)
        else:
            self.rescan_button.setText("Scan cameras")
            self.rescan_button.setEnabled(True)

    def set_camera_scan_state(self, devices: list[int] | None = None) -> None:
        if devices is None:
            self._setup_busy = True
            self.device_combo.blockSignals(True)
            self.device_combo.clear()
            self.device_combo.addItem("Searching for cameras…", None)
            self.device_combo.setEnabled(False)
            self.device_combo.blockSignals(False)
            self.rescan_button.setText("Scanning…")
            self.rescan_button.setEnabled(False)
            self.set_status("Scanning webcam devices…", busy=True)
            return

        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        if devices:
            for device in devices:
                self.device_combo.addItem(f"Camera {device}", device)
            self.device_combo.setEnabled(True)
            self.device_changed.emit(devices[0])
            self.set_status("Camera found. Choose a target photo, then press Start.")
        else:
            self._setup_busy = False
            self.device_combo.addItem("No camera found", None)
            self.device_combo.setEnabled(False)
            self.set_status(
                "No webcam detected. Connect/uncover it, allow camera access in "
                "Windows Settings > Privacy & security > Camera, close apps using it, "
                "then select Scan cameras."
            )
        self.device_combo.blockSignals(False)
        if devices:
            self._setup_busy = False
        self.rescan_button.setText("Scan cameras")
        self.rescan_button.setEnabled(True)

    @staticmethod
    def _provider_text(provider: str) -> str:
        if provider == "CPUExecutionProvider":
            return "CPU fallback (may be slow)"
        return provider.removesuffix("ExecutionProvider") or "unknown"

    def set_target(self, path: str) -> None:
        self.photo_label.setText(path)
        self.start_button.setEnabled(not self._running)

    def clear_target(self) -> None:
        self.photo_label.setText("No target photo selected")
        self.start_button.setEnabled(False)

    def set_running(self, running: bool) -> None:
        self._running = running
        self.start_button.setEnabled(
            not running and self.photo_label.text() != "No target photo selected"
        )
        self.stop_button.setEnabled(running)
        self.load_button.setEnabled(True)
        self.device_combo.setEnabled(not running and self.device_combo.count() > 0)
        self.rescan_button.setEnabled(not running and not self._setup_busy)
        self.virtual_camera_check.setEnabled(not running)

    def show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def choose_photo(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a clear, front-facing target photo",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        return path

    def update_status(self, provider: str, fps: float) -> None:
        self.provider_label.setText(f"Provider: {self._provider_text(provider)}")
        self.fps_label.setText(f"FPS: {fps:.1f}" if fps > 0 else "FPS: —")

    def on_frame(self, frame: np.ndarray) -> None:
        if frame is None:
            return
        rgb = np.ascontiguousarray(frame[:, :, ::-1])
        h, w = rgb.shape[:2]
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image.copy())
        self._preview.setPixmap(
            pixmap.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def closeEvent(self, event) -> None:
        if self._setup_busy:
            QMessageBox.information(
                self,
                "Setup is still running",
                "Wait for local model setup to finish before closing the app.",
            )
            event.ignore()
            return
        super().closeEvent(event)
