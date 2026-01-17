# preprocess.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

PreprocessVariant = Literal[
    "p0_raw_upscale",
    "p1_contrast_upscale",
    "p2_adaptive_threshold",
    "p3_tophat_otsu_cc",
]


@dataclass(frozen=True, slots=True)
class PreprocessConfig:
    # Common
    upscale: int = 3  # 2-4 is usually enough for small UI digits
    interpolation: int = cv2.INTER_CUBIC

    # P1: contrast (CLAHE)
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: tuple[int, int] = (8, 8)
    gaussian_blur_ksize: int = 0  # 0 disables; use 3/5 if the input is noisy

    # P2: adaptive threshold
    adapt_block_size: int = 17  # must be odd and >= 3
    adapt_C: int = 5
    morph_kernel: tuple[int, int] = (2, 2)
    morph_iterations: int = 0  # default 0: your dataset showed morphology can kill anti-aliasing
    p2_upscale_first: bool = True

    # P3: top-hat + Otsu + CC cleanup
    p3_upscale_first: bool = True
    tophat_kernel: tuple[int, int] = (9, 9)  # try 7/9/11; must be >= digit stroke width scale
    p3_blur_ksize: int = 3  # odd; 0 disables
    p3_morph_close_kernel: tuple[int, int] = (2, 2)
    p3_morph_close_iterations: int = 1
    p3_remove_small_cc: bool = True
    p3_min_cc_area: int = 12  # tune: higher removes noise but can eat thin strokes
    p3_force_white_bg: bool = True


def _to_gray_u8(img: np.ndarray) -> np.ndarray:
    """Convert input image to single-channel uint8 grayscale."""
    if img is None:
        raise ValueError("img is None")

    if img.ndim == 2:
        gray = img
    elif img.ndim == 3 and img.shape[2] == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif img.ndim == 3 and img.shape[2] == 4:
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(f"Unsupported image shape: {img.shape}")

    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    return gray


def _upscale(img: np.ndarray, scale: int, interpolation: int) -> np.ndarray:
    """Upscale image by an integer factor."""
    if scale <= 1:
        return img
    h, w = img.shape[:2]
    return cv2.resize(img, (w * scale, h * scale), interpolation=interpolation)


def _ensure_odd_block_size(n: int) -> int:
    """Ensure adaptive threshold block size is odd and >= 3."""
    if n < 3:
        return 3
    return n if (n % 2 == 1) else (n + 1)


def _normalize_binary_background(binary: np.ndarray) -> np.ndarray:
    """
    Make the output binary image have mostly white background.
    This helps Tesseract and keeps behavior consistent.
    """
    white_ratio = float(np.count_nonzero(binary > 0)) / float(binary.size)
    if white_ratio < 0.5:
        return cv2.bitwise_not(binary)
    return binary


def _remove_small_components(binary: np.ndarray, min_area: int) -> np.ndarray:
    """
    Remove small connected components from a binary image (uint8 0/255).
    Keeps the background/foreground polarity unchanged.
    """
    if min_area <= 0:
        return binary

    # Work on a copy; ensure binary is 0/255
    bw = (binary > 0).astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if num_labels <= 1:
        return binary

    out = np.zeros_like(bw)
    for label in range(1, num_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= min_area:
            out[labels == label] = 1

    return (out * 255).astype(np.uint8)


def preprocess_line(img: np.ndarray, variant: PreprocessVariant, cfg: PreprocessConfig) -> np.ndarray:
    """
    Preprocess a single-line ROI (lon or lat) for OCR.
    Returns a single-channel uint8 image (grayscale or binary).
    """
    gray = _to_gray_u8(img)

    if variant == "p0_raw_upscale":
        return _upscale(gray, cfg.upscale, cfg.interpolation)

    if variant == "p1_contrast_upscale":
        # Note: CLAHE can destroy anti-aliased digits on small ROI; keep as optional variant.
        clahe = cv2.createCLAHE(
            clipLimit=cfg.clahe_clip_limit,
            tileGridSize=cfg.clahe_tile_grid_size,
        )
        eq = clahe.apply(gray)

        if cfg.gaussian_blur_ksize and cfg.gaussian_blur_ksize >= 3:
            k = cfg.gaussian_blur_ksize
            if k % 2 == 0:
                k += 1
            eq = cv2.GaussianBlur(eq, (k, k), 0)

        return _upscale(eq, cfg.upscale, cfg.interpolation)

    if variant == "p2_adaptive_threshold":
        work = gray
        if cfg.p2_upscale_first:
            work = _upscale(work, cfg.upscale, cfg.interpolation)

        clahe = cv2.createCLAHE(
            clipLimit=cfg.clahe_clip_limit,
            tileGridSize=cfg.clahe_tile_grid_size,
        )
        eq = clahe.apply(work)

        block = _ensure_odd_block_size(cfg.adapt_block_size)
        th = cv2.adaptiveThreshold(
            eq,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block,
            cfg.adapt_C,
        )

        if cfg.morph_iterations > 0:
            kx, ky = cfg.morph_kernel
            kx = max(1, int(kx))
            ky = max(1, int(ky))
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))
            th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=cfg.morph_iterations)

        th = _normalize_binary_background(th)

        # If we upscaled first, don't upscale again.
        if cfg.p2_upscale_first:
            return th
        return _upscale(th, cfg.upscale, cfg.interpolation)

    if variant == "p3_tophat_otsu_cc":
        work = gray
        if cfg.p3_upscale_first:
            work = _upscale(work, cfg.upscale, cfg.interpolation)

        kx, ky = cfg.tophat_kernel
        kx = max(1, int(kx))
        ky = max(1, int(ky))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))

        # Top-hat highlights bright strokes on varying background.
        th = cv2.morphologyEx(work, cv2.MORPH_TOPHAT, kernel)

        if cfg.p3_blur_ksize and cfg.p3_blur_ksize >= 3:
            k = cfg.p3_blur_ksize
            if k % 2 == 0:
                k += 1
            th = cv2.GaussianBlur(th, (k, k), 0)

        # Otsu binarization
        _, bw = cv2.threshold(th, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Connect broken strokes a bit (anti-aliasing / thin lines)
        if cfg.p3_morph_close_iterations > 0:
            ckx, cky = cfg.p3_morph_close_kernel
            ckx = max(1, int(ckx))
            cky = max(1, int(cky))
            ckernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ckx, cky))
            bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, ckernel, iterations=cfg.p3_morph_close_iterations)

        if cfg.p3_remove_small_cc:
            bw = _remove_small_components(bw, cfg.p3_min_cc_area)

        if cfg.p3_force_white_bg:
            bw = _normalize_binary_background(bw)

        if cfg.p3_upscale_first:
            return bw
        return _upscale(bw, cfg.upscale, cfg.interpolation)

    raise ValueError(f"Unknown variant: {variant}")
