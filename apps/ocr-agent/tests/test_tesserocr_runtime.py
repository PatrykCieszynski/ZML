from __future__ import annotations

import signal

from zml_ocr_agent import tesserocr_runtime


def test_main_thread_preload_restores_sigint_handler(monkeypatch) -> None:
    original_handler = signal.getsignal(signal.SIGINT)

    def uvicorn_handler(_signal_number, _frame) -> None:
        return

    def cysignals_handler(_signal_number, _frame) -> None:
        return

    sentinel = object()

    def fake_import_module(name: str):
        assert name == "tesserocr"
        signal.signal(signal.SIGINT, cysignals_handler)
        return sentinel

    try:
        signal.signal(signal.SIGINT, uvicorn_handler)
        monkeypatch.setattr(tesserocr_runtime.importlib, "import_module", fake_import_module)

        result = tesserocr_runtime.preload_tesserocr_preserving_sigint_handler()

        assert result is sentinel
        assert signal.getsignal(signal.SIGINT) is uvicorn_handler
    finally:
        if original_handler is not None:
            signal.signal(signal.SIGINT, original_handler)
