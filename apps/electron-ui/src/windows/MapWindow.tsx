import { useEffect, useMemo, useState } from "react";
import type { BootstrapState, OcrPositionEvent, WindowType } from "@zml/shared";
import { getZml } from "../zml";

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
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      return;
    }

    let alive = true;

    api
      .getBootstrapState(windowType)
      .then((s) => {
        if (alive) setBootstrap(s);
      })
      .catch((e) => {
        console.error(e);
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });

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

  return (
    <div style={{ padding: 12, fontFamily: "system-ui, sans-serif" }}>
      <h3 style={{ marginTop: 0 }}>Map</h3>

      {error && (
        <div style={{ background: "#2a0f0f", color: "#ffdada", padding: 12, borderRadius: 8 }}>
          <b>UI error</b>
          <div style={{ marginTop: 6 }}>{error}</div>
        </div>
      )}

      {!error && (
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: "0 0 280px" }}>
            <div style={{ fontSize: 14, opacity: 0.85, marginBottom: 6 }}>Last position</div>
            <div style={{ background: "#111", color: "#ddd", padding: 10, borderRadius: 8 }}>
              {point ? (
                <>
                  <div>
                    <b>X</b>: {point.x}
                  </div>
                  <div>
                    <b>Y</b>: {point.y}
                  </div>
                </>
              ) : (
                <div style={{ opacity: 0.7 }}>No data</div>
              )}
            </div>

            <div style={{ marginTop: 12, fontSize: 12, opacity: 0.7 }}>
              {last ? `seq=${last.seq} ts=${last.tsMs}` : "waiting…"}
            </div>
          </div>

          <div style={{ flex: 1 }}>
            <div
              style={{
                height: 420,
                borderRadius: 12,
                background: "#0b0b0b",
                border: "1px solid #222",
                position: "relative",
                overflow: "hidden",
              }}
            >
              {/* Fake "map": just plot a dot with simple scaling. */}
              {point && (
                <div
                  title={`(${point.x}, ${point.y})`}
                  style={{
                    position: "absolute",
                    left: `${(point.x % 1000) / 10}%`,
                    top: `${(point.y % 1000) / 10}%`,
                    width: 10,
                    height: 10,
                    borderRadius: 999,
                    background: "#44f",
                    transform: "translate(-50%, -50%)",
                  }}
                />
              )}
            </div>

            <div style={{ fontSize: 12, opacity: 0.7, marginTop: 8 }}>
              The dot position is currently just a modulo projection. Real mapping comes later.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
