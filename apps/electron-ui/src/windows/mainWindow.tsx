import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type {
  ActiveMiningToolsDto,
  MiningClaimDto,
  MiningDropDto,
  MiningLootItemDto,
  MiningLootTotalDto,
  MiningResourceType,
  MiningToolKind,
  MiningToolProfileDto,
  RunDto,
  RunSegmentDto,
  WorldPosDTO,
  WindowType,
} from "@zml/shared";
import {
  deleteRun,
  refreshAgentHealth,
  refreshRuns,
  resumeRun,
  setActiveMiningTools,
  startRun,
  stopRun,
  toggleMapWindow,
  toggleOverlayWindow,
  updateRunName,
  useZmlRendererStore,
  type ZmlRendererState,
} from "../state/zmlRendererStore";
import { MiningToolsPanel } from "./miningToolsPanel";
import { useMapPreferences, type MapPreferences } from "./mapPreferences";
import { useOverlayPreferences, type OverlayMetricKey } from "./overlayPreferences";
import "./mainWindow.css";

type MainView = "dashboard" | "runs" | "segments" | "loot" | "claims" | "setup" | "map" | "overlay" | "debug";

type FeedItem = {
  id: string;
  tsMs: number;
  kind: "drop" | "hit" | "miss" | "claim" | "depleted" | "ignored" | "expired" | "loot";
  title: string;
  detail: string;
  amount?: string;
};

type DashboardFeedFilter = "activity" | "all" | "drops" | "claims" | "loot";

const DASHBOARD_FEED_FILTERS: Array<{ id: DashboardFeedFilter; label: string }> = [
  { id: "activity", label: "Activity" },
  { id: "all", label: "All Events" },
  { id: "drops", label: "Drops" },
  { id: "claims", label: "Claims" },
  { id: "loot", label: "Loot" },
];
const MAX_DASHBOARD_FEED_ITEMS = 80;

const NAV_ITEMS: Array<{ id: MainView; label: string }> = [
  { id: "dashboard", label: "Dashboard" },
  { id: "runs", label: "Runs" },
  { id: "segments", label: "Segments" },
  { id: "loot", label: "Loot" },
  { id: "claims", label: "Claims" },
  { id: "setup", label: "Setup" },
  { id: "map", label: "Map" },
  { id: "overlay", label: "Overlay" },
  { id: "debug", label: "Debug" },
];

export function MainWindow() {
  const windowType: WindowType = "main";
  const state = useZmlRendererStore(windowType);
  const [mapPreferences] = useMapPreferences();
  const position = state.position?.position;
  const activeRunId = state.activeRun?.runId ?? null;
  const activeRunName = state.activeRun?.name;
  const [runName, setRunName] = useState("Mining run");
  const [view, setView] = useState<MainView>("dashboard");
  const canUpdateRunName =
    state.activeRun !== null &&
    runName.trim().length > 0 &&
    runName.trim() !== state.activeRun.name &&
    !state.runCommandPending;

  useEffect(() => {
    if (activeRunName !== undefined) {
      setRunName(activeRunName);
    }
  }, [activeRunId, activeRunName]);

  const activeSetup = useMemo(
    () => getActiveSetup(state.miningTools, state.activeMiningTools),
    [state.miningTools, state.activeMiningTools],
  );
  const runStats = useMemo(
    () => getRunStats(state.miningDrops, state.miningClaims, state.miningLootTotals),
    [state.miningDrops, state.miningClaims, state.miningLootTotals],
  );
  const feed = useMemo(
    () => buildFeed(state.miningDrops, state.miningClaims, state.miningLoot),
    [state.miningDrops, state.miningClaims, state.miningLoot],
  );
  const activityFeed = useMemo(
    () => filterFeed(feed, "activity"),
    [feed],
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
  useSmallClaimSoundAlert(state.miningClaims, mapPreferences);

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
          <button
            type="button"
            className="zml-button"
            onClick={() => {
              if (state.activeRun !== null) {
                void updateRunName(state.activeRun.runId, runName);
              }
            }}
            disabled={!canUpdateRunName}
          >
            Update Name
          </button>
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
            <ActiveSetupPanel
              setup={activeSetup}
              activeTools={state.activeMiningTools}
              tools={state.miningTools}
              pending={state.toolCommandPending}
            />
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
                onDelete={(run) => {
                  const confirmed = window.confirm(
                    `Delete run "${run.name}"?\n\nIt will be hidden from the UI, but its data stays in the database.`,
                  );
                  if (confirmed) {
                    void deleteRun(run.runId);
                  }
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
            {view === "loot" && <LootView loot={state.miningLoot} totals={state.miningLootTotals} />}
            {view === "claims" && <ClaimsView claims={state.miningClaims} />}
            {view === "setup" && (
              <MiningToolsPanel
                tools={state.miningTools}
                activeTools={state.activeMiningTools}
                loading={state.miningToolsLoading}
                pending={state.toolCommandPending}
              />
            )}
            {view === "map" && <MapSettingsView position={position ?? null} />}
            {view === "overlay" && <OverlaySettingsView />}
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
            <RecentActivityPanel feed={activityFeed} positionSeq={state.positionEvent?.seq ?? null} />
          </aside>
        </main>
      )}

      <footer className="zml-footer">
        <div className="zml-footer-position">
          <span>{position?.planetName || "Unknown planet"}</span>
          <strong>{formatPosition(position)}</strong>
          <span>Seq {state.positionEvent?.seq ?? "-"}</span>
        </div>
        <span className="zml-footer-message">
          {state.lastCommandError ?? state.agent.lastError ?? "Ready"}
        </span>
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
  tools,
  pending,
}: {
  setup: ActiveSetup;
  activeTools?: ActiveMiningToolsDto;
  tools: MiningToolProfileDto[];
  pending: boolean;
}) {
  const finderTools = tools.filter((tool) => tool.kind === "finder");
  const ampTools = tools.filter((tool) => tool.kind === "amp");

  const handleFinderChange = (value: string) => {
    void setActiveMiningTools({
      finderId: emptyStringToNull(value),
      ampId: activeTools?.ampId ?? null,
      extractorId: activeTools?.extractorId ?? null,
      finderRangeEnhancerCount: activeTools?.finderRangeEnhancerCount ?? 0,
    });
  };

  const handleAmpChange = (value: string) => {
    void setActiveMiningTools({
      finderId: activeTools?.finderId ?? null,
      ampId: emptyStringToNull(value),
      extractorId: activeTools?.extractorId ?? null,
      finderRangeEnhancerCount: activeTools?.finderRangeEnhancerCount ?? 0,
    });
  };

  return (
    <section className="zml-panel">
      <PanelTitle title="Active Setup" />
      <div className="zml-setup-list">
        <label className="zml-quick-tool">
          <span>Finder</span>
          <select
            value={activeTools?.finderId ?? ""}
            onChange={(event) => {
              const { value } = event.currentTarget;
              handleFinderChange(value);
            }}
            disabled={pending}
          >
            <option value="">Default finder</option>
            {finderTools.map((tool) => (
              <option key={tool.toolId} value={tool.toolId}>
                {tool.name}
              </option>
            ))}
          </select>
          <em>{formatMeters(activeTools?.effectiveFinderRadiusM)}</em>
        </label>
        <label className="zml-quick-tool">
          <span>Amplifier</span>
          <select
            value={activeTools?.ampId ?? ""}
            onChange={(event) => {
              const { value } = event.currentTarget;
              handleAmpChange(value);
            }}
            disabled={pending}
          >
            <option value="">No amp</option>
            {ampTools.map((tool) => (
              <option key={tool.toolId} value={tool.toolId}>
                {tool.name}
              </option>
            ))}
          </select>
          <em>{setup.amp}</em>
        </label>
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
      <MetricRow label="Claims" value={String(stats.totalClaimCount)} accent="warn" />
      <MetricRow label="Extracted" value={String(stats.depletedClaimCount)} />
      <MetricRow label="Active claims" value={String(stats.activeClaimCount)} accent="gain" />
      <MetricRow label="Cost TT" value={formatPed(stats.totalCostPed)} accent="loss" />
      <MetricRow label="Return TT" value={formatPed(stats.totalReturnPed)} accent="gain" />
      <MetricRow
        label="Profit"
        value={formatPed(stats.profitPed)}
        accent={stats.profitPed >= 0 ? "gain" : "loss"}
      />
    </section>
  );
}

