// apps/ui/src/App.tsx
import { useEffect, useState } from "react";
import type { BootstrapState, OcrPositionEvent } from "@zml/shared";
import { getZml } from "./zml";

export default function App() {
    const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
    const [lastEvent, setLastEvent] = useState<OcrPositionEvent | null>(null);
    const [err, setErr] = useState<string | null>(null);

    useEffect(() => {
        let unsub: (() => void) | null = null;
        let alive = true;

        (async () => {
            try {
                const zml = getZml();

                const bs = await zml.getBootstrapState("main");
                if (!alive) return;
                setBootstrap(bs);

                unsub = zml.onPosition((evt) => {
                    setLastEvent(evt);
                });
            } catch (e) {
                if (!alive) return;
                setErr(e instanceof Error ? e.message : String(e));
            }
        })();

        return () => {
            alive = false;
            if (unsub) unsub();
        };
    }, []);

    if (err) {
        return (
            <div style={{ padding: 16 }}>
                <h2>UI error</h2>
                <pre>{err}</pre>
            </div>
        );
    }

    if (!bootstrap) {
        return (
            <div style={{ padding: 16 }}>
                <div>Loading bootstrap…</div>
            </div>
        );
    }

    const bsPos = bootstrap.position?.position;
    const evtPos = lastEvent?.payload.position;

    return (
        <div style={{ padding: 16, fontFamily: "system-ui" }}>
            <h2>ZML UI</h2>

            <div style={{ marginBottom: 12 }}>
                <div>ipcVersion: {bootstrap.ipcVersion}</div>
                <div>windowType: {bootstrap.windowType}</div>
                <div>agent: {bootstrap.agent.status}</div>
                <div>
                    streams: ws={String(bootstrap.streams.ws)} sse={String(bootstrap.streams.sse)}
                </div>
            </div>

            <div style={{ marginBottom: 12 }}>
                <h3>Bootstrap position</h3>
                {bsPos ? (
                    <div>
                        x={bsPos.x} y={bsPos.y} z={String(bsPos.z)}
                    </div>
                ) : (
                    <div>none</div>
                )}
            </div>

            <div>
                <h3>Last pushed event</h3>
                {lastEvent ? (
                    <div>
                        <div>seq={lastEvent.seq} tsMs={lastEvent.tsMs}</div>
                        <div>
                            x={evtPos?.x} y={evtPos?.y} z={String(evtPos?.z)}
                        </div>
                    </div>
                ) : (
                    <div>no events yet</div>
                )}
            </div>
        </div>
    );
}
