# preprocess.py
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class DigitsPreprocessConfig:
    upscale: int = 2
    interpolation: int = cv2.INTER_CUBIC

    tophat_kernel: tuple[int, int] = (9, 9)
    blur_ksize: int = 0  # odd, 0 disables

    morph_close_kernel: tuple[int, int] = (2, 2)
    morph_close_iterations: int = 1

    remove_small_cc: bool = False
    min_cc_area: int = 12

    force_white_bg: bool = True


def _to_gray_u8(img: np.ndarray) -> np.ndarray:
    """Convert input image to single-channel uint8 grayscale."""
    if img.ndim == 2:
        gray = img
    elif img.ndim == 3 and img.shape[2] == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif img.ndim == 3 and img.shape[2] == 4:
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(f"Unsupported image shape: {img.shape}")

    if gray.dtype != np.uint8:
        raise ValueError(f"Unsupported grayscale dtype: {gray.dtype}")

    return gray


def _upscale(img: np.ndarray, scale: int, interpolation: int) -> np.ndarray:
    """Upscale image by an integer factor."""
    if scale <= 1:
        return img
    h, w = img.shape[:2]
    return cv2.resize(img, (w * scale, h * scale), interpolation=interpolation)


def _normalize_binary_background(binary: np.ndarray) -> np.ndarray:
    """Ensure mostly white background (helps OCR)."""
    white_ratio = float(np.count_nonzero(binary > 0)) / float(binary.size)
    if white_ratio < 0.5:
        return cv2.bitwise_not(binary)
    return binary


def _remove_small_components(binary: np.ndarray, min_area: int) -> np.ndarray:
    """Remove small connected components from a binary image (uint8 0/255)."""
    if min_area <= 0:
        return binary

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


class DigitsPreprocessor:
    """
    Cache-heavy objects (kernels) are created once in __init__.
    The process() method stays stateless and thread-safe.
    """

    def __init__(self, cfg: DigitsPreprocessConfig | None = None) -> None:
        self.cfg = cfg or DigitsPreprocessConfig()

        kx, ky = (max(1, int(self.cfg.tophat_kernel[0])), max(1, int(self.cfg.tophat_kernel[1])))
        self._tophat_kernel_mat = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))

        ckx, cky = (
            max(1, int(self.cfg.morph_close_kernel[0])),
            max(1, int(self.cfg.morph_close_kernel[1])),
        )
        self._close_kernel_mat = cv2.getStructuringElement(cv2.MORPH_RECT, (ckx, cky))

    def process(self, img: np.ndarray) -> np.ndarray:
        """
        Preprocess a single-line ROI containing bright digits on varying background.
        Returns binary uint8 (0/255).
        """
        gray = _to_gray_u8(img)
        work = _upscale(gray, self.cfg.upscale, self.cfg.interpolation)

        top = cv2.morphologyEx(work, cv2.MORPH_TOPHAT, self._tophat_kernel_mat)

        if self.cfg.blur_ksize and self.cfg.blur_ksize >= 3:
            k = int(self.cfg.blur_ksize)
            if k % 2 == 0:
                k += 1
            top = cv2.GaussianBlur(top, (k, k), 0)

        _, bw = cv2.threshold(top, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        if self.cfg.morph_close_iterations > 0:
            bw = cv2.morphologyEx(
                bw,
                cv2.MORPH_CLOSE,
                self._close_kernel_mat,
                iterations=int(self.cfg.morph_close_iterations),
            )

        if self.cfg.remove_small_cc:
            bw = _remove_small_components(bw, int(self.cfg.min_cc_area))

        if self.cfg.force_white_bg:
            bw = _normalize_binary_background(bw)

        return bw
