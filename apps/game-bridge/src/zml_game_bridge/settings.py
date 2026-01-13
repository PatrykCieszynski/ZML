from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Optional

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


def find_entropia_chat_log() -> Optional[Path]:
    """Locate Entropia Universe chat.log under Documents (redirect-safe)."""
    docs = get_documents_dir()
    candidate = docs / "Entropia Universe" / "chat.log"
    return candidate if candidate.exists() else None


def _documents_via_known_folder() -> Optional[Path]:
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


def _documents_via_registry() -> Optional[Path]:
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


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 17171
    reload: bool = True

    # Paths
    db_path: Path = Path(os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())) / "zabu-mining-log" / "db" / "zabu-mining-log.sqlite3"
    chat_log_path: Path | None = find_entropia_chat_log()


