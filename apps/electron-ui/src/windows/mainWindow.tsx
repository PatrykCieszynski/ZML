import { useEffect, useState } from "react";
import type { BootstrapState, WindowType } from "@zml/shared";
import { getZml } from "../zml";

export function MainWindow() {
  const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const windowType: WindowType = "main";

  useEffect(() => {
    let alive = true;

    let api;
    try {
      api = getZml();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      return;
    }

    api
      .getBootstrapState(windowType)
      .then((s) => {
        if (alive) setBootstrap(s);
      })
      .catch((e) => {
        console.error(e);
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });

    return () => {
      alive = false;
    };
  }, []);

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h2>ZML Desktop — Main</h2>

      {error && (
        <div style={{ background: "#2a0f0f", color: "#ffdada", padding: 12, borderRadius: 8 }}>
          <b>UI error</b>
          <div style={{ marginTop: 6 }}>{error}</div>
        </div>
      )}

      {!error && !bootstrap && <p>Loading bootstrap…</p>}

      {bootstrap && (
        <pre style={{ background: "#111", color: "#ddd", padding: 12, borderRadius: 8 }}>
          {JSON.stringify(bootstrap, null, 2)}
        </pre>
      )}

      <p style={{ opacity: 0.8 }}>
        This window is just a placeholder. Next: settings + agent connection status.
      </p>
    </div>
  );
}
