import { useCallback, useEffect, useState } from "react";

export type OverlayMetricKey = "costTt" | "costWithMarkup" | "return" | "profit" | "hitRate";

export type OverlayPreferences = {
  fontSizePx: number;
  showRunName: boolean;
  showStatus: boolean;
  metrics: Record<OverlayMetricKey, boolean>;
};

const STORAGE_KEY = "zml.overlay.preferences";
const OVERLAY_PREFS_EVENT = "zml-overlay-preferences";
const MIN_FONT_SIZE_PX = 10;
const MAX_FONT_SIZE_PX = 28;

export const DEFAULT_OVERLAY_PREFERENCES: OverlayPreferences = {
  fontSizePx: 13,
  showRunName: true,
  showStatus: true,
  metrics: {
    costTt: true,
    costWithMarkup: true,
    return: true,
    profit: true,
    hitRate: true,
  },
};

export function useOverlayPreferences(): [
  OverlayPreferences,
  (next: OverlayPreferences | ((current: OverlayPreferences) => OverlayPreferences)) => void,
] {
  const [preferences, setPreferences] = useState(readOverlayPreferences);

  useEffect(() => {
    const handleChange = () => setPreferences(readOverlayPreferences());
    window.addEventListener("storage", handleChange);
    window.addEventListener(OVERLAY_PREFS_EVENT, handleChange);
    return () => {
      window.removeEventListener("storage", handleChange);
      window.removeEventListener(OVERLAY_PREFS_EVENT, handleChange);
    };
  }, []);

  const updatePreferences = useCallback(
    (next: OverlayPreferences | ((current: OverlayPreferences) => OverlayPreferences)) => {
      const current = readOverlayPreferences();
      const resolved = normalizePreferences(
        typeof next === "function" ? next(current) : next,
      );
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(resolved));
      window.dispatchEvent(new Event(OVERLAY_PREFS_EVENT));
      setPreferences(resolved);
    },
    [],
  );

  return [preferences, updatePreferences];
}

function readOverlayPreferences(): OverlayPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_OVERLAY_PREFERENCES;
    return normalizePreferences(JSON.parse(raw));
  } catch {
    return DEFAULT_OVERLAY_PREFERENCES;
  }
}

function normalizePreferences(value: unknown): OverlayPreferences {
  if (!isRecord(value)) return DEFAULT_OVERLAY_PREFERENCES;
  const metrics = isRecord(value.metrics) ? value.metrics : {};
  const legacyCost = readBoolean(metrics.cost, true);
  return {
    fontSizePx: clampFontSize(value.fontSizePx),
    showRunName: typeof value.showRunName === "boolean"
      ? value.showRunName
      : DEFAULT_OVERLAY_PREFERENCES.showRunName,
    showStatus: typeof value.showStatus === "boolean"
      ? value.showStatus
      : DEFAULT_OVERLAY_PREFERENCES.showStatus,
    metrics: {
      costTt: readBoolean(metrics.costTt, legacyCost),
      costWithMarkup: readBoolean(metrics.costWithMarkup, legacyCost),
      return: readBoolean(metrics.return, DEFAULT_OVERLAY_PREFERENCES.metrics.return),
      profit: readBoolean(metrics.profit, DEFAULT_OVERLAY_PREFERENCES.metrics.profit),
      hitRate: readBoolean(metrics.hitRate, DEFAULT_OVERLAY_PREFERENCES.metrics.hitRate),
    },
  };
}

function clampFontSize(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_OVERLAY_PREFERENCES.fontSizePx;
  }
  return Math.max(MIN_FONT_SIZE_PX, Math.min(MAX_FONT_SIZE_PX, Math.round(value)));
}

function readBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
