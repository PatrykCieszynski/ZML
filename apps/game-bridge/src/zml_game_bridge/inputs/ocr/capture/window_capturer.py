from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple, cast

import numpy as np
import win32gui
import win32ui
from ctypes import windll


PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002


def _find_window_by_title_contains(title_substr: str) -> int:
    found: list[int] = []

    def enum_cb(hwnd: int, _lparam: int) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title_substr in title:
            found.append(hwnd)

    win32gui.EnumWindows(enum_cb, 0)
    if not found:
        raise RuntimeError(f'Window not found (title contains): {title_substr!r}')
    return found[0]


@dataclass
class _GdiState:
    hwnd: int
    w: int
    h: int
    hwnd_dc: Any
    mfc_dc: Any
    save_dc: Any
    bitmap: Any


class WindowCapturer:
    def __init__(self, *, title_contains: str, flags: int = PW_CLIENTONLY | PW_RENDERFULLCONTENT) -> None:
        self._title_contains = title_contains
        self._flags = flags
        self._state: Optional[_GdiState] = None
        self._ensure_open()

    def close(self) -> None:
        st = self._state
        if st is None:
            return
        win32gui.DeleteObject(cast(int, st.bitmap.GetHandle()))
        st.save_dc.DeleteDC()
        st.mfc_dc.DeleteDC()
        win32gui.ReleaseDC(st.hwnd, cast(int, st.hwnd_dc))
        self._state = None

    def grab(self) -> np.ndarray:
        self._ensure_open()

        st = self._state
        assert st is not None

        # Recreate bitmap if size changed
        w, h = self._get_client_size(st.hwnd)

        if (w, h) != (st.w, st.h):
            self.close()
            self._ensure_open()
            st = self._state
            assert st is not None

        ok = windll.user32.PrintWindow(st.hwnd, st.save_dc.GetSafeHdc(), self._flags)
        if ok != 1:
            # Fallback: some apps hate FULLCONTENT; try client-only
            ok2 = windll.user32.PrintWindow(st.hwnd, st.save_dc.GetSafeHdc(), PW_CLIENTONLY)
            if ok2 != 1:
                raise RuntimeError(f"PrintWindow failed: {ok} / fallback {ok2}")

        bmpinfo = cast(dict, st.bitmap.GetInfo())
        bmpstr = cast(bytes, st.bitmap.GetBitmapBits(True))

        height = int(bmpinfo.get("bmHeight", 0))
        width = int(bmpinfo.get("bmWidth", 0))

        if width <= 0 or height <= 0:
            raise RuntimeError("Window has non-positive client size.")

        expected = width * height * 4
        if len(bmpstr) < expected:
            raise RuntimeError(f"Bitmap has non-positive size.: {len(bmpstr)} < {expected}")

        img = np.frombuffer(bmpstr, dtype=np.uint8).reshape((height, width, 4))
        # PrintWindow returns BGRA; drop alpha.
        return np.ascontiguousarray(img[:, :, :3])

    def _ensure_open(self) -> None:
        if self._state is not None:
            # Validate window handle
            if win32gui.IsWindow(self._state.hwnd):
                return
            self.close()

        hwnd = _find_window_by_title_contains(self._title_contains)
        w, h = self._get_client_size(hwnd)

        hwnd_dc: int = win32gui.GetWindowDC(hwnd)
        mfc_dc: Any = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc: Any = mfc_dc.CreateCompatibleDC()
        bitmap: Any = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bitmap)

        self._state = _GdiState(
            hwnd=hwnd,
            w=w,
            h=h,
            hwnd_dc=hwnd_dc,
            mfc_dc=mfc_dc,
            save_dc=save_dc,
            bitmap=bitmap,
        )

    @staticmethod
    def _get_client_size(hwnd: int) -> Tuple[int, int]:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        return right - left, bottom - top
