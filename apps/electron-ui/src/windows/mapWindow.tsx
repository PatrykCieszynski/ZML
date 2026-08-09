import { useMemo, useState } from "react";
import type { WindowType } from "@desktop/shared";
import { MapViewport } from "../widgets/map/mapViewport.tsx";
import {
  ignoreMiningClaim,
  markMiningClaimDepleted,
  toggleMapWindow,
  useZmlRendererStore,
} from "../state/zmlRendererStore";
import { useMapPreferences } from "./mapPreferences";
import "./mapWindow.css";

type MapPoint = { x: number; y: number };

export function MapWindow() {
  const windowType: WindowType = "map";
  const state = useZmlRendererStore(windowType);
  const [followPlayer, setFollowPlayer] = useState(true);
  const [preferences, setPreferences] = useMapPreferences();

  const point: MapPoint | null = useMemo(() => {
    const pos = state.position?.position;
    if (!pos) return null;
    return { x: pos.x, y: pos.y };
  }, [state.position]);

  // hardcoded planet for now
  const planetId = "rocktropia" as const;

  return (
    <div className="zml-map-window">
      <header className="zml-map-titlebar">
        <div className="zml-map-title">
          <strong>Z Mining Log Map</strong>
          <span>{planetId}</span>
        </div>
        <div className="zml-map-actions">
          <label className="zml-map-setting">
            <span>Drop circles</span>
            <select
              value={String(preferences.dropRadiusTtlMinutes)}
              onChange={(event) => {
                const value = Number(event.currentTarget.value);
                setPreferences((current) => ({ ...current, dropRadiusTtlMinutes: value }));
              }}
            >
              <option value="15">15m</option>
              <option value="30">30m</option>
              <option value="60">60m</option>
              <option value="120">120m</option>
              <option value="0">Always</option>
            </select>
          </label>
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
          dropRadiusTtlMinutes={preferences.dropRadiusTtlMinutes}
          hexGridEnabled={preferences.hexGridEnabled}
          hexGridMode={preferences.hexGridMode}
          hexGridAnchor={preferences.hexGridAnchor}
          hexGridAnchorPoint={preferences.hexGridAnchorPoint}
          hexGridOrientation={preferences.hexGridOrientation}
          followPlayer={followPlayer}
          onFollowPlayerChange={setFollowPlayer}
          onIgnoreClaim={(claimId) => {
            void ignoreMiningClaim(claimId);
          }}
          onMarkClaimDepleted={(claimId) => {
            void markMiningClaimDepleted(claimId);
          }}
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
