# ocr_tests.py
from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image

from zml_game_bridge.testing.OCR.preprocess import (
    PreprocessConfig,
    PreprocessVariant,
    preprocess_line,
)

_FILENAME_RE = re.compile(r"^(?P<id>.+)_(?P<expected>\d+)$")


@dataclass(frozen=True, slots=True)
class Sample:
    sample_id: str
    lon_path: Path
    lon_expected: int
    lat_path: Path
    lat_expected: int


@dataclass(frozen=True, slots=True)
class LineResult:
    sample_id: str
    kind: str  # "lon" or "lat"
    expected: int
    predicted: Optional[int]
    ok: bool
    ms_total: float


@dataclass(frozen=True, slots=True)
class PairResult:
    sample_id: str
    lon_ok: bool
    lat_ok: bool
    pair_ok: bool


def _parse_name(stem: str) -> Tuple[str, int]:
    """
    Parse "<sampleId>_<expected>" from the filename stem.
    """
    m = _FILENAME_RE.match(stem)
    if not m:
        raise ValueError(f"Invalid filename stem: {stem!r} (expected '<id>_<digits>')")
    return m.group("id"), int(m.group("expected"))


def _collect_samples(root: Path) -> List[Sample]:
    lon_dir = root / "lon"
    lat_dir = root / "lat"
    if not lon_dir.is_dir() or not lat_dir.is_dir():
        raise FileNotFoundError(f"Expected 'lon/' and 'lat/' folders under: {root}")

    lon_map: Dict[str, Tuple[Path, int]] = {}
    for p in sorted(lon_dir.glob("*.png")):
        sid, exp = _parse_name(p.stem)
        if sid in lon_map:
            raise ValueError(f"Duplicate lon sample_id={sid!r}: {lon_map[sid][0]} and {p}")
        lon_map[sid] = (p, exp)

    lat_map: Dict[str, Tuple[Path, int]] = {}
    for p in sorted(lat_dir.glob("*.png")):
        sid, exp = _parse_name(p.stem)
        if sid in lat_map:
            raise ValueError(f"Duplicate lat sample_id={sid!r}: {lat_map[sid][0]} and {p}")
        lat_map[sid] = (p, exp)

    sample_ids = sorted(set(lon_map.keys()) | set(lat_map.keys()))
    missing_lon = [sid for sid in sample_ids if sid not in lon_map]
    missing_lat = [sid for sid in sample_ids if sid not in lat_map]
    if missing_lon or missing_lat:
        raise ValueError(
            f"Missing pairs. Missing lon: {len(missing_lon)}; missing lat: {len(missing_lat)}"
        )

    samples: List[Sample] = []
    for sid in sample_ids:
        lon_path, lon_exp = lon_map[sid]
        lat_path, lat_exp = lat_map[sid]
        samples.append(
            Sample(
                sample_id=sid,
                lon_path=lon_path,
                lon_expected=lon_exp,
                lat_path=lat_path,
                lat_expected=lat_exp,
            )
        )
    return samples


def _read_gray(path: Path) -> np.ndarray:
    """
    Read as grayscale uint8.
    """
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def _digits_only(text: str) -> str:
    """
    Keep only [0-9] to avoid false positives from OCR artifacts.
    """
    return "".join(ch for ch in text if "0" <= ch <= "9")


def _sanity_int(x: int) -> bool:
    """
    Basic sanity check for EU coordinate-like integers.
    Adjust later if you need per-planet ranges.
    """
    return 1000 <= x <= 10_000_000


class OcrBackend:
    name: str

    def ocr_line(self, img_u8: np.ndarray) -> str:
        raise NotImplementedError


class PyTesseractBackend(OcrBackend):
    def __init__(self) -> None:
        self.name = "pytesseract"
        # Single line, digits only. Disable dictionary heuristics.
        self._config = (
            "--oem 1 --psm 7 "
            "-c tessedit_char_whitelist=0123456789 "
            "-c load_system_dawg=0 -c load_freq_dawg=0"
        )

    def ocr_line(self, img_u8: np.ndarray) -> str:
        return pytesseract.image_to_string(img_u8, config=self._config)


