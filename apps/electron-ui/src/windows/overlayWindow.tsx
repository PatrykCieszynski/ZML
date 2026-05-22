import { useEffect, useMemo, type CSSProperties } from "react";
import type { WindowType } from "@zml/shared";
import { useZmlRendererStore } from "../state/zmlRendererStore";
import { useOverlayPreferences, type OverlayMetricKey } from "./overlayPreferences";
import "./overlayWindow.css";

type OverlayMetric = {
  key: OverlayMetricKey;
  label: string;
  value: string;
  tone?: "gain" | "loss";
};

export function OverlayWindow() {
  const windowType: WindowType = "overlay";
  const state = useZmlRendererStore(windowType);
  const [preferences] = useOverlayPreferences();
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
  const metrics = useMemo<OverlayMetric[]>(
    () => {
      const allMetrics: OverlayMetric[] = [
        { key: "cost", label: "Cost", value: formatPed(stats.costMpec) },
        { key: "return", label: "Return", value: formatPed(stats.returnMpec), tone: "gain" },
        {
          key: "profit",
          label: "Profit",
          value: formatPed(stats.profitMpec),
          tone: stats.profitMpec >= 0 ? "gain" : "loss",
        },
        {
          key: "hitRate",
          label: "Hit Rate",
          value: stats.hitRate === null ? "-" : `${(stats.hitRate * 100).toFixed(1)}%`,
        },
      ];
      return allMetrics.filter((metric) => preferences.metrics[metric.key]);
    },
    [preferences.metrics, stats],
  );
  const showTitle = preferences.showRunName || preferences.showStatus;

  useEffect(() => {
    document.documentElement.dataset.windowType = "overlay";
    document.body.dataset.windowType = "overlay";
    return () => {
      delete document.documentElement.dataset.windowType;
      delete document.body.dataset.windowType;
    };
  }, []);

  return (
    <div
      className="zml-stream-overlay"
      style={{ "--zml-overlay-font-size": `${preferences.fontSizePx}px` } as CSSProperties}
    >
      {showTitle && (
        <div className="zml-overlay-title">
          {preferences.showRunName && <strong>{state.activeRun?.name ?? "No active run"}</strong>}
          {preferences.showStatus && <span>{state.streams.sse ? "live" : "offline"}</span>}
        </div>
      )}
      <div className="zml-overlay-grid">
        {metrics.map((metric) => (
          <OverlayMetricView
            key={metric.key}
            label={metric.label}
            value={metric.value}
            tone={metric.tone}
          />
        ))}
      </div>
    </div>
  );
}

function OverlayMetricView({
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
