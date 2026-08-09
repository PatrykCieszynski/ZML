from __future__ import annotations

import cv2
import numpy as np

RelativeRect = tuple[float, float, float, float]


def crop_relative(img: np.ndarray, rect: RelativeRect) -> np.ndarray:
    height = int(img.shape[0])
    width = int(img.shape[1])
    x1 = max(0, min(width, int(width * rect[0])))
    y1 = max(0, min(height, int(height * rect[1])))
    x2 = max(0, min(width, int(width * rect[2])))
    y2 = max(0, min(height, int(height * rect[3])))
    if x2 <= x1 or y2 <= y1:
        shape = (1, 1) if img.ndim == 2 else (1, 1, int(img.shape[2]))
        return np.zeros(shape, dtype=np.uint8)
    return np.ascontiguousarray(img[y1:y2, x1:x2])


def to_bgr_u8(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        converted = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 3:
        converted = img
    elif img.ndim == 3 and img.shape[2] == 4:
        converted = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    else:
        raise ValueError(f"Unsupported image shape: {img.shape}")

    if converted.dtype != np.uint8:
        raise ValueError(f"Unsupported image dtype: {converted.dtype}")
    return converted


def to_gray_u8(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        converted = img
    elif img.ndim == 3 and img.shape[2] == 3:
        converted = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif img.ndim == 3 and img.shape[2] == 4:
        converted = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(f"Unsupported image shape: {img.shape}")

    if converted.dtype != np.uint8:
        raise ValueError(f"Unsupported grayscale dtype: {converted.dtype}")
    return converted


def upscale(img: np.ndarray, scale: int, interpolation: int) -> np.ndarray:
    if scale <= 1:
        return img
    height, width = img.shape[:2]
    return cv2.resize(img, (width * scale, height * scale), interpolation=interpolation)
