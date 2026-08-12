import { ipcMain } from "electron";
import {
  IPC_CMD,
  isOcrCalibrationSnapshotDto,
  isOcrRecalibrationResultDto,
  type OcrCalibrationSnapshotDto,
  type OcrRecalibrationResultDto,
} from "@desktop/shared";

const BACKEND_URL = process.env.ZML_BACKEND_URL ?? "http://127.0.0.1:17171";
const REQUEST_TIMEOUT_MS = 15_000;

let registered = false;

export function registerCalibrationIpc(): void {
  if (registered) return;
  registered = true;

  ipcMain.handle(IPC_CMD.GET_OCR_CALIBRATION, async () => {
    const value = await requestJson("GET", "/api/v1/ocr/calibration");
    if (!isOcrCalibrationSnapshotDto(value)) {
      throw new Error("Backend OCR calibration returned an invalid payload");
    }
    return value satisfies OcrCalibrationSnapshotDto;
  });

  ipcMain.handle(IPC_CMD.RECALIBRATE_OCR, async () => {
    const value = await requestJson("POST", "/api/v1/ocr/calibration/recalibrate");
    if (!isOcrRecalibrationResultDto(value)) {
      throw new Error("Backend OCR recalibration returned an invalid payload");
    }
    return value satisfies OcrRecalibrationResultDto;
  });
}

async function requestJson(method: "GET" | "POST", pathname: string): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(new URL(pathname, BACKEND_URL), {
      method,
      headers: { accept: "application/json" },
      signal: controller.signal,
    });
    const text = await response.text();
    const payload = text ? parseJson(text) : null;
    if (!response.ok) {
      const detail = extractErrorDetail(payload) ?? `Backend request failed (${response.status})`;
      throw new Error(detail);
    }
    return payload;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("OCR calibration request timed out");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function extractErrorDetail(value: unknown): string | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const detail = (value as Record<string, unknown>).detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
}
