import { useCallback, useEffect, useState } from "react";

export type MapPreferences = {
  dropRadiusTtlMinutes: number;
  hexGridEnabled: boolean;
  hexGridMode: HexGridMode;
  hexGridAnchor: HexGridAnchor;
  hexGridAnchorPoint: HexGridAnchorPoint | null;
  hexGridOrientation: HexGridOrientation;
  smallClaimSoundEnabled: boolean;
  smallClaimSizeThreshold: number;
};

export type HexGridMode = "no-overlap" | "max-coverage";
export type HexGridAnchor = "map" | "player-offset";
export type HexGridOrientation = "vertical" | "horizontal";
export type HexGridAnchorPoint = {
  planetName?: string;
  x: number;
  y: number;
};

const STORAGE_KEY = "zml.map.preferences";
const MAP_PREFS_EVENT = "zml-map-preferences";
const DEFAULT_DROP_RADIUS_TTL_MINUTES = 30;
const MAX_DROP_RADIUS_TTL_MINUTES = 24 * 60;
const DEFAULT_SMALL_CLAIM_SIZE_THRESHOLD = 2;
const MAX_CLAIM_SIZE_INDEX = 27;

export const DEFAULT_MAP_PREFERENCES: MapPreferences = {
  dropRadiusTtlMinutes: DEFAULT_DROP_RADIUS_TTL_MINUTES,
  hexGridEnabled: false,
  hexGridMode: "max-coverage",
  hexGridAnchor: "map",
  hexGridAnchorPoint: null,
  hexGridOrientation: "vertical",
  smallClaimSoundEnabled: false,
  smallClaimSizeThreshold: DEFAULT_SMALL_CLAIM_SIZE_THRESHOLD,
};

export function useMapPreferences(): [
  MapPreferences,
  (next: MapPreferences | ((current: MapPreferences) => MapPreferences)) => void,
] {
  const [preferences, setPreferences] = useState(readMapPreferences);

  useEffect(() => {
    const handleChange = () => setPreferences(readMapPreferences());
    window.addEventListener("storage", handleChange);
    window.addEventListener(MAP_PREFS_EVENT, handleChange);
    return () => {
      window.removeEventListener("storage", handleChange);
      window.removeEventListener(MAP_PREFS_EVENT, handleChange);
    };
  }, []);

  const updatePreferences = useCallback(
    (next: MapPreferences | ((current: MapPreferences) => MapPreferences)) => {
      const current = readMapPreferences();
      const resolved = normalizePreferences(
        typeof next === "function" ? next(current) : next,
      );
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(resolved));
      window.dispatchEvent(new Event(MAP_PREFS_EVENT));
      setPreferences(resolved);
    },
    [],
  );

  return [preferences, updatePreferences];
}

function readMapPreferences(): MapPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_MAP_PREFERENCES;
    return normalizePreferences(JSON.parse(raw));
  } catch {
    return DEFAULT_MAP_PREFERENCES;
  }
}

function normalizePreferences(value: unknown): MapPreferences {
  if (!isRecord(value)) return DEFAULT_MAP_PREFERENCES;
  return {
    dropRadiusTtlMinutes: clampDropRadiusTtl(value.dropRadiusTtlMinutes),
    hexGridEnabled: typeof value.hexGridEnabled === "boolean"
      ? value.hexGridEnabled
      : DEFAULT_MAP_PREFERENCES.hexGridEnabled,
    hexGridMode: normalizeHexGridMode(value.hexGridMode),
    hexGridAnchor: normalizeHexGridAnchor(value.hexGridAnchor),
    hexGridAnchorPoint: normalizeHexGridAnchorPoint(value.hexGridAnchorPoint),
    hexGridOrientation: normalizeHexGridOrientation(value.hexGridOrientation),
    smallClaimSoundEnabled: typeof value.smallClaimSoundEnabled === "boolean"
      ? value.smallClaimSoundEnabled
      : DEFAULT_MAP_PREFERENCES.smallClaimSoundEnabled,
    smallClaimSizeThreshold: clampClaimSizeThreshold(value.smallClaimSizeThreshold),
  };
}

function clampDropRadiusTtl(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_DROP_RADIUS_TTL_MINUTES;
  }
  return Math.max(0, Math.min(MAX_DROP_RADIUS_TTL_MINUTES, Math.round(value)));
}

function normalizeHexGridMode(value: unknown): HexGridMode {
  return value === "no-overlap" || value === "max-coverage"
    ? value
    : DEFAULT_MAP_PREFERENCES.hexGridMode;
}

function normalizeHexGridAnchor(value: unknown): HexGridAnchor {
  if (value === "map" || value === "player-offset") return value;
  if (value === "player") return "player-offset";
  return DEFAULT_MAP_PREFERENCES.hexGridAnchor;
}

function normalizeHexGridOrientation(value: unknown): HexGridOrientation {
  return value === "vertical" || value === "horizontal"
    ? value
    : DEFAULT_MAP_PREFERENCES.hexGridOrientation;
}

function clampClaimSizeThreshold(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_SMALL_CLAIM_SIZE_THRESHOLD;
  }
  return Math.max(0, Math.min(MAX_CLAIM_SIZE_INDEX, Math.round(value)));
}

function normalizeHexGridAnchorPoint(value: unknown): HexGridAnchorPoint | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.x !== "number" ||
    !Number.isFinite(value.x) ||
    typeof value.y !== "number" ||
    !Number.isFinite(value.y)
  ) {
    return null;
  }

  return {
    planetName: typeof value.planetName === "string" ? value.planetName : undefined,
    x: value.x,
    y: value.y,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
