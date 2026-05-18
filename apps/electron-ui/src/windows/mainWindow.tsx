import { useState } from "react";
import type { WindowType } from "@zml/shared";
import { refreshAgentHealth, startRun, stopRun, useZmlRendererStore } from "../state/zmlRendererStore";

export function MainWindow() {
  const windowType: WindowType = "main";
  const state = useZmlRendererStore(windowType);
  const position = state.position?.position;
  const [runName, setRunName] = useState("Mining run");

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h2>ZML Desktop</h2>

      {state.error && (
        <div style={{ background: "#2a0f0f", color: "#ffdada", padding: 12, borderRadius: 8 }}>
          <b>UI error</b>
          <div style={{ marginTop: 6 }}>{state.error}</div>
        </div>
      )}

      {!state.error && state.bootstrapping && <p>Loading bootstrap...</p>}

      {!state.error && state.bootstrapped && (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <section style={{ background: "#111", color: "#ddd", padding: 12, borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Agent</h3>
            <div>Status: {state.agent.status}</div>
            <div>WS: {state.streams.ws ? "connected" : "offline"}</div>
            <div>SSE: {state.streams.sse ? "connected" : "offline"}</div>
            <div>Health: {state.agentHealth?.status ?? "-"}</div>
            {state.agent.lastError && <div style={{ color: "#ffb4b4" }}>{state.agent.lastError}</div>}
            {state.lastCommandError && <div style={{ color: "#ffb4b4" }}>{state.lastCommandError}</div>}
            <button
              type="button"
              onClick={() => {
                void refreshAgentHealth();
              }}
              disabled={state.agentHealthChecking}
              style={{ marginTop: 10 }}
            >
              {state.agentHealthChecking ? "Checking..." : "Check health"}
            </button>
          </section>

          <section style={{ background: "#111", color: "#ddd", padding: 12, borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Position</h3>
            <div>X: {position ? position.x : "-"}</div>
            <div>Y: {position ? position.y : "-"}</div>
            <div>Z: {position?.z ?? "-"}</div>
            <div>Seq: {state.positionEvent?.seq ?? "-"}</div>
          </section>

          <section style={{ background: "#111", color: "#ddd", padding: 12, borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Run Commands</h3>
            <div>Active: {state.activeRun ? `${state.activeRun.name} (${state.activeRun.status})` : "-"}</div>
            <input
              value={runName}
              onChange={(event) => setRunName(event.currentTarget.value)}
              disabled={state.runCommandPending}
              style={{ boxSizing: "border-box", marginTop: 10, width: "100%" }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button
                type="button"
                onClick={() => {
                  void startRun(runName);
                }}
                disabled={state.runCommandPending}
              >
                Start run
              </button>
              <button
                type="button"
                onClick={() => {
                  void stopRun();
                }}
                disabled={state.runCommandPending}
              >
                Stop run
              </button>
            </div>
          </section>
        </div>
      )}

      {state.bootstrapped && (
        <pre style={{ background: "#111", color: "#ddd", padding: 12, borderRadius: 8 }}>
          {JSON.stringify(state, null, 2)}
        </pre>
      )}
    </div>
  );
}
