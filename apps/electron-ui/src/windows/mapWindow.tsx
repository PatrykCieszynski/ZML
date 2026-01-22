import { useEffect, useMemo, useState } from "react";
import type { BootstrapState, OcrPositionEvent, WindowType } from "@zml/shared";
import { getZml } from "../zml";
import {MapViewport} from "../widgets/map/mapViewport.tsx";

type MapPoint = { x: number; y: number };

export function MapWindow() {
  const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
  const [last, setLast] = useState<OcrPositionEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const windowType: WindowType = "map";

  useEffect(() => {
    let api;
    try {
      api = getZml();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return;
    }

    let alive = true;

    api.getBootstrapState(windowType)
        .then((s) => alive && setBootstrap(s))
        .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));

    const unsub = api.onPosition((ev) => setLast(ev));

    return () => {
      alive = false;
      unsub();
    };
  }, []);

  const point: MapPoint | null = useMemo(() => {
    const pos = last?.payload?.position ?? bootstrap?.position?.position;
    if (!pos) return null;
    return { x: pos.x, y: pos.y };
  }, [last, bootstrap]);

  // hardcoded planet for now
  const planetId = "calypso" as const;

  return (
      <div style={{ position: "fixed", inset: 0, background: "#000" }}>
        <MapViewport planetId={planetId} point={point} />

        {/* overlays */}
        {error && (
            <div
                style={{
                  position: "absolute",
                  left: 12,
                  top: 12,
                  background: "#2a0f0f",
                  color: "#ffdada",
                  padding: 12,
                  borderRadius: 10,
                  maxWidth: 420,
                }}
            >
              <b>UI error</b>
              <div style={{ marginTop: 6 }}>{error}</div>
            </div>
        )}

        {!error && (
            <div
                style={{
                  position: "absolute",
                  left: 12,
                  top: 12,
                  background: "rgba(0,0,0,0.55)",
                  color: "#ddd",
                  padding: "10px 12px",
                  borderRadius: 10,
                  fontFamily: "system-ui, sans-serif",
                  fontSize: 12,
                  backdropFilter: "blur(6px)",
                }}
            >
              <div><b>{planetId}</b></div>
              <div>X: {point ? point.x : "—"}</div>
              <div>Y: {point ? point.y : "—"}</div>
              <div style={{ opacity: 0.7, marginTop: 6 }}>
                {last ? `seq=${last.seq} ts=${last.tsMs}` : "waiting…"}
              </div>
            </div>
        )}
      </div>
  );
}
