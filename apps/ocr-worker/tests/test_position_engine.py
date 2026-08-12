from __future__ import annotations

from pathlib import Path

from zml_ocr_worker.pipelines.position.engine import TesserDigitsEngine


class _FakeApi:
    def __init__(self) -> None:
        self.variables: dict[str, str] = {}
        self.closed = False

    def SetVariable(self, name: str, value: str) -> None:
        self.variables[name] = value

    def End(self) -> None:
        self.closed = True


class _FakeTesserocr:
    class PSM:
        SINGLE_WORD = 8

    class OEM:
        LSTM_ONLY = 1

    def __init__(self) -> None:
        self.api = _FakeApi()
        self.created_psm: int | None = None

    def PyTessBaseAPI(
        self,
        *,
        path: str,
        lang: str,
        psm: int,
        oem: int,
    ) -> _FakeApi:
        assert Path(path).exists()
        assert lang == "eng"
        assert oem == self.OEM.LSTM_ONLY
        self.created_psm = psm
        return self.api


def test_digits_engine_uses_single_word_page_segmentation(tmp_path: Path) -> None:
    (tmp_path / "eng.traineddata").touch()
    tesserocr = _FakeTesserocr()

    engine = TesserDigitsEngine(
        tessdata_dir=str(tmp_path),
        tesserocr_module=tesserocr,
    )
    try:
        assert tesserocr.created_psm == tesserocr.PSM.SINGLE_WORD
        assert tesserocr.api.variables["tessedit_char_whitelist"] == "0123456789"
        assert tesserocr.api.variables["classify_bln_numeric_mode"] == "1"
    finally:
        engine.close()

    assert tesserocr.api.closed
