import WebSocket from "ws";
import {
    wireToOcrPositionDTO,
    type OcrPositionEvent,
    type OcrPositionWire,
} from "@zml/shared";

type Status = "connecting" | "connected" | "disconnected";

type Opts = {
    baseUrl: string; // e.g. http://127.0.0.1:8000 (or 127.0.0.1:8000)
    onStatus: (s: Status, err?: string) => void;
    onEvent: (ev: OcrPositionEvent) => void;
};

export function isOcrPositionWire(x: unknown): x is OcrPositionWire {
    if (typeof x !== "object" || x === null) return false;
    const r = x as any;

    return (
        typeof r.ts_ms === "number" &&
        Number.isFinite(r.ts_ms) &&
        typeof r.x === "number" &&
        Number.isFinite(r.x) &&
        typeof r.y === "number" &&
        Number.isFinite(r.y)
    );
}

function normalizeBaseUrl(baseUrl: string): string {
    // Allow passing "127.0.0.1:8000" without protocol.
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(baseUrl)) return baseUrl;
    return `http://${baseUrl}`;
}

function toWsUrl(baseUrl: string): string {
    // http:// -> ws://, https:// -> wss://
    const u = new URL(normalizeBaseUrl(baseUrl));
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/ws/position";
    u.search = "";
    u.hash = "";
    return u.toString();
}

function computeBackoffMs(retry: number): number {
    // 200ms .. 5000ms with a little jitter
    const base = Math.min(5000, 200 * Math.pow(2, Math.min(5, retry)));
    const jitter = Math.floor(Math.random() * 150);
    return base + jitter;
}

function decodeWsData(data: WebSocket.RawData): string {
    // ws RawData can be Buffer | ArrayBuffer | Buffer[] | string

    if (Buffer.isBuffer(data)) return data.toString("utf-8");
    if (Array.isArray(data)) return Buffer.concat(data).toString("utf-8");
    if (data instanceof ArrayBuffer) return Buffer.from(data).toString("utf-8");
    // Fallback
    return Buffer.from(data as any).toString("utf-8");
}

export function startPositionWsClient(opts: Opts): () => void {
    let ws: WebSocket | null = null;
    let stopped = false;

    let retry = 0;
    let timer: NodeJS.Timeout | null = null;

    let seq = 0;

    const clearTimer = () => {
        if (timer) clearTimeout(timer);
        timer = null;
    };

    const cleanupSocket = () => {
        if (!ws) return;
        try {
            ws.removeAllListeners();
            ws.close();
        } catch {
            // ignore
        }
        ws = null;
    };

    const scheduleReconnect = (reason?: unknown) => {
        if (stopped) return;
        if (timer) return; // prevent double scheduling (close+error)

        cleanupSocket();

        const errMsg =
            reason instanceof Error
                ? reason.message
                : typeof reason === "string"
                    ? reason
                    : reason != null
                        ? String(reason)
                        : undefined;

        opts.onStatus("disconnected", errMsg);

        const delay = computeBackoffMs(retry);
        retry += 1;

        timer = setTimeout(() => {
            timer = null;
            connect();
        }, delay);
    };

    const connect = () => {
        if (stopped) return;

        clearTimer();

        const url = toWsUrl(opts.baseUrl);
        opts.onStatus("connecting");

        const sock = new WebSocket(url, {
            perMessageDeflate: false,
            handshakeTimeout: 5000,
        });
        ws = sock;

        sock.on("open", () => {
            if (ws !== sock) return;
            retry = 0;
            opts.onStatus("connected");
        });

        sock.on("message", (data) => {
            if (ws !== sock) return;

            try {
                const text = decodeWsData(data);
                const msg = JSON.parse(text) as unknown;

                if (!isOcrPositionWire(msg)) return;

                const dto = wireToOcrPositionDTO(msg);
                const ev: OcrPositionEvent = {
                    type: "ocr.position",
                    seq: ++seq,
                    tsMs: dto.tsMs,
                    payload: dto,
                };

                opts.onEvent(ev);
            } catch {
                // Ignore garbage (optionally rate-limit logs)
            }
        });

        sock.on("close", () => {
            if (ws !== sock) return;
            scheduleReconnect();
        });

        sock.on("error", (err) => {
            if (ws !== sock) return;
            scheduleReconnect(err);
        });
    };

    connect();

    return () => {
        stopped = true;
        clearTimer();
        cleanupSocket();
    };
}
