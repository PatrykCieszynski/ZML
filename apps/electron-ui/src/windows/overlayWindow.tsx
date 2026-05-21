import { useEffect, useMemo } from "react";
import type { WindowType } from "@zml/shared";
import { useZmlRendererStore } from "../state/zmlRendererStore";
import "./overlayWindow.css";

export function OverlayWindow() {
  const windowType: WindowType = "overlay";
  const state = useZmlRendererStore(windowType);
  const stats = useMemo(() => {
    const costMpec = state.miningDrops.reduce((sum, drop) => sum + drop.cost.totalMpec, 0);
    const returnMpec = state.miningLoot.reduce((sum, item) => sum + item.valueMpec, 0);
    const hitCount = state.miningDrops.filter((drop) => drop.result === "hit").length;
    return {
      costMpec,
      returnMpec,
      profitMpec: returnMpec - costMpec,
      hitRate: state.miningDrops.length === 0 ? null : hitCount / state.miningDrops.length,
    };
  }, [state.miningDrops, state.miningLoot]);

  useEffect(() => {
    document.body.dataset.windowType = "overlay";
    return () => {
      delete document.body.dataset.windowType;
    };
  }, []);

  return (
    <div className="zml-stream-overlay">
      <div className="zml-overlay-title">
        <strong>{state.activeRun?.name ?? "No active run"}</strong>
        <span>{state.streams.sse ? "live" : "offline"}</span>
      </div>
      <div className="zml-overlay-grid">
        <OverlayMetric label="Cost" value={formatPed(stats.costMpec)} />
        <OverlayMetric label="Return" value={formatPed(stats.returnMpec)} tone="gain" />
        <OverlayMetric label="Profit" value={formatPed(stats.profitMpec)} tone={stats.profitMpec >= 0 ? "gain" : "loss"} />
        <OverlayMetric label="Hit Rate" value={stats.hitRate === null ? "-" : `${(stats.hitRate * 100).toFixed(1)}%`} />
      </div>
    </div>
  );
}

function OverlayMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss";
}) {
  return (
    <div className="zml-overlay-metric">
      <span>{label}</span>
      <strong className={tone ? `is-${tone}` : undefined}>{value}</strong>
    </div>
  );
}

function formatPed(valueMpec: number): string {
  return `${(valueMpec / 100_000).toFixed(2)} PED`;
}
