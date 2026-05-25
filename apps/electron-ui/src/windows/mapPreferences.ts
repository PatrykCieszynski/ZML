import { useCallback, useEffect, useState } from "react";

export type MapPreferences = {
  dropRadiusTtlMinutes: number;
};

const STORAGE_KEY = "zml.map.preferences";
const MAP_PREFS_EVENT = "zml-map-preferences";
const DEFAULT_DROP_RADIUS_TTL_MINUTES = 30;
const MAX_DROP_RADIUS_TTL_MINUTES = 24 * 60;

export const DEFAULT_MAP_PREFERENCES: MapPreferences = {
  dropRadiusTtlMinutes: DEFAULT_DROP_RADIUS_TTL_MINUTES,
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
  };
}

function clampDropRadiusTtl(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_DROP_RADIUS_TTL_MINUTES;
  }
  return Math.max(0, Math.min(MAX_DROP_RADIUS_TTL_MINUTES, Math.round(value)));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
