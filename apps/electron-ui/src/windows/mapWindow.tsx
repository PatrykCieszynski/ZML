import { useMemo, useState } from "react";
import type { WindowType } from "@zml/shared";
import { MapViewport } from "../widgets/map/mapViewport.tsx";
import { toggleMapWindow, useZmlRendererStore } from "../state/zmlRendererStore";
import "./mapWindow.css";

type MapPoint = { x: number; y: number };

export function MapWindow() {
  const windowType: WindowType = "map";
  const state = useZmlRendererStore(windowType);
  const [followPlayer, setFollowPlayer] = useState(true);

  const point: MapPoint | null = useMemo(() => {
    const pos = state.position?.position;
    if (!pos) return null;
    return { x: pos.x, y: pos.y };
  }, [state.position]);

  // hardcoded planet for now
  const planetId = "calypso" as const;

  return (
    <div className="zml-map-window">
      <header className="zml-map-titlebar">
        <div className="zml-map-title">
          <strong>Z Mining Log Map</strong>
          <span>{planetId}</span>
        </div>
        <div className="zml-map-actions">
          <button
            type="button"
            className={followPlayer ? "is-active" : undefined}
            onClick={() => setFollowPlayer((current) => !current)}
          >
            {followPlayer ? "Following" : "Follow Player"}
          </button>
          <button
            type="button"
            onClick={() => {
              void toggleMapWindow();
            }}
          >
            Hide
          </button>
        </div>
      </header>

      <div className="zml-map-canvas">
        <MapViewport
          planetId={planetId}
          point={point}
          miningClaims={state.miningClaims}
          miningDrops={state.miningDrops}
          playerRadiusM={state.activeMiningTools?.effectiveFinderRadiusM}
          followPlayer={followPlayer}
          onFollowPlayerChange={setFollowPlayer}
        />
      </div>

      {state.error && (
        <div className="zml-map-error">
          <b>UI error</b>
          <div>{state.error}</div>
        </div>
      )}
    </div>
  );
}
