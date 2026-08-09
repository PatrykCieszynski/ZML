from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from zml_ocr_agent.pipelines.mining_finder import engine as engine_module


class _FakeApi:
    def __init__(self, text: str) -> None:
        self._text = text
        self.variables: dict[str, str] = {}
        self.page_seg_mode: int | None = None
        self.image_bytes: tuple[bytes, int, int, int, int] | None = None
        self.ended = False

    def SetVariable(self, key: str, value: str) -> None:
        self.variables[key] = value

    def SetPageSegMode(self, psm: int) -> None:
        self.page_seg_mode = psm

    def SetImageBytes(self, data: bytes, width: int, height: int, bpp: int, bpl: int) -> None:
        self.image_bytes = (data, width, height, bpp, bpl)

    def GetUTF8Text(self) -> str:
        return self._text

    def End(self) -> None:
        self.ended = True


class _FakeTesserocr(ModuleType):
    PSM: SimpleNamespace
    OEM: SimpleNamespace
    api_kwargs: dict[str, object]

    def __init__(self, api: _FakeApi) -> None:
        super().__init__("tesserocr")
        self._api = api
        self.PSM = SimpleNamespace(SINGLE_BLOCK=6)
        self.OEM = SimpleNamespace(LSTM_ONLY=1)
        self.api_kwargs = {}

    def PyTessBaseAPI(self, **kwargs: object) -> _FakeApi:
        self.api_kwargs = kwargs
        return self._api


def test_tesserocr_finder_text_engine_reuses_single_api_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_api = _FakeApi("UNIVERSAL AMMO\n1000")
    fake_tesserocr = _FakeTesserocr(fake_api)
    monkeypatch.setattr(engine_module, "get_tessdata_dir", lambda _path=None: tmp_path)

    engine = engine_module.TesserocrFinderTextEngine(tesserocr_module=fake_tesserocr)
    rgb = np.zeros((8, 12, 3), dtype=np.uint8)

    assert engine.recognize_text(rgb, psm=7) == "UNIVERSAL AMMO\n1000"
    assert engine.recognize_text(rgb, psm=8) == "UNIVERSAL AMMO\n1000"

    assert fake_tesserocr.api_kwargs == {
        "path": str(tmp_path),
        "lang": "eng",
        "psm": 6,
        "oem": 1,
    }
    assert fake_api.variables["user_defined_dpi"] == "300"
    assert fake_api.variables["load_system_dawg"] == "0"
    assert fake_api.variables["load_freq_dawg"] == "0"
    assert fake_api.page_seg_mode == 8
    assert fake_api.image_bytes is not None
    data, width, height, bpp, bpl = fake_api.image_bytes
    assert len(data) == width * height
    assert (width, height, bpp, bpl) == (12, 8, 1, 12)

    engine.close()
    assert fake_api.ended
