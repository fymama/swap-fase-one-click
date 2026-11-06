"""Window-first application entry point and local runtime controller."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from .bootstrap import MODELS_DIR, ensure_models
from .capture import (
    CameraBusyError,
    CaptureThread,
    list_capturable_devices,
)
from .engine import FaceEngine, NoFaceError
from .framebuffer import LatestFrameBuffer
from .pipeline import InferenceWorker
from .sink import DEFAULT_VCAM_DEVICE, PreviewSink, TeeSink, VirtualCamSink
from .state import AppState
from .ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class SetupUiBridge(QObject):
    """Deliver setup-thread results to the Qt main thread before touching widgets."""

    def __init__(
        self, window: MainWindow, ready_handler, camera_error_handler, parent: QObject
    ) -> None:
        super().__init__(parent)
        self._window = window
        self._ready_handler = ready_handler
        self._camera_error_handler = camera_error_handler

    @Slot(str)
    def show_progress(self, message: str) -> None:
        self._window.show_setup_progress(message)

    @Slot(object, object)
    def setup_ready(self, engine: FaceEngine, devices: list[int]) -> None:
        self._ready_handler(engine, devices)

    @Slot(str)
    def setup_failed(self, message: str) -> None:
        self._window.set_setup_failed(
            f"Setup failed: {message}\nCheck your connection and model files, then retry."
        )

    @Slot(str)
    def camera_error(self, message: str) -> None:
        self._camera_error_handler(message)

    @Slot(object)
    def cameras_scanned(self, devices: list[int]) -> None:
        self._window.set_camera_scan_state(devices)

    @Slot(str)
    def camera_scan_failed(self, message: str) -> None:
        self._window.set_camera_scan_state([])
        self._window.set_status(
            f"Camera scan failed: {message}. Close other apps using the webcam, then scan again."
        )


class SetupWorker(QThread):
    """Download/verify local models and initialize inference off the UI thread."""

    progress = Signal(str)
    ready = Signal(object, object)
    failed = Signal(str)

    def __init__(self, prefer_gpu: bool) -> None:
        super().__init__()
        self._prefer_gpu = prefer_gpu

    def run(self) -> None:
        try:
            inswapper_path = ensure_models(progress=self.progress.emit)
            self.progress.emit("Preparing the face-swap engine…")
            try:
                engine = FaceEngine(
                    model_root=MODELS_DIR,
                    inswapper_path=inswapper_path,
                    prefer_gpu=self._prefer_gpu,
                    det_size=(320, 320),
                )
            except Exception:
                if not self._prefer_gpu:
                    raise
                logger.exception("accelerated inference setup failed; retrying on CPU")
                self.progress.emit(
                    "The accelerator could not start. Retrying with CPU fallback…"
                )
                engine = FaceEngine(
                    model_root=MODELS_DIR,
                    inswapper_path=inswapper_path,
                    prefer_gpu=False,
                    det_size=(320, 320),
                )
            self.progress.emit("Checking available cameras…")
            devices = list_capturable_devices()
            self.ready.emit(engine, devices)
        except Exception as exc:
            logger.exception("local setup failed")
            self.failed.emit(str(exc))


class CameraScanWorker(QThread):
    """Re-scan webcam indices without freezing the window."""

    found = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.found.emit(list_capturable_devices())
        except Exception as exc:
            logger.exception("camera rescan failed")
            self.failed.emit(str(exc))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="swap-fase",
        description="Open the local face-swap app. A target photo can be selected in the window.",
    )
    parser.add_argument(
        "--target",
        help="optional target photo; if supplied, load it and start the preview on launch",
    )
    parser.add_argument("--device", type=int, help="camera index to use")
    parser.add_argument("--vcam", action="store_true", help="enable virtual-camera output")
    parser.add_argument(
        "--vcam-device",
        default=DEFAULT_VCAM_DEVICE,
        help="virtual-camera device (default is platform-specific)",
    )
    parser.add_argument(
        "--vcam-mirror",
        action="store_true",
        help="mirror the virtual-camera output as well as the preview",
    )
    parser.add_argument("--cpu", action="store_true", help="force CPU inference")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(argv)
    qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    state = AppState()
    buffer = LatestFrameBuffer()
    window = MainWindow()
    resources: dict[str, object | None] = {
        "engine": None,
        "capture": None,
        "worker": None,
        "vcam": None,
        "target": None,
        "setup": None,
        "bridge": None,
        "camera_scanner": None,
    }

    def stop_pipeline() -> None:
        state.running = False
        worker = resources["worker"]
        capture = resources["capture"]
        if worker is not None:
            worker.stop()
        if capture is not None:
            capture.stop()
        for thread in (worker, capture):
            if thread is not None:
                thread.join(timeout=5.0)
                if thread.is_alive():
                    vcam = resources["vcam"]
                    if vcam is not None:
                        vcam.close()
                    window.set_status(
                        "A processing thread is still stopping; wait before restarting."
                    )
                    return
        vcam = resources["vcam"]
        if vcam is not None:
            vcam.close()
        resources.update(capture=None, worker=None, vcam=None)
        window.set_running(False)
        provider, _ = state.status_snapshot()
        state.set_status(provider, 0.0)
        window.set_status("Stopped. The camera has been released.")

    def start_pipeline() -> None:
        engine = resources["engine"]
        if engine is None:
            window.set_status("Local setup is still in progress.")
            return
        if resources["target"] is None:
            window.show_error("Choose a photo", "Choose a target photo before starting.")
            return
        device_index = window.device_combo.currentData()
        if device_index is None:
            window.show_error(
                "Camera not found",
                "No webcam has been detected yet. Connect it, allow camera access in "
                "Windows Settings > Privacy & security > Camera, close apps using it, "
                "then select Scan cameras.",
            )
            return

        vcam = None
        capture = None
        try:
            if window.virtual_camera_check.isChecked():
                from .capture import _CAP_HEIGHT, _CAP_WIDTH

                vcam = VirtualCamSink(
                    device=args.vcam_device,
                    width=_CAP_WIDTH,
                    height=_CAP_HEIGHT,
                    fps=30.0,
                    mirror=args.vcam_mirror,
                )
                sink = TeeSink([PreviewSink(window.frame_ready.emit), vcam])
            else:
                sink = PreviewSink(window.frame_ready.emit)

            state.device_index = int(device_index)
            state.running = True
            capture = CaptureThread(
                device_index=int(device_index),
                buffer=buffer,
                state=state,
                error_callback=window.camera_error.emit,
            )
            worker = InferenceWorker(engine=engine, buffer=buffer, sink=sink, state=state)
            resources.update(capture=capture, worker=worker, vcam=vcam)
            capture.start()
            worker.start()
        except (CameraBusyError, RuntimeError) as exc:
            state.running = False
            if capture is not None and capture.is_alive():
                capture.stop()
                capture.join(timeout=5.0)
            if vcam is not None:
                vcam.close()
            resources.update(capture=None, worker=None, vcam=None)
            window.set_running(False)
            window.show_error(
                "Could not start camera",
                f"{exc}\n\nClose other apps using the webcam and check virtual-camera setup.",
            )
            window.set_status("Could not start. Check the message above and retry.")
            return
        window.set_running(True)
        window.set_status(
            "Running locally. Virtual camera is on."
            if vcam is not None
            else "Running locally. Preview only; no virtual camera is active."
        )

    def load_photo() -> None:
        path = window.choose_photo()
        if not path:
            return
        engine = resources["engine"]
        if engine is None:
            window.show_error("Setup in progress", "Wait for local setup to finish.")
            return
        image = cv2.imread(path)
        if image is None:
            window.show_error(
                "Photo could not be opened",
                "Choose a valid PNG, JPEG, BMP, or WebP image.",
            )
            return
        try:
            face = engine.embed(image)
        except NoFaceError:
            window.show_error(
                "No face found",
                "Choose a clear, front-facing photo with one visible face and some space around the head.",
            )
            return
        except Exception as exc:
            logger.exception("target-photo analysis failed")
            window.show_error("Photo could not be analyzed", str(exc))
            return
        state.set_target(face)
        resources["target"] = path
        window.set_target(Path(path).name)
        window.set_status(
            "Target photo updated; it is active in the preview."
            if state.running
            else "Target photo is ready. Press Start to connect the camera."
        )

    def setup_ready(engine: FaceEngine, devices: list[int]) -> None:
        resources["engine"] = engine
        state.set_status(engine.provider, 0.0)
        window.set_ready(engine.provider, devices)
        window.load_button.setEnabled(True)
        window.set_camera_scan_state(devices)
        if devices:
            window.set_status(
                "Camera found. Choose a target photo, then press Start. "
                + ("CPU fallback may be slow." if not engine.using_gpu else "Accelerator ready.")
            )
        if args.device is not None and args.device in devices:
            index = window.device_combo.findData(args.device)
            if index >= 0:
                window.device_combo.setCurrentIndex(index)
        if args.vcam:
            window.virtual_camera_check.setChecked(True)
        if args.target:
            load_photo_from_path(args.target)

    def camera_failed(message: str) -> None:
        stop_pipeline()
        window.show_error("Camera stopped", message)

    def load_photo_from_path(path: str) -> None:
        engine = resources["engine"]
        if engine is None:
            return
        image = cv2.imread(path)
        if image is None:
            window.show_error("Photo could not be opened", f"Could not read: {path}")
            return
        try:
            face = engine.embed(image)
        except NoFaceError:
            window.show_error(
                "No face found",
                "Choose a clear, front-facing photo with one visible face.",
            )
            return
        except Exception as exc:
            logger.exception("command-line target-photo analysis failed")
            window.show_error("Photo could not be analyzed", str(exc))
            return
        state.set_target(face)
        resources["target"] = path
        window.set_target(Path(path).name)
        start_pipeline()

    def start_setup() -> None:
        window.retry_button.setVisible(False)
        window.retry_button.setEnabled(False)
        window.load_button.setEnabled(False)
        window.show_setup_progress("Preparing local models and the inference engine…")
        setup = SetupWorker(prefer_gpu=not args.cpu)
        resources["setup"] = setup
        bridge = resources["bridge"]
        setup.progress.connect(bridge.show_progress)
        setup.ready.connect(bridge.setup_ready)
        setup.failed.connect(bridge.setup_failed)
        setup.finished.connect(window.setup_thread_finished)
        setup.start()

    def scan_cameras() -> None:
        existing = resources["camera_scanner"]
        if existing is not None and existing.isRunning():
            return
        scanner = CameraScanWorker()
        resources["camera_scanner"] = scanner
        scanner.found.connect(bridge.cameras_scanned)
        scanner.failed.connect(bridge.camera_scan_failed)
        scanner.finished.connect(window.setup_thread_finished)
        window.set_camera_scan_state()
        scanner.start()

    bridge = SetupUiBridge(
        window,
        setup_ready,
        camera_failed,
        parent=window,
    )
    resources["bridge"] = bridge

    window.load_photo_requested.connect(load_photo)
    window.start_requested.connect(start_pipeline)
    window.stop_requested.connect(stop_pipeline)
    window.retry_requested.connect(start_setup)
    window.camera_scan_requested.connect(scan_cameras)
    window.mirror_changed.connect(state.set_mirror)
    window.swap_changed.connect(state.set_swap_enabled)
    window.device_changed.connect(lambda index: setattr(state, "device_index", index))
    window.virtual_camera_changed.connect(
        lambda enabled: window.set_status(
            "Virtual camera will start with the preview."
            if enabled
            else "Preview only; no virtual camera is active."
        )
        if resources["engine"] is not None
        else None
    )
    window.camera_error.connect(bridge.camera_error)

    timer = QTimer(window)
    timer.timeout.connect(
        lambda: window.update_status(*state.status_snapshot())
        if resources["engine"] is not None
        else None
    )
    timer.start(500)
    qt_app.aboutToQuit.connect(stop_pipeline)
    window.show()
    start_setup()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
