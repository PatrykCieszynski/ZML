import { useMemo } from "react";
import type { WindowType } from "@zml/shared";
import {MapViewport} from "../widgets/map/mapViewport.tsx";
import { useZmlRendererStore } from "../state/zmlRendererStore";

type MapPoint = { x: number; y: number };

export function MapWindow() {
  const windowType: WindowType = "map";
  const state = useZmlRendererStore(windowType);

  const point: MapPoint | null = useMemo(() => {
    const pos = state.position?.position;
    if (!pos) return null;
    return { x: pos.x, y: pos.y };
  }, [state.position]);

  // hardcoded planet for now
  const planetId = "calypso" as const;

  return (
      <div style={{ position: "fixed", inset: 0, background: "#000" }}>
        <MapViewport planetId={planetId} point={point} miningDrops={state.miningDrops} />

        {/* overlays */}
        {state.error && (
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
              <div style={{ marginTop: 6 }}>{state.error}</div>
            </div>
        )}

        {!state.error && (
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
                {state.positionEvent ? `seq=${state.positionEvent.seq} ts=${state.positionEvent.tsMs}` : "waiting…"}
              </div>
            </div>
        )}
      </div>
  );
}
