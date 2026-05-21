import { useMemo, useState } from "react";
import type {
  ActiveMiningToolsDto,
  MiningClaimDto,
  MiningDropDto,
  MiningLootItemDto,
  MiningToolKind,
  MiningToolProfileDto,
  RunDto,
  RunSegmentDto,
  WindowType,
} from "@zml/shared";
import {
  refreshAgentHealth,
  refreshRuns,
  resumeRun,
  startRun,
  stopRun,
  toggleMapWindow,
  toggleOverlayWindow,
  useZmlRendererStore,
} from "../state/zmlRendererStore";
import { MiningToolsPanel } from "./miningToolsPanel";
import "./mainWindow.css";

type MainView = "dashboard" | "runs" | "segments" | "loot" | "claims" | "setup" | "debug";

type FeedItem = {
  id: string;
  tsMs: number;
  kind: "drop" | "hit" | "miss" | "claim";
  title: string;
  detail: string;
  amount?: string;
};

const NAV_ITEMS: Array<{ id: MainView; label: string }> = [
  { id: "dashboard", label: "Dashboard" },
  { id: "runs", label: "Runs" },
  { id: "segments", label: "Segments" },
  { id: "loot", label: "Loot" },
  { id: "claims", label: "Claims" },
  { id: "setup", label: "Setup" },
  { id: "debug", label: "Debug" },
];

