import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type {
  ActiveMiningToolsDto,
  CloudConnectionState,
  MiningToolKind,
  MiningToolProfileDto,
} from "@desktop/shared";
import {
  connectCloud,
  createMiningTool,
  deleteMiningTool,
  disconnectCloud,
  refreshMiningTools,
  setActiveMiningTools,
  useZmlRendererStore,
} from "../state/zmlRendererStore";

type MiningToolsPanelProps = {
  tools: MiningToolProfileDto[];
  activeTools?: ActiveMiningToolsDto;
  loading: boolean;
  pending: boolean;
};

type ActiveDraft = {
  finderId: string;
  ampId: string;
  extractorId: string;
  finderRangeEnhancerCount: string;
};

const TOOL_KINDS: MiningToolKind[] = ["finder", "amp", "extractor"];

const KIND_LABELS: Record<MiningToolKind, string> = {
  finder: "Finders",
  amp: "Amps",
  extractor: "Extractors",
};

export function MiningToolsPanel({
  tools,
  activeTools,
  loading,
  pending,
}: MiningToolsPanelProps) {
  const cloud = useZmlRendererStore("main").cloud;
  const [kind, setKind] = useState<MiningToolKind>("finder");
  const [name, setName] = useState("");
  const [decayMpec, setDecayMpec] = useState("0");
  const [decayPec, setDecayPec] = useState("");
  const [markupPercent, setMarkupPercent] = useState("100");
  const [radiusM, setRadiusM] = useState("55");
  const [formError, setFormError] = useState<string | null>(null);
  const [activeDraft, setActiveDraft] = useState<ActiveDraft>({
    finderId: "",
    ampId: "",
    extractorId: "",
    finderRangeEnhancerCount: "0",
  });

  useEffect(() => {
    setActiveDraft({
      finderId: activeTools?.finderId ?? "",
      ampId: activeTools?.ampId ?? "",
      extractorId: activeTools?.extractorId ?? "",
      finderRangeEnhancerCount: String(activeTools?.finderRangeEnhancerCount ?? 0),
    });
  }, [
    activeTools?.finderId,
    activeTools?.ampId,
    activeTools?.extractorId,
    activeTools?.finderRangeEnhancerCount,
  ]);

  const toolsByKind = useMemo(() => {
    return {
      finder: tools.filter((tool) => tool.kind === "finder"),
      amp: tools.filter((tool) => tool.kind === "amp"),
      extractor: tools.filter((tool) => tool.kind === "extractor"),
    };
  }, [tools]);
  const pecConversion = useMemo(() => parsePecConversion(decayPec), [decayPec]);

  const handleCreateTool = () => {
    const parsed = parseToolForm({ kind, name, decayMpec, markupPercent, radiusM });
    if (typeof parsed === "string") {
      setFormError(parsed);
      return;
    }

    setFormError(null);
    setName("");
    void createMiningTool(parsed);
  };

  const handleSaveActiveTools = () => {
    const enhancerCount = Number(activeDraft.finderRangeEnhancerCount);
    if (!Number.isInteger(enhancerCount) || enhancerCount < 0) {
      setFormError("Finder enhancers must be a non-negative integer");
      return;
    }

    setFormError(null);
    void setActiveMiningTools({
      finderId: emptyToNull(activeDraft.finderId),
      ampId: emptyToNull(activeDraft.ampId),
      extractorId: emptyToNull(activeDraft.extractorId),
      finderRangeEnhancerCount: enhancerCount,
    });
  };

  return (
    <section style={panelStyle}>
      <CloudConnectionSection cloud={cloud} />

      <div style={panelHeaderStyle}>
        <h3 style={{ margin: 0 }}>Mining Tools</h3>
        <button
          type="button"
          onClick={() => {
            void refreshMiningTools();
          }}
          disabled={loading || pending}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {formError && <div style={errorStyle}>{formError}</div>}

      <div style={splitGridStyle}>
        <div style={columnStyle}>
          <h4 style={headingStyle}>Active Setup</h4>
          <label style={labelStyle}>
            Finder
            <select
              value={activeDraft.finderId}
              onChange={(event) => {
                const { value } = event.currentTarget;
                setActiveDraft((draft) => ({ ...draft, finderId: value }));
              }}
              disabled={pending}
              style={inputStyle}
            >
              <option value="">Default finder</option>
              {toolsByKind.finder.map((tool) => (
                <option key={tool.toolId} value={tool.toolId}>
                  {tool.name}
                </option>
              ))}
            </select>
          </label>
          <label style={labelStyle}>
            Amp
            <select
              value={activeDraft.ampId}
              onChange={(event) => {
                const { value } = event.currentTarget;
                setActiveDraft((draft) => ({ ...draft, ampId: value }));
              }}
              disabled={pending}
              style={inputStyle}
            >
              <option value="">No amp</option>
              {toolsByKind.amp.map((tool) => (
                <option key={tool.toolId} value={tool.toolId}>
                  {tool.name}
                </option>
              ))}
            </select>
          </label>
          <label style={labelStyle}>
            Extractor
            <select
              value={activeDraft.extractorId}
              onChange={(event) => {
                const { value } = event.currentTarget;
                setActiveDraft((draft) => ({ ...draft, extractorId: value }));
              }}
              disabled={pending}
              style={inputStyle}
            >
              <option value="">No extractor</option>
              {toolsByKind.extractor.map((tool) => (
                <option key={tool.toolId} value={tool.toolId}>
                  {tool.name}
                </option>
              ))}
            </select>
          </label>
          <label style={labelStyle}>
            Finder range enhancers
            <input
              type="number"
              min={0}
              step={1}
              value={activeDraft.finderRangeEnhancerCount}
              onChange={(event) => {
                const { value } = event.currentTarget;
                setActiveDraft((draft) => ({
                  ...draft,
                  finderRangeEnhancerCount: value,
                }));
              }}
              disabled={pending}
              style={inputStyle}
            />
          </label>
          <div style={metricsStyle}>
            <span>Radius: {formatMeters(activeTools?.effectiveFinderRadiusM)}</span>
            <span>Extraction: {formatMpec(activeTools?.extractionCostMpec)}</span>
          </div>
          <button type="button" onClick={handleSaveActiveTools} disabled={pending}>
            {pending ? "Saving..." : "Save active tools"}
          </button>
        </div>

        <div style={columnStyle}>
          <h4 style={headingStyle}>Add Tool</h4>
          <label style={labelStyle}>
            Type
            <select
              value={kind}
              onChange={(event) => setKind(event.currentTarget.value as MiningToolKind)}
              disabled={pending}
              style={inputStyle}
            >
              <option value="finder">Finder</option>
              <option value="amp">Amp</option>
              <option value="extractor">Extractor</option>
            </select>
          </label>
          <label style={labelStyle}>
            Name
            <input
              value={name}
              onChange={(event) => setName(event.currentTarget.value)}
              disabled={pending}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            Decay mPEC
            <input
              type="number"
              min={0}
              step={1}
              value={decayMpec}
              onChange={(event) => setDecayMpec(event.currentTarget.value)}
              disabled={pending}
              style={inputStyle}
            />
          </label>
          <div style={converterStyle}>
            <label style={labelStyle}>
              Wiki decay (PEC)
              <input
                type="text"
                inputMode="decimal"
                placeholder="3.96"
                value={decayPec}
                onChange={(event) => {
                  const { value } = event.currentTarget;
                  setDecayPec(value);
                }}
                disabled={pending}
                style={inputStyle}
              />
            </label>
            <div style={converterResultStyle}>
              <span>
                {decayPec.trim() === ""
                  ? "PEC to mPEC"
                  : pecConversion === null
                    ? "Invalid PEC value"
                    : `${pecConversion.mpec} mPEC / ${formatPedDecimal(pecConversion.mpec)} PED`}
              </span>
              <button
                type="button"
                onClick={() => {
                  if (pecConversion !== null) {
                    setDecayMpec(String(pecConversion.mpec));
                  }
                }}
                disabled={pending || pecConversion === null}
              >
                Use as decay
              </button>
            </div>
          </div>
          <label style={labelStyle}>
            Markup percent
            <input
              value={markupPercent}
              onChange={(event) => setMarkupPercent(event.currentTarget.value)}
              disabled={pending}
              style={inputStyle}
            />
          </label>
          {kind === "finder" && (
            <label style={labelStyle}>
              Radius m
              <input
                type="number"
                min={0}
                step={0.1}
                value={radiusM}
                onChange={(event) => setRadiusM(event.currentTarget.value)}
                disabled={pending}
                style={inputStyle}
              />
            </label>
          )}
          <button type="button" onClick={handleCreateTool} disabled={pending}>
            Add tool
          </button>
        </div>
      </div>

      <div style={toolListStyle}>
        {TOOL_KINDS.map((toolKind) => (
          <div key={toolKind} style={toolGroupStyle}>
            <h4 style={headingStyle}>{KIND_LABELS[toolKind]}</h4>
            {toolsByKind[toolKind].length === 0 ? (
              <div style={emptyStyle}>-</div>
            ) : (
              toolsByKind[toolKind].map((tool) => (
                <div key={tool.toolId} style={toolRowStyle}>
                  <div>
                    <strong>{tool.name}</strong>
                    <div style={mutedStyle}>
                      {formatMpec(tool.decayMpec)} - markup {tool.markupPercent}%
                      {tool.radiusM !== null ? ` - ${formatMeters(tool.radiusM)}` : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      void deleteMiningTool(tool.toolId);
                    }}
                    disabled={pending}
                  >
                    Delete
                  </button>
                </div>
              ))
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function CloudConnectionSection({ cloud }: { cloud: CloudConnectionState }) {
  const pending = cloud.status === "connecting" || cloud.status === "waiting_for_approval";
  const environmentManaged = cloud.credentialSource === "environment";
  const statusLabel = cloudStatusLabel(cloud);

  return (
    <div style={cloudSectionStyle}>
      <div style={cloudCopyStyle}>
        <div style={cloudTitleRowStyle}>
          <h3 style={{ margin: 0 }}>ZML Cloud</h3>
          <span style={cloudStatusStyle(cloud.status === "connected")}>{statusLabel}</span>
        </div>
        <div style={mutedStyle}>
          Sync complete mining claim observations through your ZML account. Discord authorization opens in your browser; Desktop stores only a revocable ZML credential.
        </div>
        {cloud.status === "waiting_for_approval" && cloud.pairingExpiresAtTsMs !== undefined && (
          <div style={cloudHintStyle}>
            Waiting for browser approval. Request expires at {new Date(cloud.pairingExpiresAtTsMs).toLocaleTimeString()}.
          </div>
        )}
        {cloud.status === "connected" && (
          <div style={cloudHintStyle}>
            {environmentManaged
              ? "Connected using the ZML_CLOUD_SYNC_TOKEN development override."
              : "Connected. The credential is encrypted for this operating-system user and restored on restart."}
          </div>
        )}
        {cloud.lastError && <div style={errorStyle}>{cloud.lastError}</div>}
      </div>

      <div style={cloudActionsStyle}>
        {(cloud.status === "disconnected" || cloud.status === "error") && (
          <button type="button" onClick={() => void connectCloud()} disabled={environmentManaged}>
            Connect ZML Cloud
          </button>
        )}
        {pending && (
          <button type="button" onClick={() => void disconnectCloud()}>
            Cancel
          </button>
        )}
        {cloud.status === "connected" && (
          <button
            type="button"
            onClick={() => void disconnectCloud()}
            disabled={environmentManaged}
          >
            {environmentManaged ? "Managed by environment" : "Disconnect"}
          </button>
        )}
      </div>
    </div>
  );
}

function cloudStatusLabel(cloud: CloudConnectionState): string {
  switch (cloud.status) {
    case "disconnected":
      return "Not connected";
    case "connecting":
      return "Connecting...";
    case "waiting_for_approval":
      return "Waiting for approval";
    case "connected":
      return "Connected";
    case "error":
      return "Connection error";
  }
}

function parseToolForm({
  kind,
  name,
  decayMpec,
  markupPercent,
  radiusM,
}: {
  kind: MiningToolKind;
  name: string;
  decayMpec: string;
  markupPercent: string;
  radiusM: string;
}) {
  const trimmedName = name.trim();
  if (!trimmedName) return "Tool name is required";

  const parsedDecay = Number(decayMpec);
  if (!Number.isInteger(parsedDecay) || parsedDecay < 0) {
    return "Decay must be a non-negative integer mPEC value";
  }

  const trimmedMarkup = markupPercent.trim();
  if (!trimmedMarkup || Number.isNaN(Number(trimmedMarkup)) || Number(trimmedMarkup) < 0) {
    return "Markup percent must be a non-negative number";
  }

  const parsedRadius = kind === "finder" ? Number(radiusM) : null;
  if (kind === "finder" && (parsedRadius === null || !Number.isFinite(parsedRadius) || parsedRadius <= 0)) {
    return "Finder radius must be positive";
  }

  return {
    kind,
    name: trimmedName,
    decayMpec: parsedDecay,
    markupPercent: trimmedMarkup,
    radiusM: parsedRadius,
  };
}

function emptyToNull(value: string): string | null {
  return value === "" ? null : value;
}

function parsePecConversion(value: string): { mpec: number } | null {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null;

  const pec = Number(normalized);
  const mpec = Math.round(pec * 1_000);
  if (!Number.isFinite(pec) || pec < 0 || !Number.isSafeInteger(mpec)) return null;
  return { mpec };
}

function formatPedDecimal(valueMpec: number): string {
  return (valueMpec / 100_000).toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
}

function formatMpec(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${(value / 100_000).toFixed(4)} PED`;
}

function formatMeters(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(1)} m`;
}

const panelStyle = {
  background: "#111",
  color: "#ddd",
  padding: 12,
  borderRadius: 8,
  gridColumn: "1 / -1",
} satisfies CSSProperties;

const panelHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  alignItems: "center",
} satisfies CSSProperties;

const cloudSectionStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 16,
  marginBottom: 16,
  padding: 12,
  border: "1px solid #2c3f52",
  borderRadius: 8,
  background: "#101923",
} satisfies CSSProperties;

const cloudCopyStyle = {
  display: "grid",
  gap: 6,
  minWidth: 0,
} satisfies CSSProperties;

const cloudTitleRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: 10,
} satisfies CSSProperties;

const cloudActionsStyle = {
  display: "flex",
  alignItems: "center",
  flexShrink: 0,
} satisfies CSSProperties;

const cloudHintStyle = {
  color: "#a7d7ff",
  fontSize: 12,
} satisfies CSSProperties;

function cloudStatusStyle(connected: boolean): CSSProperties {
  return {
    padding: "3px 7px",
    border: `1px solid ${connected ? "#316b4a" : "#4b5666"}`,
    borderRadius: 99,
    color: connected ? "#8ee3af" : "#a9b6c8",
    fontSize: 11,
    fontWeight: 700,
  };
}

const splitGridStyle = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  marginTop: 12,
} satisfies CSSProperties;

const columnStyle = {
  display: "grid",
  gap: 8,
  alignContent: "start",
} satisfies CSSProperties;

const labelStyle = {
  display: "grid",
  gap: 4,
  fontSize: 13,
} satisfies CSSProperties;

const inputStyle = {
  boxSizing: "border-box",
  width: "100%",
} satisfies CSSProperties;

const headingStyle = {
  margin: 0,
} satisfies CSSProperties;

const metricsStyle = {
  display: "flex",
  gap: 12,
  color: "#a7d7ff",
  fontSize: 13,
} satisfies CSSProperties;

const converterStyle = {
  display: "grid",
  gap: 6,
  paddingTop: 8,
  borderTop: "1px solid #2c2c2c",
} satisfies CSSProperties;

const converterResultStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 8,
  minHeight: 28,
  color: "#a7d7ff",
  fontSize: 12,
} satisfies CSSProperties;

const toolListStyle = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
  marginTop: 14,
} satisfies CSSProperties;

const toolGroupStyle = {
  display: "grid",
  gap: 8,
  alignContent: "start",
} satisfies CSSProperties;

const toolRowStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: 8,
  alignItems: "center",
  padding: "8px 0",
  borderTop: "1px solid #2c2c2c",
} satisfies CSSProperties;

const mutedStyle = {
  color: "#aaa",
  fontSize: 12,
  marginTop: 2,
} satisfies CSSProperties;

const emptyStyle = {
  color: "#777",
} satisfies CSSProperties;

const errorStyle = {
  marginTop: 10,
  color: "#ffb4b4",
} satisfies CSSProperties;