class TesserOcrBackend(OcrBackend):
    def __init__(self) -> None:
        self.name = "tesserocr"
        try:
            import tesserocr  # type: ignore
        except Exception as e:
            raise RuntimeError(f"tesserocr import failed: {e}") from e

        self._tesserocr = tesserocr
        self._api = tesserocr.PyTessBaseAPI(psm=tesserocr.PSM.SINGLE_LINE, oem=tesserocr.OEM.LSTM_ONLY, lang="eng")
        self._api.SetVariable("tessedit_char_whitelist", "0123456789")
        self._api.SetVariable("load_system_dawg", "0")
        self._api.SetVariable("load_freq_dawg", "0")
        # classify_bln_numeric_mode=1
        self._api.SetVariable("classify_bln_numeric_mode", "1")
        # user_defined_dpi=300
        self._api.SetVariable("user_defined_dpi", "300")
        self._api.SetVariable("tessedit_do_invert", "0")

    def ocr_line(self, img_u8: np.ndarray) -> str:
        # tesserocr expects RGB or grayscale; grayscale uint8 is fine.
        img_pil = Image.fromarray(img_u8)
        self._api.SetImage(img_pil)

        return self._api.GetUTF8Text() or ""

    def close(self) -> None:
        self._api.End()


def _run_one_line(
    *,
    backend: OcrBackend,
    cfg: PreprocessConfig,
    variant: PreprocessVariant,
    sample_id: str,
    kind: str,
    path: Path,
    expected: int,
) -> LineResult:
    t0 = time.perf_counter()

    img = _read_gray(path)
    pre = preprocess_line(img, variant=variant, cfg=cfg)
    raw_text = backend.ocr_line(pre)
    digits = _digits_only(raw_text)

    predicted: Optional[int]
    if digits == "":
        predicted = None
    else:
        try:
            predicted = int(digits)
        except ValueError:
            predicted = None

    if predicted is None or not _sanity_int(predicted):
        predicted = None

    ok = (predicted == expected)
    ms_total = (time.perf_counter() - t0) * 1000.0

    return LineResult(
        sample_id=sample_id,
        kind=kind,
        expected=expected,
        predicted=predicted,
        ok=ok,
        ms_total=ms_total,
    )


def _summarize(lines: List[LineResult], pairs: List[PairResult]) -> str:
    def _stats(kind: str) -> Tuple[int, int, int, float]:
        xs = [r for r in lines if r.kind == kind]
        total = len(xs)
        ok = sum(1 for r in xs if r.ok)
        none = sum(1 for r in xs if r.predicted is None)
        fp = sum(1 for r in xs if (r.predicted is not None and not r.ok))
        avg_ms = (sum(r.ms_total for r in xs) / total) if total else 0.0
        return ok, none, fp, avg_ms

    lon_ok, lon_none, lon_fp, lon_ms = _stats("lon")
    lat_ok, lat_none, lat_fp, lat_ms = _stats("lat")

    total_pairs = len(pairs)
    pair_ok = sum(1 for p in pairs if p.pair_ok)

    def pct(x: int, n: int) -> float:
        return (100.0 * x / n) if n else 0.0

    out = []
    out.append(f"Lon: ok={lon_ok}/{len(lines)//2} ({pct(lon_ok, len(lines)//2):.2f}%), "
               f"none={lon_none} ({pct(lon_none, len(lines)//2):.2f}%), "
               f"fp={lon_fp} ({pct(lon_fp, len(lines)//2):.2f}%), avg_ms={lon_ms:.2f}")
    out.append(f"Lat: ok={lat_ok}/{len(lines)//2} ({pct(lat_ok, len(lines)//2):.2f}%), "
               f"none={lat_none} ({pct(lat_none, len(lines)//2):.2f}%), "
               f"fp={lat_fp} ({pct(lat_fp, len(lines)//2):.2f}%), avg_ms={lat_ms:.2f}")
    out.append(f"Pair: ok={pair_ok}/{total_pairs} ({pct(pair_ok, total_pairs):.2f}%)")
    return "\n".join(out)