export function MainWindow() {
  const windowType: WindowType = "main";
  const state = useZmlRendererStore(windowType);
  const position = state.position?.position;
  const [runName, setRunName] = useState("Mining run");
  const [view, setView] = useState<MainView>("dashboard");

  const activeSetup = useMemo(
    () => getActiveSetup(state.miningTools, state.activeMiningTools),
    [state.miningTools, state.activeMiningTools],
  );
  const runStats = useMemo(
    () => getRunStats(state.miningDrops, state.miningClaims, state.miningLoot),
    [state.miningDrops, state.miningClaims, state.miningLoot],
  );
  const feed = useMemo(
    () => buildFeed(state.miningDrops, state.miningClaims),
    [state.miningDrops, state.miningClaims],
  );
  const warnings = useMemo(
    () => buildWarnings({
      agentStatus: state.agent.status,
      wsConnected: state.streams.ws,
      sseConnected: state.streams.sse,
      activeRun: state.activeRun !== null,
      activeFinder: state.activeMiningTools?.finderId ?? null,
      lastError: state.agent.lastError ?? state.lastCommandError,
    }),
    [
      state.agent.status,
      state.agent.lastError,
      state.streams.ws,
      state.streams.sse,
      state.activeRun,
      state.activeMiningTools?.finderId,
      state.lastCommandError,
    ],
  );

  return (
    <div className="zml-app-shell">
      <header className="zml-topbar">
        <div className="zml-brand">
          <div className="zml-brand-mark" aria-hidden="true" />
          <div className="zml-brand-title">Z Mining Log</div>
        </div>

        <nav className="zml-nav" aria-label="Main view">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={item.id === view ? "zml-nav-item is-active" : "zml-nav-item"}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="zml-status-strip">
          <StatusPill label="Agent" ok={state.agent.status === "connected"} />
          <StatusPill label="WS" ok={state.streams.ws} />
          <StatusPill label="SSE" ok={state.streams.sse} />
          <StatusPill label="Run" ok={state.activeRun !== null} />
        </div>
      </header>

      <section className="zml-commandbar">
        <div className="zml-run-controls">
          <button
            type="button"
            className="zml-button zml-button-primary"
            onClick={() => {
              void startRun(runName);
            }}
            disabled={state.runCommandPending}
          >
            Start Run
          </button>
          <button
            type="button"
            className="zml-button"
            onClick={() => {
              void stopRun();
            }}
            disabled={state.runCommandPending || state.activeRun === null}
          >
            Stop
          </button>
          <label className="zml-run-name">
            <span>Run Name</span>
            <input
              value={runName}
              onChange={(event) => setRunName(event.currentTarget.value)}
              disabled={state.runCommandPending}
            />
          </label>
        </div>

        <div className="zml-run-meta">
          <button
            type="button"
            className="zml-button"
            onClick={() => {
              void toggleMapWindow();
            }}
          >
            {state.mapWindowVisible ? "Hide Map" : "Show Map"}
          </button>
          <button
            type="button"
            className="zml-button"
            onClick={() => {
              void toggleOverlayWindow();
            }}
          >
            {state.overlayWindowVisible ? "Hide Overlay" : "Show Overlay"}
          </button>
          <span>Status: {state.activeRun?.status ?? "idle"}</span>
          <span>Segments: {state.runSegments.length}</span>
          <span>Position: {formatPosition(position)}</span>
        </div>
      </section>

      {state.error && (
        <div className="zml-inline-error">
          <strong>UI error</strong>
          <span>{state.error}</span>
        </div>
      )}

      {!state.error && state.bootstrapping && (
        <div className="zml-loading">Loading bootstrap...</div>
      )}

      {!state.error && state.bootstrapped && (
        <main className="zml-main-grid">
          <aside className="zml-left-panel">
            <ActiveSetupPanel setup={activeSetup} activeTools={state.activeMiningTools} />
            <RunSummaryPanel stats={runStats} activeRunName={state.activeRun?.name ?? null} />
          </aside>

          <section className="zml-workspace">
            {view === "dashboard" && <DashboardFeed feed={feed} />}
            {view === "runs" && (
              <RunsView
                runs={state.runs}
                activeRunId={state.activeRun?.runId ?? null}
                pending={state.runCommandPending}
                onRefresh={() => {
                  void refreshRuns();
                }}
                onResume={(runId) => {
                  void resumeRun(runId);
                }}
              />
            )}
            {view === "segments" && (
              <SegmentsView
                segments={state.runSegments}
                drops={state.miningDrops}
                claims={state.miningClaims}
              />
            )}
            {view === "loot" && <LootView loot={state.miningLoot} />}
            {view === "claims" && <ClaimsView claims={state.miningClaims} />}
            {view === "setup" && (
              <MiningToolsPanel
                tools={state.miningTools}
                activeTools={state.activeMiningTools}
                loading={state.miningToolsLoading}
                pending={state.toolCommandPending}
              />
            )}
            {view === "debug" && (
              <DebugView
                stateSnapshot={state}
                onCheckHealth={() => {
                  void refreshAgentHealth();
                }}
              />
            )}
          </section>

          <aside className="zml-right-panel">
            <WarningsPanel warnings={warnings} />
            <RecentActivityPanel feed={feed} positionSeq={state.positionEvent?.seq ?? null} />
          </aside>
        </main>
      )}

      <footer className="zml-footer">
        <span>{position?.planetName || "Unknown planet"}</span>
        <span>{formatPosition(position)}</span>
        <span>Seq: {state.positionEvent?.seq ?? "-"}</span>
        <span>{state.lastCommandError ?? state.agent.lastError ?? "Ready"}</span>
      </footer>
    </div>
  );
}

function StatusPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={ok ? "zml-status-pill is-ok" : "zml-status-pill"}>
      <span className="zml-status-dot" />
      {label}
    </span>
  );
}

function ActiveSetupPanel({
  setup,
  activeTools,
}: {
  setup: ActiveSetup;
  activeTools?: ActiveMiningToolsDto;
}) {
  return (
    <section className="zml-panel">
      <PanelTitle title="Active Setup" />
      <div className="zml-setup-list">
        <SetupLine label="Finder" value={setup.finder} badge={formatMeters(activeTools?.effectiveFinderRadiusM)} />
        <SetupLine label="Amplifier" value={setup.amp} />
        <SetupLine label="Extractor" value={setup.extractor} badge={formatPedFromMpec(activeTools?.extractionCostMpec)} />
      </div>
      <div className="zml-divider" />
      <MetricRow label="Drop radius" value={formatMeters(activeTools?.effectiveFinderRadiusM)} />
      <MetricRow label="Extractor cost" value={formatPedFromMpec(activeTools?.extractionCostMpec)} />
      <MetricRow label="Range enhancers" value={String(activeTools?.finderRangeEnhancerCount ?? 0)} />
    </section>
  );
}

