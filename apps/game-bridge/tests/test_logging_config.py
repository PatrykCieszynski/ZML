from __future__ import annotations

import logging
from pathlib import Path

from zml_game_bridge.settings import configure_logging_from_env


def test_configure_logging_writes_errors_to_file(monkeypatch, tmp_path: Path) -> None:
    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level
    error_log_path = tmp_path / "logs" / "errors.log"
    monkeypatch.setenv("ZML_ERROR_LOG_PATH", str(error_log_path))
    monkeypatch.setenv("ZML_LOG_LEVEL", "INFO")

    try:
        configure_logging_from_env()
        logging.getLogger("test").info("info should stay out of the file")
        logging.getLogger("test").error("error should be persisted")

        for handler in root_logger.handlers:
            handler.flush()

        contents = error_log_path.read_text(encoding="utf-8")
        assert "error should be persisted" in contents
        assert "info should stay out of the file" not in contents
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers[:] = previous_handlers
        root_logger.setLevel(previous_level)
