"""Tests for model setup progress without downloading real model files."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swapfase import bootstrap  # noqa: E402


class _Response:
    headers = {"Content-Length": "4"}

    def __init__(self) -> None:
        self._chunks = iter((b"ab", b"cd", b""))

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return next(self._chunks)


class BootstrapProgressTests(unittest.TestCase):
    def test_download_reports_percent_and_writes_complete_file(self) -> None:
        messages: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            destination = str(Path(directory) / "model.onnx")
            with patch.object(bootstrap.urllib.request, "urlopen", return_value=_Response()):
                bootstrap._download("https://example.invalid/model", destination, messages.append)

            self.assertEqual(Path(destination).read_bytes(), b"abcd")
            self.assertEqual(messages, ["Downloading swap model: 50%", "Downloading swap model: 100%"])

    def test_existing_models_report_setup_stages(self) -> None:
        messages: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / bootstrap.INSWAPPER_FILENAME
            model_path.write_bytes(b"present")
            with (
                patch.object(bootstrap, "MODELS_DIR", directory),
                patch.object(bootstrap, "ensure_buffalo_l"),
                patch.object(bootstrap, "_verify_or_raise"),
            ):
                result = bootstrap.ensure_models(messages.append)

        self.assertEqual(result, str(model_path))
        self.assertEqual(
            messages,
            [
                "Checking face-analysis models…",
                "Verifying the local swap model…",
                "Models are ready.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