function RunSummaryPanel({
  stats,
  activeRunName,
}: {
  stats: RunStats;
  activeRunName: string | null;
}) {
  return (
    <section className="zml-panel">
      <PanelTitle title="Run Summary" />
      <div className="zml-active-run-name">{activeRunName ?? "No active run"}</div>
      <div className="zml-divider" />
      <MetricRow label="Drops" value={String(stats.dropCount)} />
      <MetricRow label="Hits" value={String(stats.hitCount)} accent="warn" />
      <MetricRow label="Misses" value={String(stats.noResourceCount)} />
      <MetricRow label="Hit rate" value={formatPercent(stats.hitRate)} />
      <MetricRow label="Cost TT" value={formatPed(stats.totalCostPed)} accent="loss" />
      <MetricRow label="Return TT" value={formatPed(stats.totalReturnPed)} accent="gain" />
      <MetricRow
        label="Profit"
        value={formatPed(stats.profitPed)}
        accent={stats.profitPed >= 0 ? "gain" : "loss"}
      />
      <MetricRow label="Active claims" value={String(stats.activeClaimCount)} accent="gain" />
    </section>
  );
}

function DashboardFeed({ feed }: { feed: FeedItem[] }) {
  return (
    <section className="zml-work-panel">
      <div className="zml-tabs-inline">
        <button type="button" className="is-active">All</button>
        <button type="button">Drops</button>
        <button type="button">Claims</button>
        <button type="button">Warnings</button>
      </div>
      {feed.length === 0 ? (
        <EmptyState text="No mining events yet" />
      ) : (
        <div className="zml-feed">
          {feed.map((item) => (
            <div key={item.id} className={`zml-feed-row is-${item.kind}`}>
              <time>{formatTime(item.tsMs)}</time>
              <span className="zml-feed-kind" aria-hidden="true" />
              <strong>{item.title}</strong>
              <span>{item.detail}</span>
              {item.amount && <b>{item.amount}</b>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function RunsView({
  runs,
  activeRunId,
  pending,
  onRefresh,
  onResume,
}: {
  runs: RunDto[];
  activeRunId: number | null;
  pending: boolean;
  onRefresh: () => void;
  onResume: (runId: number) => void;
}) {
  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Runs</h2>
          <span>Recent mining sessions</span>
        </div>
        <button type="button" className="zml-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      {runs.length === 0 ? (
        <EmptyState text="No runs yet" />
      ) : (
        <div className="zml-table-wrap">
          <table className="zml-data-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Created</th>
                <th>Updated</th>
                <th>Notes</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.runId}>
                  <td>
                    <strong>{run.name}</strong>
                  </td>
                  <td>
                    <span className={run.runId === activeRunId ? "zml-tag is-active" : "zml-tag"}>
                      {run.runId === activeRunId ? "active" : run.status}
                    </span>
                  </td>
                  <td>{run.createdTsMs === undefined ? "-" : formatTime(run.createdTsMs)}</td>
                  <td>{run.updatedTsMs === undefined ? "-" : formatTime(run.updatedTsMs)}</td>
                  <td>{run.notes ?? "-"}</td>
                  <td>
                    <button
                      type="button"
                      className="zml-button"
                      onClick={() => onResume(run.runId)}
                      disabled={pending || run.runId === activeRunId}
                    >
                      Resume
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SegmentsView({
  segments,
  drops,
  claims,
}: {
  segments: RunSegmentDto[];
  drops: MiningDropDto[];
  claims: MiningClaimDto[];
}) {
  const segmentRows = segments.map((segment) => {
    const segmentDrops = drops.filter((drop) => drop.segmentId === segment.segmentId);
    const segmentClaims = claims.filter((claim) => claim.dropId !== null && segmentDrops.some((drop) => drop.dropId === claim.dropId));
    const costPed = segmentDrops.reduce((sum, drop) => sum + drop.cost.totalMpec, 0) / 100_000;
    return { segment, dropCount: segmentDrops.length, claimCount: segmentClaims.length, costPed };
  });

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Segments</h2>
          <span>Current run</span>
        </div>
      </div>
      {segmentRows.length === 0 ? (
        <EmptyState text="No segments yet" />
      ) : (
        <div className="zml-table-wrap">
          <table className="zml-data-table">
            <thead>
              <tr>
                <th>Segment</th>
                <th>Status</th>
                <th>Start</th>
                <th>End</th>
                <th>Finder</th>
                <th>Amp</th>
                <th>Extractor</th>
                <th>Drops</th>
                <th>Claims</th>
                <th>Cost TT</th>
              </tr>
            </thead>
            <tbody>
              {segmentRows.map(({ segment, dropCount, claimCount, costPed }) => (
                <tr key={segment.segmentId}>
                  <td>#{segment.segmentIndex}</td>
                  <td>
                    <span className={segment.status === "active" ? "zml-tag is-active" : "zml-tag"}>
                      {segment.status}
                    </span>
                  </td>
                  <td>{formatTime(segment.startedTsMs)}</td>
                  <td>{segment.endedTsMs === null ? "-" : formatTime(segment.endedTsMs)}</td>
                  <td>{readToolSnapshotName(segment.setupSnapshot, "finder")}</td>
                  <td>{readToolSnapshotName(segment.setupSnapshot, "amp")}</td>
                  <td>{readToolSnapshotName(segment.setupSnapshot, "extractor")}</td>
                  <td>{dropCount}</td>
                  <td>{claimCount}</td>
                  <td>{formatPed(costPed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LootView({ loot }: { loot: MiningLootItemDto[] }) {
  const totalMpec = loot.reduce((sum, item) => sum + item.valueMpec, 0);
  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Loot</h2>
          <span>Live chat-derived returns</span>
        </div>
        <strong className="zml-section-total">{formatPedFromMpec(totalMpec)}</strong>
      </div>
      {loot.length === 0 ? (
        <EmptyState text="No loot recorded in this UI session" />
      ) : (
        <div className="zml-table-wrap">
          <table className="zml-data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Item</th>
                <th>Qty</th>
                <th>Value</th>
                <th>Extraction cost</th>
              </tr>
            </thead>
            <tbody>
              {loot.map((item) => (
                <tr key={`${item.eventId}:${item.createdTsMs}:${item.itemName}`}>
                  <td>{item.eventDt ?? formatTime(item.createdTsMs)}</td>
                  <td>{item.itemName}</td>
                  <td>{item.qty}</td>
                  <td>{formatPedFromMpec(item.valueMpec)}</td>
                  <td>{formatPedFromMpec(item.extractionCostMpec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ClaimsView({ claims }: { claims: MiningClaimDto[] }) {
  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Claims</h2>
          <span>Active only</span>
        </div>
      </div>
      {claims.length === 0 ? (
        <EmptyState text="No active claims" />
      ) : (
        <div className="zml-table-wrap">
          <table className="zml-data-table">
            <thead>
              <tr>
                <th>Resource</th>
                <th>Size</th>
                <th>Position</th>
                <th>Range</th>
                <th>Depth</th>
                <th>Expires</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((claim) => (
                <tr key={claim.claimId}>
                  <td>{claim.resourceName ?? "-"}</td>
                  <td>{formatSize(claim.sizeLabel, claim.sizeIndex)}</td>
                  <td>{formatPosition(claim.position)}</td>
                  <td>{formatMeters(claim.rangeM)}</td>
                  <td>{formatMeters(claim.depthM)}</td>
                  <td>{formatExpires(claim.expectedExpiresTsMs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DebugView({
  stateSnapshot,
  onCheckHealth,
}: {
  stateSnapshot: unknown;
  onCheckHealth: () => void;
}) {
  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Debug</h2>
          <span>Runtime snapshot</span>
        </div>
        <button type="button" className="zml-button" onClick={onCheckHealth}>
          Check Health
        </button>
      </div>
      <pre className="zml-debug-json">{JSON.stringify(stateSnapshot, null, 2)}</pre>
    </section>
  );
}

function WarningsPanel({ warnings }: { warnings: Array<{ title: string; detail: string }> }) {
  return (
    <section className="zml-panel zml-warning-panel">
      <PanelTitle title="Warnings" />
      {warnings.length === 0 ? (
        <EmptyState text="No warnings" compact />
      ) : (
        <div className="zml-warning-list">
          {warnings.map((warning) => (
            <div key={warning.title} className="zml-warning-card">
              <strong>{warning.title}</strong>
              <span>{warning.detail}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function RecentActivityPanel({
  feed,
  positionSeq,
}: {
  feed: FeedItem[];
  positionSeq: number | null;
}) {
  const latest = feed[0] ?? null;
  return (
    <section className="zml-panel">
      <PanelTitle title="Recent Activity" />
      <MetricRow label="Latest" value={latest ? latest.title : "-"} />
      <MetricRow label="Time" value={latest ? formatTime(latest.tsMs) : "-"} />
      <MetricRow label="Position seq" value={positionSeq === null ? "-" : String(positionSeq)} />
    </section>
  );
}

function PanelTitle({ title }: { title: string }) {
  return <h2 className="zml-panel-title">{title}</h2>;
}

function SetupLine({ label, value, badge }: { label: string; value: string; badge?: string }) {
  return (
    <div className="zml-setup-line">
      <span>{label}</span>
      <strong>{value}</strong>
      {badge && badge !== "-" && <em>{badge}</em>}
    </div>
  );
}

function MetricRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "gain" | "loss" | "warn";
}) {
  return (
    <div className="zml-metric-row">
      <span>{label}</span>
      <strong className={accent ? `is-${accent}` : undefined}>{value}</strong>
    </div>
  );
}

function EmptyState({ text, compact = false }: { text: string; compact?: boolean }) {
  return <div className={compact ? "zml-empty is-compact" : "zml-empty"}>{text}</div>;
}

type ActiveSetup = {
  finder: string;
  amp: string;
  extractor: string;
};

type RunStats = {
  dropCount: number;
  hitCount: number;
  noResourceCount: number;
  activeClaimCount: number;
  hitRate: number | null;
  totalCostPed: number;
  totalReturnPed: number;
  profitPed: number;
};

function getActiveSetup(
  tools: MiningToolProfileDto[],
  activeTools?: ActiveMiningToolsDto,
): ActiveSetup {
  return {
    finder: findToolName(tools, "finder", activeTools?.finderId, "Default finder"),
    amp: findToolName(tools, "amp", activeTools?.ampId, "No amp"),
    extractor: findToolName(tools, "extractor", activeTools?.extractorId, "No extractor"),
  };
}

function findToolName(
  tools: MiningToolProfileDto[],
  kind: MiningToolKind,
  toolId: string | null | undefined,
  fallback: string,
): string {
  if (!toolId) return fallback;
  return tools.find((tool) => tool.kind === kind && tool.toolId === toolId)?.name ?? fallback;
}

function getRunStats(drops: MiningDropDto[], claims: MiningClaimDto[], loot: MiningLootItemDto[]): RunStats {
  const hitCount = drops.filter((drop) => drop.result === "hit").length;
  const noResourceCount = drops.filter((drop) => drop.result === "no_resources").length;
  const totalCostPed = drops.reduce((sum, drop) => sum + drop.cost.totalMpec, 0) / 100_000;
  const totalReturnPed = loot.reduce((sum, item) => sum + item.valueMpec, 0) / 100_000;

  return {
    dropCount: drops.length,
    hitCount,
    noResourceCount,
    activeClaimCount: claims.filter((claim) => claim.status === "active").length,
    hitRate: drops.length === 0 ? null : hitCount / drops.length,
    totalCostPed,
    totalReturnPed,
    profitPed: totalReturnPed - totalCostPed,
  };
}

function buildFeed(drops: MiningDropDto[], claims: MiningClaimDto[]): FeedItem[] {
  const items: FeedItem[] = [];

  for (const drop of drops) {
    items.push({
      id: `${drop.dropId}:drop`,
      tsMs: drop.observedTsMs,
      kind: "drop",
      title: "Probe Fired",
      detail: formatDropDetail(drop),
    });

    if (drop.result === "hit") {
      items.push({
        id: `${drop.dropId}:hit`,
        tsMs: drop.resultObservedTsMs ?? drop.observedTsMs,
        kind: "hit",
        title: "Claim Detected",
        detail: `${drop.resourceName ?? "Unknown resource"} ${formatSize(drop.sizeLabel, drop.sizeIndex)}`,
        amount: formatMeters(drop.rangeM),
      });
    }

    if (drop.result === "no_resources") {
      items.push({
        id: `${drop.dropId}:miss`,
        tsMs: drop.resultObservedTsMs ?? drop.observedTsMs,
        kind: "miss",
        title: "No Resources Found",
        detail: formatDropDetail(drop),
      });
    }
  }

  for (const claim of claims) {
    items.push({
      id: `${claim.claimId}:claim`,
      tsMs: claim.observedTsMs,
      kind: "claim",
      title: "Claim Active",
      detail: `${claim.resourceName ?? "Unknown resource"} ${formatSize(claim.sizeLabel, claim.sizeIndex)}`,
      amount: formatExpires(claim.expectedExpiresTsMs),
    });
  }

  return items.sort((a, b) => b.tsMs - a.tsMs).slice(0, 80);
}

function buildWarnings({
  agentStatus,
  wsConnected,
  sseConnected,
  activeRun,
  activeFinder,
  lastError,
}: {
  agentStatus: string;
  wsConnected: boolean;
  sseConnected: boolean;
  activeRun: boolean;
  activeFinder: string | null;
  lastError?: string | null;
}): Array<{ title: string; detail: string }> {
  const warnings: Array<{ title: string; detail: string }> = [];
  if (agentStatus !== "connected") {
    warnings.push({ title: "Agent Offline", detail: "Backend connection is not ready." });
  }
  if (!wsConnected) {
    warnings.push({ title: "Position Stream Offline", detail: "Player position updates are not connected." });
  }
  if (!sseConnected) {
    warnings.push({ title: "Event Stream Offline", detail: "Mining events are not connected." });
  }
  if (!activeRun) {
    warnings.push({ title: "No Active Run", detail: "Drops will not be assigned to a run segment." });
  }
  if (!activeFinder) {
    warnings.push({ title: "No Finder Selected", detail: "Drop radius will use backend fallback." });
  }
  if (lastError) {
    warnings.push({ title: "Latest Error", detail: lastError });
  }
  return warnings.slice(0, 5);
}

function formatDropDetail(drop: MiningDropDto): string {
  const position = formatPosition(drop.position);
  const mode = drop.modesMask === null ? "mode -" : `mode ${drop.modesMask}`;
  return `${position} ${mode}`;
}

function formatSize(label: string | null, index: number | null): string {
  if (label === null && index === null) return "";
  if (label === null) return `(${index})`;
  return index === null ? `(${label})` : `(${label} ${index})`;
}

function formatPosition(position?: { x: number; y: number } | null): string {
  if (!position) return "-";
  return `${position.x}, ${position.y}`;
}

function formatMeters(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(1)} m`;
}

function formatPedFromMpec(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return formatPed(value / 100_000);
}

function formatPed(value: number): string {
  return `${value.toFixed(2)} PED`;
}

function formatPercent(value: number | null): string {
  if (value === null) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function formatTime(tsMs: number): string {
  return new Date(tsMs).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatExpires(tsMs: number | null): string {
  if (tsMs === null) return "no timer";
  const remainingMs = tsMs - Date.now();
  if (remainingMs <= 0) return "expired";
  const totalMinutes = Math.ceil(remainingMs / 60_000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
}

function readToolSnapshotName(snapshot: Record<string, unknown>, key: "finder" | "amp" | "extractor"): string {
  const value = snapshot[key];
  if (!isRecord(value)) return key === "amp" ? "No amp" : "-";
  return typeof value.name === "string" ? value.name : "-";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
