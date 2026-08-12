export type CalibrationRect = [number, number, number, number];

export type OcrCalibrationRegionDto = {
  available: boolean;
  imageDataUrl?: string;
  capturedTsMs?: number | null;
  rect?: CalibrationRect | null;
  confidence?: number | null;
  scale?: number | null;
  innerRects?: Record<string, CalibrationRect>;
};

export type OcrCalibrationSnapshotDto = {
  capturedTsMs: number | null;
  finder: OcrCalibrationRegionDto;
  compass: OcrCalibrationRegionDto;
};

export type OcrRecalibrationResultDto = {
  ok: boolean;
  workerPid: number;
  message: string;
};

export function isOcrCalibrationSnapshotDto(value: unknown): value is OcrCalibrationSnapshotDto {
  if (!isObject(value)) return false;
  return (
    isNullableNumber(value.capturedTsMs) &&
    isCalibrationRegion(value.finder) &&
    isCalibrationRegion(value.compass)
  );
}

export function isOcrRecalibrationResultDto(value: unknown): value is OcrRecalibrationResultDto {
  return (
    isObject(value) &&
    value.ok === true &&
    typeof value.workerPid === "number" &&
    Number.isFinite(value.workerPid) &&
    typeof value.message === "string"
  );
}

function isCalibrationRegion(value: unknown): value is OcrCalibrationRegionDto {
  if (!isObject(value) || typeof value.available !== "boolean") return false;
  if (!value.available) return true;
  return (
    typeof value.imageDataUrl === "string" &&
    value.imageDataUrl.startsWith("data:image/png;base64,") &&
    isOptionalNullableNumber(value.capturedTsMs) &&
    isOptionalRect(value.rect) &&
    isOptionalNullableNumber(value.confidence) &&
    isOptionalNullableNumber(value.scale) &&
    (value.innerRects === undefined || isRectRecord(value.innerRects))
  );
}

function isRectRecord(value: unknown): value is Record<string, CalibrationRect> {
  if (!isObject(value)) return false;
  return Object.values(value).every(isRect);
}

function isOptionalRect(value: unknown): boolean {
  return value === undefined || value === null || isRect(value);
}

function isRect(value: unknown): value is CalibrationRect {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item))
  );
}

function isOptionalNullableNumber(value: unknown): boolean {
  return value === undefined || isNullableNumber(value);
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
