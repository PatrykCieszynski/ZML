import { useMemo, useState } from "react";
import type {
  MiningClaimDto,
  MiningDropDto,
  MiningToolProfileDto,
  RunDto,
  RunSegmentDto,
  SplitRunSegmentRequest,
} from "@desktop/shared";
import "./segmentsView.css";

type SegmentRow = {
  segment: RunSegmentDto;
  dropCount: number;
  claimCount: number;
  ttCostPed: number;
  withMarkupCostPed: number;
};

type CorrectionDialog =
  | { kind: "split"; row: SegmentRow }
  | { kind: "move"; row: SegmentRow }
  | null;

const KEEP_TOOL = "__keep__";
const NO_AMP = "__none__";

export function SegmentsView({
  segments,
  drops,
  claims,
  tools,
  runs,
}: {
  segments: RunSegmentDto[];
  drops: MiningDropDto[];
  claims: MiningClaimDto[];
  tools: MiningToolProfileDto[];
  runs: RunDto[];
}) {
  const [busySegmentId, setBusySegmentId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<CorrectionDialog>(null);
  const [error, setError] = useState<string | null>(null);
  const finders = useMemo(
    () => tools.filter((tool) => tool.kind === "finder").sort(compareToolNames),
    [tools],
  );
  const amps = useMemo(
    () => tools.filter((tool) => tool.kind === "amp").sort(compareToolNames),
    [tools],
  );
  const segmentRows = useMemo(
    () => buildSegmentRows(segments, drops, claims),
    [segments, drops, claims],
  );

  const correctFinder = async (row: SegmentRow, toolId: string) => {
    const tool = finders.find((item) => item.toolId === toolId);
    if (!tool) return;
    if (!window.confirm(
      `Apply ${tool.name} to all ${row.dropCount} drops in segment #${row.segment.segmentIndex}? Costs and finder radius will be recalculated.`,
    )) return;
    await runCorrection(row.segment.segmentId, async () => {
      await window.zml.updateRunSegmentSetup(row.segment.runId, row.segment.segmentId, {
        finderToolId: tool.toolId,
      });
    });
  };

  const correctAmp = async (row: SegmentRow, value: string) => {
    const tool = value === NO_AMP ? null : amps.find((item) => item.toolId === value) ?? null;
    const label = tool?.name ?? "No amp";
    if (!window.confirm(
      `Apply ${label} to all ${row.dropCount} drops in segment #${row.segment.segmentIndex}? Costs will be recalculated.`,
    )) return;
    await runCorrection(row.segment.segmentId, async () => {
      await window.zml.updateRunSegmentSetup(row.segment.runId, row.segment.segmentId, {
        ampToolId: tool?.toolId ?? null,
      });
    });
  };

  const runCorrection = async (segmentId: string, action: () => Promise<void>) => {
    setBusySegmentId(segmentId);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusySegmentId(null);
    }
  };

  return (
    <section className="zml-work-panel">
      <div className="zml-section-head">
        <div>
          <h2>Segments</h2>
          <span>Current run · click Finder/Amp to correct a whole segment</span>
        </div>
      </div>
      {error && <div className="zml-segment-error">{error}</div>}
      {segmentRows.length === 0 ? (
        <div className="zml-segment-empty">No segments yet</div>
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
                <th>Cost incl. MU</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {segmentRows.map((row) => {
                const currentFinderName = readToolSnapshotName(row.segment.setupSnapshot, "finder");
                const currentAmpName = readToolSnapshotName(row.segment.setupSnapshot, "amp");
                const finderValue = matchingToolId(finders, currentFinderName) ?? KEEP_TOOL;
                const ampValue = currentAmpName === "-"
                  ? NO_AMP
                  : matchingToolId(amps, currentAmpName) ?? KEEP_TOOL;
                const busy = busySegmentId === row.segment.segmentId;
                return (
                  <tr key={row.segment.segmentId}>
                    <td>#{row.segment.segmentIndex}</td>
                    <td>
                      <span className={row.segment.status === "active" ? "zml-tag is-active" : "zml-tag"}>
                        {row.segment.status}
                      </span>
                    </td>
                    <td>{formatTime(row.segment.startedTsMs)}</td>
                    <td>{row.segment.endedTsMs === null ? "-" : formatTime(row.segment.endedTsMs)}</td>
                    <td>
                      <select
                        className="zml-segment-tool-select"
                        value={finderValue}
                        disabled={busy}
                        onChange={(event) => void correctFinder(row, event.currentTarget.value)}
                      >
                        {finderValue === KEEP_TOOL && (
                          <option value={KEEP_TOOL}>{currentFinderName}</option>
                        )}
                        {finders.map((tool) => (
                          <option key={tool.toolId} value={tool.toolId}>{tool.name}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <select
                        className="zml-segment-tool-select"
                        value={ampValue}
                        disabled={busy}
                        onChange={(event) => void correctAmp(row, event.currentTarget.value)}
                      >
                        {ampValue === KEEP_TOOL && (
                          <option value={KEEP_TOOL}>{currentAmpName}</option>
                        )}
                        <option value={NO_AMP}>No amp</option>
                        {amps.map((tool) => (
                          <option key={tool.toolId} value={tool.toolId}>{tool.name}</option>
                        ))}
                      </select>
                    </td>
                    <td>{formatSegmentModes(readSnapshotNumber(row.segment.setupSnapshot, "modes_mask"))}</td>
                    <td>{formatSnapshotUnits(readSnapshotNumber(row.segment.setupSnapshot, "ammo_per_drop"))}</td>
                    <td>{formatSnapshotUnits(readSnapshotNumber(row.segment.setupSnapshot, "probes_per_drop"))}</td>
                    <td>{row.dropCount}</td>
                    <td>{row.claimCount}</td>
                    <td>{formatPed(row.ttCostPed)}</td>
                    <td>{formatPed(row.withMarkupCostPed)}</td>
                    <td>
                      <details className="zml-segment-actions">
                        <summary aria-label={`Correct segment ${row.segment.segmentIndex}`}>⋯</summary>
                        <div className="zml-segment-actions-popout">
                          <button
                            type="button"
                            disabled={busy || row.dropCount < 2}
                            onClick={() => setDialog({ kind: "split", row })}
                          >
                            Split segment
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setDialog({ kind: "move", row })}
                          >
                            Move to run
                          </button>
                        </div>
                      </details>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {dialog?.kind === "split" && (
        <SplitSegmentDialog
          row={dialog.row}
          finders={finders}
          amps={amps}
          busy={busySegmentId === dialog.row.segment.segmentId}
          onCancel={() => setDialog(null)}
          onSubmit={async (request) => {
            await runCorrection(dialog.row.segment.segmentId, async () => {
              await window.zml.splitRunSegment(
                dialog.row.segment.runId,
                dialog.row.segment.segmentId,
                request,
              );
              setDialog(null);
            });
          }}
        />
      )}
      {dialog?.kind === "move" && (
        <MoveSegmentDialog
          row={dialog.row}
          runs={runs}
          busy={busySegmentId === dialog.row.segment.segmentId}
          onCancel={() => setDialog(null)}
          onSubmit={async (request) => {
            await runCorrection(dialog.row.segment.segmentId, async () => {
              await window.zml.moveRunSegment(
                dialog.row.segment.runId,
                dialog.row.segment.segmentId,
                request,
              );
              setDialog(null);
            });
          }}
        />
      )}
    </section>
  );
}

function SplitSegmentDialog({
  row,
  finders,
  amps,
  busy,
  onCancel,
  onSubmit,
}: {
  row: SegmentRow;
  finders: MiningToolProfileDto[];
  amps: MiningToolProfileDto[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (request: SplitRunSegmentRequest) => Promise<void>;
}) {
  const [selection, setSelection] = useState<"first" | "last">("first");
  const [dropCount, setDropCount] = useState(1);
  const [finderToolId, setFinderToolId] = useState(KEEP_TOOL);
  const [ampToolId, setAmpToolId] = useState(KEEP_TOOL);
  const maxDrops = Math.max(1, row.dropCount - 1);
  const safeDropCount = Math.min(maxDrops, Math.max(1, dropCount));

  const submit = async () => {
    const request: SplitRunSegmentRequest = {
      selection,
      dropCount: safeDropCount,
      ...(finderToolId === KEEP_TOOL ? {} : { finderToolId }),
      ...(ampToolId === KEEP_TOOL
        ? {}
        : { ampToolId: ampToolId === NO_AMP ? null : ampToolId }),
    };
    await onSubmit(request);
  };

  return (
    <div className="zml-segment-dialog-backdrop" role="presentation" onMouseDown={onCancel}>
      <div className="zml-segment-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="zml-segment-dialog-head">
          <div>
            <strong>Split segment #{row.segment.segmentIndex}</strong>
            <span>Move part of this segment into a corrected setup bucket.</span>
          </div>
          <button type="button" onClick={onCancel} aria-label="Close">×</button>
        </div>
        <label>
          Drops to move
          <div className="zml-segment-inline-fields">
            <select value={selection} onChange={(event) => setSelection(event.currentTarget.value as "first" | "last")}>
              <option value="first">First</option>
              <option value="last">Last</option>
            </select>
            <input
              type="number"
              min={1}
              max={maxDrops}
              value={dropCount}
              onChange={(event) => setDropCount(Number(event.currentTarget.value))}
            />
            <span>of {row.dropCount}</span>
          </div>
        </label>
        <label>
          Finder
          <select value={finderToolId} onChange={(event) => setFinderToolId(event.currentTarget.value)}>
            <option value={KEEP_TOOL}>Keep {readToolSnapshotName(row.segment.setupSnapshot, "finder")}</option>
            {finders.map((tool) => <option key={tool.toolId} value={tool.toolId}>{tool.name}</option>)}
          </select>
        </label>
        <label>
          Amp
          <select value={ampToolId} onChange={(event) => setAmpToolId(event.currentTarget.value)}>
            <option value={KEEP_TOOL}>Keep {readToolSnapshotName(row.segment.setupSnapshot, "amp")}</option>
            <option value={NO_AMP}>No amp</option>
            {amps.map((tool) => <option key={tool.toolId} value={tool.toolId}>{tool.name}</option>)}
          </select>
        </label>
        <div className="zml-segment-preview">
          {safeDropCount} drops → new segment · {row.dropCount - safeDropCount} drops remain
        </div>
        <div className="zml-segment-dialog-actions">
          <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="is-primary" onClick={() => void submit()} disabled={busy}>
            {busy ? "Splitting…" : "Split"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MoveSegmentDialog({
  row,
  runs,
  busy,
  onCancel,
  onSubmit,
}: {
  row: SegmentRow;
  runs: RunDto[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (request: { targetRunId?: number; newRunName?: string }) => Promise<void>;
}) {
  const availableRuns = runs.filter((run) => run.runId !== row.segment.runId && run.status !== "deleted");
  const [destination, setDestination] = useState<"new" | "existing">("new");
  const [targetRunId, setTargetRunId] = useState<number | null>(availableRuns[0]?.runId ?? null);
  const [newRunName, setNewRunName] = useState(`Mining run ${new Date().toLocaleDateString()}`);
  const canSubmit = destination === "new" ? newRunName.trim().length > 0 : targetRunId !== null;

  const submit = async () => {
    if (!canSubmit) return;
    await onSubmit(
      destination === "new"
        ? { newRunName: newRunName.trim() }
        : { targetRunId: targetRunId ?? undefined },
    );
  };

  return (
    <div className="zml-segment-dialog-backdrop" role="presentation" onMouseDown={onCancel}>
      <div className="zml-segment-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="zml-segment-dialog-head">
          <div>
            <strong>Move segment #{row.segment.segmentIndex}</strong>
            <span>{row.dropCount} drops · {row.claimCount} claims · {formatPed(row.ttCostPed)} TT</span>
          </div>
          <button type="button" onClick={onCancel} aria-label="Close">×</button>
        </div>
        <div className="zml-segment-choice-tabs">
          <button type="button" className={destination === "new" ? "is-active" : ""} onClick={() => setDestination("new")}>New run</button>
          <button type="button" className={destination === "existing" ? "is-active" : ""} onClick={() => setDestination("existing")}>Existing run</button>
        </div>
        {destination === "new" ? (
          <label>
            New run name
            <input value={newRunName} onChange={(event) => setNewRunName(event.currentTarget.value)} />
            <small>If this is the active run, mining continues in the new run after the move.</small>
          </label>
        ) : (
          <label>
            Destination run
            <select
              value={targetRunId ?? ""}
              onChange={(event) => setTargetRunId(event.currentTarget.value ? Number(event.currentTarget.value) : null)}
            >
              {availableRuns.length === 0 && <option value="">No other runs</option>}
              {availableRuns.map((run) => <option key={run.runId} value={run.runId}>{run.name}</option>)}
            </select>
          </label>
        )}
        <div className="zml-segment-dialog-actions">
          <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="is-primary" onClick={() => void submit()} disabled={busy || !canSubmit}>
            {busy ? "Moving…" : "Move"}
          </button>
        </div>
      </div>
    </div>
  );
}

function buildSegmentRows(
  segments: RunSegmentDto[],
  drops: MiningDropDto[],
  claims: MiningClaimDto[],
): SegmentRow[] {
  return segments.map((segment) => {
    const segmentDrops = drops.filter((drop) => drop.segmentId === segment.segmentId);
    const segmentDropIds = new Set(segmentDrops.map((drop) => drop.dropId));
    const segmentClaims = claims.filter((claim) => (
      claim.segmentId === segment.segmentId ||
      (claim.segmentId === null && claim.dropId !== null && segmentDropIds.has(claim.dropId))
    ));
    return {
      segment,
      dropCount: segmentDrops.length,
      claimCount: segmentClaims.length,
      ttCostPed: segmentDrops.reduce((sum, drop) => sum + drop.cost.totalTtMpec, 0) / 100_000,
      withMarkupCostPed:
        segmentDrops.reduce((sum, drop) => sum + drop.cost.totalWithMarkupMpec, 0) / 100_000,
    };
  });
}

function matchingToolId(tools: MiningToolProfileDto[], name: string): string | null {
  return tools.find((tool) => tool.name === name)?.toolId ?? null;
}

function compareToolNames(left: MiningToolProfileDto, right: MiningToolProfileDto): number {
  return left.name.localeCompare(right.name);
}

function readToolSnapshotName(snapshot: Record<string, unknown>, key: "finder" | "amp"): string {
  const value = snapshot[key];
  if (value === null || typeof value !== "object") return "-";
  const name = (value as Record<string, unknown>).name;
  return typeof name === "string" && name.trim() ? name : "-";
}

function readSnapshotNumber(snapshot: Record<string, unknown>, key: string): number | null {
  const value = snapshot[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatSegmentModes(mask: number | null): string {
  if (mask === null || mask <= 0) return "-";
  const modes: string[] = [];
  if ((mask & 1) !== 0) modes.push("Ore");
  if ((mask & 2) !== 0) modes.push("Enmatter");
  if ((mask & 4) !== 0) modes.push("Treasure");
  return modes.length ? modes.join(" + ") : String(mask);
}

function formatSnapshotUnits(value: number | null): string {
  return value === null ? "-" : String(value);
}

function formatTime(tsMs: number): string {
  return new Date(tsMs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatPed(value: number): string {
  return `${value.toFixed(2)} PED`;
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Segment correction failed";
}
