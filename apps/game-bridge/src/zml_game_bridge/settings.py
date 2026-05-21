from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

APP_DATA_DIR_NAME = "z-mining-log"


def get_documents_dir() -> Path:
    """Return the current user's Documents directory (handles folder redirection on Windows)."""
    p = _documents_via_known_folder()
    if p is not None:
        return p

    p = _documents_via_registry()
    if p is not None:
        return p

    # Fallback (may be wrong on redirected setups)
    return Path.home() / "Documents"


def find_entropia_chat_log() -> Path | None:
    """Locate Entropia Universe chat.log under Documents (redirect-safe)."""
    docs = get_documents_dir()
    candidate = docs / "Entropia Universe" / "chat.log"
    return candidate if candidate.exists() else None


def _documents_via_known_folder() -> Path | None:
    """Windows: SHGetKnownFolderPath(FOLDERID_Documents)."""
    try:
        import ctypes
        from uuid import UUID

        # FOLDERID_Documents
        folder_id = UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")

        # Signature: HRESULT SHGetKnownFolderPath(REFKNOWNFOLDERID, DWORD, HANDLE, PWSTR*)
        SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath  # type: ignore[attr-defined]
        SHGetKnownFolderPath.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        SHGetKnownFolderPath.restype = ctypes.c_long

        CoTaskMemFree = ctypes.windll.ole32.CoTaskMemFree  # type: ignore[attr-defined]
        CoTaskMemFree.argtypes = [ctypes.c_void_p]
        CoTaskMemFree.restype = None

        out_path = ctypes.c_wchar_p()
        hr = SHGetKnownFolderPath(folder_id.bytes_le, 0, None, ctypes.byref(out_path))
        if hr != 0 or not out_path.value:
            return None

        try:
            return Path(out_path.value)
        finally:
            CoTaskMemFree(out_path)
    except Exception:
        return None


def _documents_via_registry() -> Path | None:
    """Windows: HKCU\\...\\User Shell Folders\\Personal."""
    try:
        import os
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")  # 'Personal' == Documents
        if not isinstance(value, str) or not value:
            return None
        return Path(os.path.expandvars(value))
    except Exception:
        return None


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return Path(value)


def _default_db_path() -> Path:
    env_path = _env_path("ZML_DB_PATH")
    if env_path is not None:
        return env_path

    app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(app_data) / APP_DATA_DIR_NAME / "db" / "z-mining-log.sqlite3"


def _default_error_log_path() -> Path:
    env_path = _env_path("ZML_ERROR_LOG_PATH")
    if env_path is not None:
        return env_path

    app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(app_data) / APP_DATA_DIR_NAME / "logs" / "errors.log"


def _default_mining_resource_catalog_path() -> Path:
    env_path = _env_path("ZML_MINING_RESOURCE_CATALOG_PATH")
    if env_path is not None:
        return env_path

    app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(app_data) / APP_DATA_DIR_NAME / "config" / "mining_resources.json"


def _default_mining_tools_path() -> Path:
    env_path = _env_path("ZML_MINING_TOOLS_PATH")
    if env_path is not None:
        return env_path

    app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(app_data) / APP_DATA_DIR_NAME / "config" / "mining_tools.json"


def _default_chat_log_path() -> Path | None:
    env_path = _env_path("ZML_CHAT_LOG_PATH")
    if env_path is not None:
        return env_path

    detected_path = find_entropia_chat_log()
    if detected_path is not None:
        return detected_path

    return Path("testing/chat.log")


def _default_chat_start_at_end() -> bool:
    return _env_bool("ZML_CHAT_START_AT_END", default=True)


def _default_ocr_enabled() -> bool:
    return _env_bool("ZML_OCR_ENABLED", default=True)


def _default_mock_inputs_enabled() -> bool:
    return _env_bool("ZML_MOCK_INPUTS", default=False)


def _env_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _default_mock_mining_interval_ms() -> int:
    return _env_int("ZML_MOCK_MINING_INTERVAL_MS", default=3_000)


def configure_logging_from_env() -> None:
    logging_level = os.getenv("ZML_LOG_LEVEL", "INFO").strip().upper()
    log_format = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, logging_level, logging.INFO))
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    error_log_path = _default_error_log_path()
    error_log_path.parent.mkdir(parents=True, exist_ok=True)
    error_file_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(error_file_handler)

    _install_exception_hooks()


def _install_exception_hooks() -> None:
    def log_unhandled_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger(__name__).critical(
            "unhandled_runtime_exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        if args.exc_value is None:
            logging.getLogger(__name__).critical(
                "unhandled_thread_exception thread_name=%s exc_type=%s",
                args.thread.name if args.thread is not None else None,
                args.exc_type.__name__,
            )
            return
        logging.getLogger(__name__).critical(
            "unhandled_thread_exception thread_name=%s",
            args.thread.name if args.thread is not None else None,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_unhandled_exception
    threading.excepthook = log_thread_exception


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 17171
    reload: bool = False

    # Paths
    db_path: Path = field(default_factory=_default_db_path)
    chat_log_path: Path | None = field(default_factory=_default_chat_log_path)
    mining_resource_catalog_path: Path = field(
        default_factory=_default_mining_resource_catalog_path
    )
    mining_tools_path: Path = field(default_factory=_default_mining_tools_path)

    chat_start_at_end: bool = field(default_factory=_default_chat_start_at_end)
    ocr_enabled: bool = field(default_factory=_default_ocr_enabled)
    mock_inputs_enabled: bool = field(default_factory=_default_mock_inputs_enabled)
    mock_mining_interval_ms: int = field(default_factory=_default_mock_mining_interval_ms)