function DashboardFeed({ feed }: { feed: FeedItem[] }) {
  const [filter, setFilter] = useState<DashboardFeedFilter>("activity");
  const visibleFeed = useMemo(() => filterFeed(feed, filter), [feed, filter]);

  return (
    <section className="zml-work-panel">
      <div className="zml-tabs-inline">
        {DASHBOARD_FEED_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === filter ? "is-active" : undefined}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {visibleFeed.length === 0 ? (
        <EmptyState text="No mining events yet" />
      ) : (
        <div className="zml-feed">
          {visibleFeed.map((item) => (
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
  onDelete,
}: {
  runs: RunDto[];
  activeRunId: number | null;
  pending: boolean;
  onRefresh: () => void;
  onResume: (runId: number) => void;
  onDelete: (run: RunDto) => void;
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
                    <div className="zml-table-actions">
                      <button
                        type="button"
                        className="zml-button"
                        onClick={() => onResume(run.runId)}
                        disabled={pending || run.runId === activeRunId}
                      >
                        Resume
                      </button>
                      <button
                        type="button"
                        className="zml-button zml-button-danger"
                        onClick={() => onDelete(run)}
                        disabled={pending}
                      >
                        Delete
                      </button>
                    </div>
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
    const segmentDropIds = new Set(segmentDrops.map((drop) => drop.dropId));
    const segmentClaims = claims.filter((claim) => (
      claim.segmentId === segment.segmentId ||
      (claim.segmentId === null && claim.dropId !== null && segmentDropIds.has(claim.dropId))
    ));
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
                <th>Mode</th>
                <th>Ammo</th>
                <th>Probes</th>
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
                  <td>{formatSegmentModes(readSnapshotNumber(segment.setupSnapshot, "modes_mask"))}</td>
                  <td>{formatSnapshotUnits(readSnapshotNumber(segment.setupSnapshot, "ammo_per_drop"))}</td>
                  <td>{formatSnapshotUnits(readSnapshotNumber(segment.setupSnapshot, "probes_per_drop"))}</td>
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

function LootView({ loot, totals }: { loot: MiningLootItemDto[]; totals: MiningLootTotalDto[] }) {
  const runTotals = useMemo(() => totals.filter((item) => item.scope === "run"), [totals]);
  const totalMpec = runTotals.reduce((sum, item) => sum + item.valueMpec, 0);
  const extractionCostMpec = totalExtractionCostMpec(runTotals);
  const netMpec = totalMpec - extractionCostMpec;
  const rows = useMemo(() => buildLootAggregation(runTotals), [runTotals]);
  const eventCount = runTotals.reduce((sum, item) => sum + item.eventCount, 0);

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Loot</h2>
          <span>Run return aggregation by resource/item</span>
        </div>
        <strong className="zml-section-total">{formatPedFromMpec(totalMpec)}</strong>
      </div>
      <div className="zml-claim-summary-grid">
        <ClaimSummaryCard label="Items" value={String(rows.length)} />
        <ClaimSummaryCard label="Events" value={String(eventCount)} />
        <ClaimSummaryCard label="Return" value={formatPedFromMpec(totalMpec)} />
        <ClaimSummaryCard label="Net Return" value={formatPedFromMpec(netMpec)} />
      </div>
      {rows.length === 0 ? (
        <EmptyState text="No loot recorded for this run" />
      ) : (
        <>
          <div className="zml-table-wrap">
            <table className="zml-data-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Events</th>
                  <th>Qty</th>
                  <th>Return</th>
                  <th>Extraction Cost</th>
                  <th>Net Return</th>
                  <th>Distribution</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.itemName}>
                    <td>
                      <strong>{row.itemName}</strong>
                    </td>
                    <td>{row.eventCount}</td>
                    <td>{row.qty}</td>
                    <td>{formatPedFromMpec(row.valueMpec)}</td>
                    <td>{formatPedFromMpec(row.extractionCostMpec)}</td>
                    <td>{formatPedFromMpec(row.netMpec)}</td>
                    <td>
                      <div className="zml-distribution-cell">
                        <div className="zml-distribution-bar" aria-hidden="true">
                          <span style={{ width: `${row.percent * 100}%` }} />
                        </div>
                        <strong>{formatPercent(row.percent)}</strong>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="zml-section-head zml-subsection-head">
            <div>
              <h2>Loot History</h2>
              <span>Raw chat-derived item received events</span>
              <span>Latest {loot.length} entries</span>
            </div>
          </div>
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
                    <td>{formatEventTime(item.eventDt, item.createdTsMs)}</td>
                    <td>{item.itemName}</td>
                    <td>{item.qty}</td>
                    <td>{formatPedFromMpec(item.valueMpec)}</td>
                    <td>{formatPedFromMpec(item.extractionCostMpec)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

type ClaimFilter = "all" | "ore" | "enmatter" | "treasure";

const CLAIM_FILTERS: Array<{ id: ClaimFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "ore", label: "Ore" },
  { id: "enmatter", label: "Enmatter" },
  { id: "treasure", label: "Treasure" },
];

function ClaimsView({ claims }: { claims: MiningClaimDto[] }) {
  const [filter, setFilter] = useState<ClaimFilter>("all");
  const activeClaims = useMemo(
    () => claims.filter((claim) => claim.status === "active"),
    [claims],
  );
  const depletedClaims = useMemo(
    () => claims.filter((claim) => claim.status === "depleted"),
    [claims],
  );
  const ignoredClaims = useMemo(
    () => claims.filter((claim) => claim.status === "ignored"),
    [claims],
  );
  const expiredClaims = useMemo(
    () => claims.filter((claim) => claim.status === "expired"),
    [claims],
  );
  const countedClaims = useMemo(
    () => claims.filter((claim) => claim.status !== "ignored"),
    [claims],
  );
  const filteredHistory = useMemo(
    () => sortClaimHistory(
      filter === "all" ? claims : claims.filter((claim) => claim.miningType === filter),
    ),
    [claims, filter],
  );
  const rows = useMemo(
    () => buildClaimDistribution(activeClaims, filter),
    [activeClaims, filter],
  );
  const visibleTotal = rows.reduce((sum, row) => sum + row.count, 0);

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Claims</h2>
          <span>Active distribution and run claim history</span>
        </div>
      </div>
      <div className="zml-tabs-inline">
        {CLAIM_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === filter ? "is-active" : undefined}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="zml-claim-summary-grid">
        <ClaimSummaryCard label="Total" value={String(countedClaims.length)} />
        <ClaimSummaryCard label="Active" value={String(activeClaims.length)} />
        <ClaimSummaryCard label="Extracted" value={String(depletedClaims.length)} />
        <ClaimSummaryCard label="Expired" value={String(expiredClaims.length)} />
        <ClaimSummaryCard label="Ignored" value={String(ignoredClaims.length)} />
        <ClaimSummaryCard label="Visible Active" value={String(visibleTotal)} />
      </div>

      <div className="zml-section-head zml-subsection-head">
        <div>
          <h2>Active Distribution</h2>
          <span>Map-visible claims only</span>
        </div>
      </div>
      {activeClaims.length === 0 ? (
        <EmptyState text="No active claims" compact />
      ) : rows.length === 0 ? (
        <EmptyState text="No active claims for this filter" compact />
      ) : (
        <div className="zml-table-wrap">
          <table className="zml-data-table">
            <thead>
              <tr>
                <th>Resource</th>
                <th>Type</th>
                <th>Claims</th>
                <th>Distribution</th>
                <th>Next Expires</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.miningType ?? "unknown"}:${row.resourceName}`}>
                  <td>
                    <strong>{row.resourceName}</strong>
                  </td>
                  <td>{formatMiningType(row.miningType)}</td>
                  <td>{row.count}</td>
                  <td>
                    <div className="zml-distribution-cell">
                      <div className="zml-distribution-bar" aria-hidden="true">
                        <span style={{ width: `${row.percent * 100}%` }} />
                      </div>
                      <strong>{formatPercent(row.percent)}</strong>
                    </div>
                  </td>
                  <td>{formatExpires(row.nextExpiresTsMs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="zml-section-head zml-subsection-head">
        <div>
          <h2>Claim History</h2>
          <span>Extracted claims stay here for run and segment stats</span>
        </div>
      </div>
      {filteredHistory.length === 0 ? (
        <EmptyState text="No claim history for this filter" compact />
      ) : (
        <div className="zml-table-wrap">
          <table className="zml-data-table">
            <thead>
              <tr>
                <th>Found</th>
                <th>Resource</th>
                <th>Type</th>
                <th>Size</th>
                <th>Status</th>
                <th>Segment</th>
                <th>Depleted</th>
              </tr>
            </thead>
            <tbody>
              {filteredHistory.map((claim) => (
                <tr key={claim.claimId}>
                  <td>{formatTime(claim.observedTsMs)}</td>
                  <td>
                    <strong>{claim.resourceName ?? "Unknown resource"}</strong>
                  </td>
                  <td>{formatMiningType(claim.miningType)}</td>
                  <td>{formatSize(claim.sizeLabel, claim.sizeIndex)}</td>
                  <td>
                    <span className={claimStatusClassName(claim)}>{formatClaimStatus(claim)}</span>
                  </td>
                  <td>{formatSegmentRef(claim.segmentId)}</td>
                  <td>{formatClaimDepletion(claim)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const CLAIM_SIZE_ALERT_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: "Disabled" },
  { value: 1, label: "Minimal I" },
  { value: 2, label: "Tiny II" },
  { value: 3, label: "Very Poor III" },
  { value: 4, label: "Poor IV" },
  { value: 5, label: "Small V" },
  { value: 6, label: "Modest VI" },
  { value: 7, label: "Average VII" },
  { value: 8, label: "Medium VIII" },
  { value: 9, label: "Ample IX" },
  { value: 10, label: "Considerable X" },
  { value: 11, label: "Sizable XI" },
  { value: 12, label: "Large XII" },
  { value: 13, label: "Abundant XIII" },
  { value: 14, label: "Great XIV" },
  { value: 15, label: "Substantial XV" },
  { value: 16, label: "Significant XVI" },
  { value: 17, label: "Plentiful XVII" },
  { value: 18, label: "Huge XVIII" },
  { value: 19, label: "Extremely Large XIX" },
  { value: 20, label: "Massive XX" },
  { value: 21, label: "Vast XXI" },
  { value: 22, label: "Enormous XXII" },
  { value: 23, label: "Rich XXIII" },
  { value: 24, label: "Gigantic XXIV" },
  { value: 25, label: "Mammoth XXV" },
  { value: 26, label: "Colossal XXVI" },
  { value: 27, label: "Immense XXVII" },
];

function MapSettingsView({ position }: { position: WorldPosDTO | null }) {
  const [preferences, setPreferences] = useMapPreferences();
  const currentAnchorLabel = preferences.hexGridAnchor === "player-offset"
    ? formatAnchorPoint(preferences.hexGridAnchorPoint)
    : "Fixed map origin";

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Map</h2>
          <span>Hexgrid, map markers, and claim alerts</span>
        </div>
      </div>

      <div className="zml-overlay-settings">
        <div className="zml-setting-row">
          <div>
            <strong>Drop circles TTL</strong>
            <span>{formatMinutesPreference(preferences.dropRadiusTtlMinutes)}</span>
          </div>
          <select
            value={String(preferences.dropRadiusTtlMinutes)}
            onChange={(event) => {
              const value = Number(event.currentTarget.value);
              setPreferences((current) => ({ ...current, dropRadiusTtlMinutes: value }));
            }}
          >
            <option value="15">15 minutes</option>
            <option value="30">30 minutes</option>
            <option value="60">60 minutes</option>
            <option value="120">2 hours</option>
            <option value="0">Always</option>
          </select>
        </div>

        <div className="zml-setting-row">
          <div>
            <strong>Hexgrid mode</strong>
            <span>{preferences.hexGridEnabled ? formatHexGridMode(preferences.hexGridMode) : "Hidden"}</span>
          </div>
          <div className="zml-settings-stack">
            <SettingsCheckbox
              label="Show hexgrid"
              checked={preferences.hexGridEnabled}
              onChange={(checked) =>
                setPreferences((current) => ({ ...current, hexGridEnabled: checked }))
              }
            />
            <select
              value={preferences.hexGridMode}
              onChange={(event) => {
                const value = event.currentTarget.value === "no-overlap"
                  ? "no-overlap"
                  : "max-coverage";
                setPreferences((current) => ({ ...current, hexGridMode: value }));
              }}
            >
              <option value="max-coverage">Max coverage</option>
              <option value="no-overlap">No overlap</option>
            </select>
          </div>
        </div>

        <div className="zml-setting-row">
          <div>
            <strong>Hexgrid anchor</strong>
            <span>{currentAnchorLabel}</span>
          </div>
          <div className="zml-settings-stack">
            <button
              type="button"
              className="zml-button"
              onClick={() => {
                if (position === null) return;
                setPreferences((current) => ({
                  ...current,
                  hexGridEnabled: true,
                  hexGridAnchor: "player-offset",
                  hexGridAnchorPoint: {
                    planetName: position.planetName,
                    x: position.x,
                    y: position.y,
                  },
                }));
              }}
              disabled={position === null}
            >
              Set offset from current player position
            </button>
            <button
              type="button"
              className="zml-button"
              onClick={() => {
                setPreferences((current) => ({
                  ...current,
                  hexGridAnchor: "map",
                  hexGridAnchorPoint: null,
                }));
              }}
            >
              Use map origin
            </button>
          </div>
        </div>

        <div className="zml-setting-row">
          <div>
            <strong>Hexgrid orientation</strong>
            <span>{preferences.hexGridOrientation === "vertical" ? "Vertical" : "Horizontal"}</span>
          </div>
          <select
            value={preferences.hexGridOrientation}
            onChange={(event) => {
              const value = event.currentTarget.value === "horizontal"
                ? "horizontal"
                : "vertical";
              setPreferences((current) => ({ ...current, hexGridOrientation: value }));
            }}
          >
            <option value="vertical">Vertical</option>
            <option value="horizontal">Horizontal</option>
          </select>
        </div>

        <div className="zml-setting-row">
          <div>
            <strong>Small claim sound</strong>
            <span>{preferences.smallClaimSoundEnabled ? "Enabled" : "Muted"}</span>
          </div>
          <div className="zml-settings-stack">
            <SettingsCheckbox
              label="Play alert"
              checked={preferences.smallClaimSoundEnabled}
              onChange={(checked) =>
                setPreferences((current) => ({ ...current, smallClaimSoundEnabled: checked }))
              }
            />
            <select
              value={String(preferences.smallClaimSizeThreshold)}
              onChange={(event) => {
                const value = Number(event.currentTarget.value);
                setPreferences((current) => ({ ...current, smallClaimSizeThreshold: value }));
              }}
            >
              {CLAIM_SIZE_ALERT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button type="button" className="zml-button" onClick={playSmallClaimSound}>
              Test sound
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

const OVERLAY_METRICS: Array<{ key: OverlayMetricKey; label: string }> = [
  { key: "cost", label: "Cost" },
  { key: "return", label: "Return" },
  { key: "profit", label: "Profit" },
  { key: "hitRate", label: "Hit Rate" },
];

function OverlaySettingsView() {
  const [preferences, setPreferences] = useOverlayPreferences();

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Overlay</h2>
          <span>Streaming overlay display options</span>
        </div>
      </div>

      <div className="zml-overlay-settings">
        <div className="zml-setting-row">
          <div>
            <strong>Font size</strong>
            <span>{preferences.fontSizePx}px</span>
          </div>
          <input
            type="range"
            min={10}
            max={28}
            value={preferences.fontSizePx}
            onChange={(event) => {
              setPreferences((current) => ({
                ...current,
                fontSizePx: Number(event.currentTarget.value),
              }));
            }}
          />
        </div>

        <div className="zml-toggle-list">
          <SettingsCheckbox
            label="Run name"
            checked={preferences.showRunName}
            onChange={(checked) =>
              setPreferences((current) => ({ ...current, showRunName: checked }))
            }
          />
          <SettingsCheckbox
            label="Live status"
            checked={preferences.showStatus}
            onChange={(checked) =>
              setPreferences((current) => ({ ...current, showStatus: checked }))
            }
          />
          {OVERLAY_METRICS.map((metric) => (
            <SettingsCheckbox
              key={metric.key}
              label={metric.label}
              checked={preferences.metrics[metric.key]}
              onChange={(checked) =>
                setPreferences((current) => ({
                  ...current,
                  metrics: {
                    ...current.metrics,
                    [metric.key]: checked,
                  },
                }))
              }
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function SettingsCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="zml-overlay-checkbox">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.currentTarget.checked)}
      />
      <span>{label}</span>
    </label>
  );
}

function ClaimSummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="zml-claim-summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DebugView({
  stateSnapshot,
  onCheckHealth,
}: {
  stateSnapshot: ZmlRendererState;
  onCheckHealth: () => void;
}) {
  const health = stateSnapshot.agentHealth;
  const workers = health ? Object.entries(health.workers) : [];
  const latestDrops = stateSnapshot.miningDrops.slice(0, 5);
  const latestClaims = stateSnapshot.miningClaims.slice(0, 5);

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Debug</h2>
          <span>Operational state without the JSON wall first</span>
        </div>
        <button type="button" className="zml-button" onClick={onCheckHealth}>
          {stateSnapshot.agentHealthChecking ? "Checking..." : "Check Health"}
        </button>
      </div>

      <div className="zml-debug-grid">
        <DebugCard title="Streams">
          <DebugMetric label="Agent" value={stateSnapshot.agent.status} tone={stateSnapshot.agent.status === "connected" ? "ok" : "warn"} />
          <DebugMetric label="WS" value={stateSnapshot.streams.ws ? "connected" : "offline"} tone={stateSnapshot.streams.ws ? "ok" : "warn"} />
          <DebugMetric label="SSE" value={stateSnapshot.streams.sse ? "connected" : "offline"} tone={stateSnapshot.streams.sse ? "ok" : "warn"} />
          <DebugMetric label="Last error" value={stateSnapshot.lastCommandError ?? stateSnapshot.agent.lastError ?? "-"} />
        </DebugCard>

        <DebugCard title="Run">
          <DebugMetric label="Active run" value={stateSnapshot.activeRun?.name ?? "-"} />
          <DebugMetric label="Run status" value={stateSnapshot.activeRun?.status ?? "idle"} />
          <DebugMetric label="Segments" value={String(stateSnapshot.runSegments.length)} />
          <DebugMetric label="Runs cached" value={String(stateSnapshot.runs.length)} />
        </DebugCard>

        <DebugCard title="Mining Cache">
          <DebugMetric label="Drops" value={String(stateSnapshot.miningDrops.length)} />
          <DebugMetric label="Claims" value={String(stateSnapshot.miningClaims.length)} />
          <DebugMetric label="Active claims" value={String(stateSnapshot.miningClaims.filter((claim) => claim.status === "active").length)} tone="ok" />
          <DebugMetric label="Loot rows" value={String(stateSnapshot.miningLoot.length)} />
        </DebugCard>

        <DebugCard title="Position">
          <DebugMetric label="Planet" value={stateSnapshot.position?.position.planetName || "-"} />
          <DebugMetric label="Coords" value={formatPosition(stateSnapshot.position?.position)} />
          <DebugMetric label="Seq" value={stateSnapshot.positionEvent?.seq === undefined ? "-" : String(stateSnapshot.positionEvent.seq)} />
          <DebugMetric label="Position ts" value={stateSnapshot.position?.tsMs === undefined ? "-" : formatTime(stateSnapshot.position.tsMs)} />
        </DebugCard>
      </div>

      <div className="zml-debug-grid is-wide">
        <DebugCard title="Workers">
          {workers.length === 0 ? (
            <EmptyState text="No health snapshot yet" compact />
          ) : (
            <div className="zml-debug-worker-list">
              {workers.map(([name, worker]) => (
                <div key={name} className="zml-debug-worker">
                  <strong>{name}</strong>
                  <span className={worker.state === "running" ? "is-ok" : "is-warn"}>
                    {worker.enabled ? worker.state : "disabled"}
                  </span>
                  <small>{worker.lastError ?? formatTime(worker.lastSeenTsMs)}</small>
                </div>
              ))}
            </div>
          )}
        </DebugCard>

        <DebugCard title="Recent Drops">
          <DebugList
            rows={latestDrops.map((drop) => ({
              id: drop.dropId,
              left: formatTime(drop.observedTsMs),
              main: drop.result,
              right: formatPosition(drop.position),
            }))}
            empty="No drops cached"
          />
        </DebugCard>

        <DebugCard title="Recent Claims">
          <DebugList
            rows={latestClaims.map((claim) => ({
              id: claim.claimId,
              left: formatTime(claim.observedTsMs),
              main: claim.resourceName ?? "Unknown resource",
              right: claim.status,
            }))}
            empty="No claims cached"
          />
        </DebugCard>
      </div>

      <details className="zml-debug-raw">
        <summary>Raw state snapshot</summary>
        <pre className="zml-debug-json">{JSON.stringify(stateSnapshot, null, 2)}</pre>
      </details>
    </section>
  );
}

function DebugCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="zml-debug-card">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function DebugMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}) {
  return (
    <div className="zml-debug-metric">
      <span>{label}</span>
      <strong className={tone ? `is-${tone}` : undefined}>{value}</strong>
    </div>
  );
}

function DebugList({
  rows,
  empty,
}: {
  rows: Array<{ id: string; left: string; main: string; right: string }>;
  empty: string;
}) {
  if (rows.length === 0) return <EmptyState text={empty} compact />;

  return (
    <div className="zml-debug-list">
      {rows.map((row) => (
        <div key={row.id} className="zml-debug-list-row">
          <time>{row.left}</time>
          <strong>{row.main}</strong>
          <span>{row.right}</span>
        </div>
      ))}
    </div>
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

function useSmallClaimSoundAlert(
  claims: readonly MiningClaimDto[],
  preferences: MapPreferences,
): void {
  const initializedRef = useRef(false);
  const seenClaimIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!initializedRef.current) {
      for (const claim of claims) {
        seenClaimIdsRef.current.add(claim.claimId);
      }
      initializedRef.current = true;
      return;
    }

    let shouldPlay = false;
    for (const claim of claims) {
      if (seenClaimIdsRef.current.has(claim.claimId)) continue;
      seenClaimIdsRef.current.add(claim.claimId);
      if (shouldPlaySmallClaimSound(claim, preferences)) {
        shouldPlay = true;
      }
    }

    if (shouldPlay) {
      playSmallClaimSound();
    }
  }, [
    claims,
    preferences.smallClaimSizeThreshold,
    preferences.smallClaimSoundEnabled,
  ]);
}

function shouldPlaySmallClaimSound(
  claim: MiningClaimDto,
  preferences: MapPreferences,
): boolean {
  return (
    preferences.smallClaimSoundEnabled &&
    preferences.smallClaimSizeThreshold > 0 &&
    claim.status === "active" &&
    claim.sizeIndex !== null &&
    claim.sizeIndex <= preferences.smallClaimSizeThreshold
  );
}

function playSmallClaimSound(): void {
  const AudioContextCtor =
    window.AudioContext ??
    (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) return;

  try {
    const context = new AudioContextCtor();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const startedAt = context.currentTime;

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, startedAt);
    oscillator.frequency.exponentialRampToValueAtTime(660, startedAt + 0.18);
    gain.gain.setValueAtTime(0.0001, startedAt);
    gain.gain.exponentialRampToValueAtTime(0.65, startedAt + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, startedAt + 0.22);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(startedAt);
    oscillator.stop(startedAt + 0.24);
    oscillator.onended = () => {
      void context.close();
    };
  } catch {
    // Browser audio can be blocked until the first user interaction.
  }
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
  totalClaimCount: number;
  activeClaimCount: number;
  depletedClaimCount: number;
  hitRate: number | null;
  totalCostPed: number;
  totalReturnPed: number;
  profitPed: number;
};

type ClaimDistributionRow = {
  resourceName: string;
  miningType: MiningResourceType | null;
  count: number;
  percent: number;
  nextExpiresTsMs: number | null;
};

type LootAggregationRow = {
  itemName: string;
  eventCount: number;
  qty: number;
  valueMpec: number;
  extractionCostMpec: number;
  netMpec: number;
  percent: number;
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

function buildClaimDistribution(
  claims: MiningClaimDto[],
  filter: ClaimFilter,
): ClaimDistributionRow[] {
  const filteredClaims =
    filter === "all" ? claims : claims.filter((claim) => claim.miningType === filter);
  const total = filteredClaims.length;
  const rows = new Map<string, ClaimDistributionRow>();

  for (const claim of filteredClaims) {
    const resourceName = claim.resourceName ?? "Unknown resource";
    const miningType = claim.miningType;
    const key = `${miningType ?? "unknown"}:${resourceName}`;
    const current = rows.get(key);
    const nextExpiresTsMs = minNullableTs(
      current?.nextExpiresTsMs ?? null,
      claim.expectedExpiresTsMs,
    );

    rows.set(key, {
      resourceName,
      miningType,
      count: (current?.count ?? 0) + 1,
      percent: 0,
      nextExpiresTsMs,
    });
  }

  return [...rows.values()]
    .map((row) => ({
      ...row,
      percent: total === 0 ? 0 : row.count / total,
    }))
    .sort((a, b) => b.count - a.count || a.resourceName.localeCompare(b.resourceName));
}

function buildLootAggregation(totals: MiningLootTotalDto[]): LootAggregationRow[] {
  const totalMpec = totals.reduce((sum, item) => sum + item.valueMpec, 0);
  return totals
    .map((item) => ({
      itemName: item.itemName,
      eventCount: item.eventCount,
      qty: item.qty,
      valueMpec: item.valueMpec,
      extractionCostMpec: item.extractionCostMpec,
      netMpec: item.valueMpec - item.extractionCostMpec,
      percent: 0,
    }))
    .map((row) => ({
      ...row,
      percent: totalMpec === 0 ? 0 : row.valueMpec / totalMpec,
    }))
    .sort((a, b) => b.valueMpec - a.valueMpec || a.itemName.localeCompare(b.itemName));
}

function minNullableTs(left: number | null, right: number | null): number | null {
  if (left === null) return right;
  if (right === null) return left;
  return Math.min(left, right);
}

function sortClaimHistory(claims: MiningClaimDto[]): MiningClaimDto[] {
  return [...claims].sort((a, b) => claimActivityTsMs(b) - claimActivityTsMs(a));
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

function emptyStringToNull(value: string): string | null {
  return value === "" ? null : value;
}

function getRunStats(
  drops: MiningDropDto[],
  claims: MiningClaimDto[],
  lootTotals: MiningLootTotalDto[],
): RunStats {
  const runLootTotals = lootTotals.filter((item) => item.scope === "run");
  const hitCount = drops.filter((drop) => drop.result === "hit").length;
  const noResourceCount = drops.filter((drop) => drop.result === "no_resources").length;
  const activeClaimCount = claims.filter((claim) => claim.status === "active").length;
  const depletedClaimCount = claims.filter((claim) => claim.status === "depleted").length;
  const totalClaimCount = claims.filter((claim) => claim.status !== "ignored").length;
  const totalCostPed =
    (drops.reduce((sum, drop) => sum + drop.cost.totalMpec, 0) + totalExtractionCostMpec(runLootTotals)) /
    100_000;
  const totalReturnPed = runLootTotals.reduce((sum, item) => sum + item.valueMpec, 0) / 100_000;

  return {
    dropCount: drops.length,
    hitCount,
    noResourceCount,
    totalClaimCount,
    activeClaimCount,
    depletedClaimCount,
    hitRate: drops.length === 0 ? null : hitCount / drops.length,
    totalCostPed,
    totalReturnPed,
    profitPed: totalReturnPed - totalCostPed,
  };
}

function buildFeed(
  drops: MiningDropDto[],
  claims: MiningClaimDto[],
  loot: MiningLootItemDto[],
): FeedItem[] {
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
    const isDepleted = claim.status === "depleted";
    const isIgnored = claim.status === "ignored";
    const isExpired = claim.status === "expired";
    items.push({
      id: `${claim.claimId}:claim:${claim.status}`,
      tsMs: claimActivityTsMs(claim),
      kind: isIgnored ? "ignored" : isExpired ? "expired" : isDepleted ? "depleted" : "claim",
      title: isIgnored
        ? "Claim Ignored"
        : isExpired
          ? "Claim Expired"
          : isDepleted
            ? "Claim Extracted"
            : "Claim Recorded",
      detail: `${claim.resourceName ?? "Unknown resource"} ${formatSize(claim.sizeLabel, claim.sizeIndex)}`,
      amount: isIgnored
        ? "hidden"
        : isExpired
          ? "expired"
          : isDepleted
            ? formatMeters(claim.depletedDistanceM)
            : formatExpires(claim.expectedExpiresTsMs),
    });
  }

  for (const item of loot) {
    items.push({
      id: `${item.eventId}:${item.createdTsMs}:loot`,
      tsMs: lootActivityTsMs(item),
      kind: "loot",
      title: "Item Received",
      detail: `${item.itemName} x${item.qty}`,
      amount: formatPedFromMpec(item.valueMpec),
    });
  }

  return items.sort((a, b) => b.tsMs - a.tsMs);
}

function filterFeed(feed: FeedItem[], filter: DashboardFeedFilter): FeedItem[] {
  if (filter === "all") return feed.slice(0, MAX_DASHBOARD_FEED_ITEMS);
  if (filter === "activity") {
    return feed
      .filter((item) => item.kind !== "loot" && item.kind !== "hit")
      .slice(0, MAX_DASHBOARD_FEED_ITEMS);
  }
  if (filter === "drops") {
    return feed
      .filter((item) => item.kind === "drop" || item.kind === "miss")
      .slice(0, MAX_DASHBOARD_FEED_ITEMS);
  }
  if (filter === "claims") {
    return feed
      .filter(
        (item) =>
          item.kind === "hit" ||
          item.kind === "claim" ||
          item.kind === "depleted" ||
          item.kind === "expired" ||
          item.kind === "ignored",
      )
      .slice(0, MAX_DASHBOARD_FEED_ITEMS);
  }
  return feed.filter((item) => item.kind === "loot").slice(0, MAX_DASHBOARD_FEED_ITEMS);
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

function formatMinutesPreference(minutes: number): string {
  if (minutes <= 0) return "Always visible";
  if (minutes < 60) return `${minutes}m`;
  const hours = minutes / 60;
  return Number.isInteger(hours) ? `${hours}h` : `${minutes}m`;
}

function formatHexGridMode(value: "no-overlap" | "max-coverage"): string {
  return value === "no-overlap" ? "No overlap" : "Max coverage";
}

function formatAnchorPoint(point: { planetName?: string; x: number; y: number } | null): string {
  if (point === null) return "Player offset not set";
  const planet = point.planetName ? `${point.planetName} ` : "";
  return `${planet}${point.x}, ${point.y}`;
}

function formatSegmentRef(segmentId: string | null): string {
  if (segmentId === null) return "-";
  return segmentId.length <= 8 ? segmentId : segmentId.slice(0, 8);
}

function formatClaimDepletion(claim: MiningClaimDto): string {
  if (claim.status !== "depleted") return "-";
  const distance = formatMeters(claim.depletedDistanceM);
  if (claim.depletedEventDt === null) return distance;
  const when = formatDateTimeString(claim.depletedEventDt);
  if (distance === "-") return when;
  return `${when} / ${distance}`;
}

function claimStatusClassName(claim: MiningClaimDto): string {
  if (claim.status === "active") return "zml-tag is-active";
  if (claim.status === "depleted") return "zml-tag is-depleted";
  if (claim.status === "expired") return "zml-tag is-expired";
  return "zml-tag is-ignored";
}

function formatClaimStatus(claim: MiningClaimDto): string {
  if (claim.status === "active") return "active";
  if (claim.status === "depleted") return "extracted";
  if (claim.status === "expired") return "expired";
  return "ignored";
}

function claimActivityTsMs(claim: MiningClaimDto): number {
  if (claim.status === "expired" && claim.expectedExpiresTsMs !== null) {
    return claim.expectedExpiresTsMs;
  }
  if (claim.status !== "depleted" || claim.depletedEventDt === null) {
    return claim.observedTsMs;
  }
  const parsed = Date.parse(claim.depletedEventDt);
  return Number.isFinite(parsed) ? parsed : claim.observedTsMs;
}

function lootActivityTsMs(item: MiningLootItemDto): number {
  if (item.eventDt === null) return item.createdTsMs;
  const parsed = Date.parse(item.eventDt);
  return Number.isFinite(parsed) ? parsed : item.createdTsMs;
}

function formatDateTimeString(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? formatTime(parsed) : value;
}

function formatMiningType(value: MiningResourceType | null): string {
  if (value === "ore") return "Ore";
  if (value === "enmatter") return "Enmatter";
  if (value === "treasure") return "Treasure";
  if (value === "other") return "Other";
  return "Unknown";
}

function formatPedFromMpec(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return formatPed(value / 100_000);
}

function totalExtractionCostMpec(lootTotals: MiningLootTotalDto[]): number {
  return lootTotals.reduce((sum, item) => sum + item.extractionCostMpec, 0);
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

function formatEventTime(eventDt: string | null, fallbackTsMs: number): string {
  if (eventDt === null) return formatTime(fallbackTsMs);
  return formatDateTimeString(eventDt);
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

function readToolSnapshotName(snapshot: Record<string, unknown>, key: "finder" | "amp"): string {
  const value = snapshot[key];
  if (!isRecord(value)) return key === "amp" ? "No amp" : "-";
  return typeof value.name === "string" ? value.name : "-";
}

function readSnapshotNumber(snapshot: Record<string, unknown>, key: string): number | null {
  const value = snapshot[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatSegmentModes(mask: number | null): string {
  if (mask === null) return "-";
  if (mask === 0) return "None";

  const labels: string[] = [];
  if ((mask & 1) !== 0) labels.push("Ore");
  if ((mask & 2) !== 0) labels.push("Enmatter");
  if ((mask & 4) !== 0) labels.push("Treasure");

  const unknownMask = mask & ~7;
  if (unknownMask !== 0) labels.push(`Unknown ${unknownMask}`);
  return labels.length > 0 ? labels.join(" + ") : `Unknown ${mask}`;
}

function formatSnapshotUnits(value: number | null): string {
  if (value === null) return "-";
  return value.toLocaleString();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