def _build_pairs(line_results: List[LineResult]) -> List[PairResult]:
    by_id: Dict[str, Dict[str, LineResult]] = {}
    for r in line_results:
        by_id.setdefault(r.sample_id, {})[r.kind] = r

    pairs: List[PairResult] = []
    for sid, m in sorted(by_id.items(), key=lambda kv: kv[0]):
        lon = m.get("lon")
        lat = m.get("lat")
        if lon is None or lat is None:
            continue
        pairs.append(
            PairResult(
                sample_id=sid,
                lon_ok=lon.ok,
                lat_ok=lat.ok,
                pair_ok=(lon.ok and lat.ok),
            )
        )
    return pairs


def _write_failures_csv(path: Path, results: List[LineResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sample_id", "kind", "expected", "predicted", "ok", "ms_total"])
        for r in results:
            if r.ok:
                continue
            w.writerow([r.sample_id, r.kind, r.expected, r.predicted, r.ok, f"{r.ms_total:.3f}"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="Dataset root with 'lon/' and 'lat/' folders")
    ap.add_argument("--out", type=Path, default=Path("out_ocr_tests"), help="Output folder for reports")
    ap.add_argument(
        "--variants",
        nargs="*",
        default=["p0_raw_upscale", "p3_tophat_otsu_cc"],
        help="Preprocess variants to run",
    )
    ap.add_argument(
        "--backends",
        nargs="*",
        default=["pytesseract", "tesserocr"],
        help="OCR backends to run (tesserocr is optional if installed)",
    )
    ap.add_argument("--limit", type=int, default=0, help="Limit samples (0 = all)")
    args = ap.parse_args()

    samples = _collect_samples(args.root)
    if args.limit and args.limit > 0:
        samples = samples[: args.limit]

    cfg = PreprocessConfig()

    requested_variants: List[PreprocessVariant] = []
    for v in args.variants:
        requested_variants.append(v)  # type: ignore[arg-type]

    backends: List[OcrBackend] = []
    for b in args.backends:
        if b == "pytesseract":
            backends.append(PyTesseractBackend())
        elif b == "tesserocr":
            try:
                backends.append(TesserOcrBackend())
            except Exception as e:
                print(f"[WARN] Skipping tesserocr: {e}")
        else:
            raise ValueError(f"Unknown backend: {b}")

    if not backends:
        print("No OCR backends available.")
        return 2

    args.out.mkdir(parents=True, exist_ok=True)

    for backend in backends:
        for variant in requested_variants:
            line_results: List[LineResult] = []

            for s in samples:
                line_results.append(
                    _run_one_line(
                        backend=backend,
                        cfg=cfg,
                        variant=variant,
                        sample_id=s.sample_id,
                        kind="lon",
                        path=s.lon_path,
                        expected=s.lon_expected,
                    )
                )
                line_results.append(
                    _run_one_line(
                        backend=backend,
                        cfg=cfg,
                        variant=variant,
                        sample_id=s.sample_id,
                        kind="lat",
                        path=s.lat_path,
                        expected=s.lat_expected,
                    )
                )

            pairs = _build_pairs(line_results)
            summary = _summarize(line_results, pairs)

            print("\n" + "=" * 80)
            print(f"backend={backend.name} variant={variant}")
            print(summary)

            fail_csv = args.out / f"failures__{backend.name}__{variant}.csv"
            _write_failures_csv(fail_csv, line_results)

        # Close backend if needed
        if hasattr(backend, "close"):
            try:
                backend.close()  # type: ignore[attr-defined]
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
