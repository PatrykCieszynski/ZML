import type { BackendEventEnvelope } from "@desktop/shared";

export type AgentEventStreamStatus = "connecting" | "connected" | "disconnected";

export type AgentEventStreamOptions = {
    baseUrl: string;
    onStatus: (status: AgentEventStreamStatus, err?: string) => void;
    onEvent: (event: BackendEventEnvelope<string, unknown>) => void;
};

export type StopAgentEventStream = () => void;

type SseMessage = {
    id?: string;
    event?: string;
    data: string;
};

type EventStreamDataWire = {
    schema_version: 1;
    created_ts_ms: number;
    event_dt: string | null;
    payload: unknown;
};

function normalizeBaseUrl(baseUrl: string): string {
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(baseUrl)) return baseUrl;
    return `http://${baseUrl}`;
}

function toEventsStreamUrl(baseUrl: string): string {
    const url = new URL(normalizeBaseUrl(baseUrl));
    url.pathname = "/events/stream";
    url.search = "";
    url.hash = "";
    return url.toString();
}

function computeBackoffMs(retry: number): number {
    const base = Math.min(5000, 300 * Math.pow(2, Math.min(5, retry)));
    const jitter = Math.floor(Math.random() * 150);
    return base + jitter;
}

function decodeError(error: unknown): string | undefined {
    if (error instanceof Error) return error.message;
    if (typeof error === "string") return error;
    if (error != null) return String(error);
    return undefined;
}

function parseSseMessage(block: string): SseMessage | null {
    const lines = block.split(/\r?\n/);
    const dataLines: string[] = [];
    let id: string | undefined;
    let event: string | undefined;

    for (const line of lines) {
        if (!line || line.startsWith(":")) continue;

        const separator = line.indexOf(":");
        const field = separator === -1 ? line : line.slice(0, separator);
        const rawValue = separator === -1 ? "" : line.slice(separator + 1);
        const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;

        if (field === "id") id = value;
        if (field === "event") event = value;
        if (field === "data") dataLines.push(value);
    }

    if (!event && dataLines.length === 0) return null;
    return { id, event, data: dataLines.join("\n") };
}

function isEventStreamDataWire(value: unknown): value is EventStreamDataWire {
    if (typeof value !== "object" || value === null) return false;
    const record = value as Record<string, unknown>;
    return (
        record.schema_version === 1 &&
        typeof record.created_ts_ms === "number" &&
        Number.isFinite(record.created_ts_ms) &&
        (record.event_dt === null || typeof record.event_dt === "string") &&
        "payload" in record
    );
}

function toAgentEvent(message: SseMessage): BackendEventEnvelope<string, unknown> | null {
    if (!message.event || !message.data) return null;

    const data = JSON.parse(message.data) as unknown;
    if (!isEventStreamDataWire(data)) return null;

    const eventId = message.id ? Number.parseInt(message.id, 10) : undefined;
    return {
        type: message.event,
        eventId: eventId !== undefined && Number.isFinite(eventId) ? eventId : undefined,
        createdTsMs: data.created_ts_ms,
        eventDt: data.event_dt,
        payload: data.payload,
    };
}

export function startAgentEventStream(opts: AgentEventStreamOptions): StopAgentEventStream {
    let stopped = false;
    let retry = 0;
    let timer: NodeJS.Timeout | null = null;
    let controller: AbortController | null = null;

    const clearTimer = () => {
        if (timer) clearTimeout(timer);
        timer = null;
    };

    const scheduleReconnect = (error?: unknown) => {
        if (stopped || timer) return;
        controller?.abort();
        controller = null;
        opts.onStatus("disconnected", decodeError(error));

        const delay = computeBackoffMs(retry);
        retry += 1;
        timer = setTimeout(() => {
            timer = null;
            void connect();
        }, delay);
    };

    const handleChunk = (chunk: string, pending: { buffer: string }) => {
        pending.buffer += chunk;
        pending.buffer = pending.buffer.replace(/\r\n/g, "\n");

        let splitAt = pending.buffer.indexOf("\n\n");
        while (splitAt !== -1) {
            const block = pending.buffer.slice(0, splitAt);
            pending.buffer = pending.buffer.slice(splitAt + 2);

            const message = parseSseMessage(block);
            if (message) {
                const event = parseAgentEvent(message);
                if (event) opts.onEvent(event);
            }

            splitAt = pending.buffer.indexOf("\n\n");
        }
    };

    const connect = async () => {
        if (stopped) return;
        clearTimer();

        controller?.abort();
        controller = new AbortController();
        opts.onStatus("connecting");

        try {
            const response = await fetch(toEventsStreamUrl(opts.baseUrl), {
                headers: { accept: "text/event-stream" },
                signal: controller.signal,
            });

            if (!response.ok || response.body === null) {
                throw new Error(`Event stream failed: ${response.status} ${response.statusText}`);
            }

            retry = 0;
            opts.onStatus("connected");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            const pending = { buffer: "" };

            while (!stopped) {
                const { value, done } = await reader.read();
                if (done) break;
                handleChunk(decoder.decode(value, { stream: true }), pending);
            }

            if (!stopped) scheduleReconnect();
        } catch (error) {
            if (!stopped) scheduleReconnect(error);
        }
    };

    void connect();

    return () => {
        stopped = true;
        clearTimer();
        controller?.abort();
        controller = null;
        opts.onStatus("disconnected");
    };
}

function parseAgentEvent(message: SseMessage): BackendEventEnvelope<string, unknown> | null {
    try {
        return toAgentEvent(message);
    } catch {
        return null;
    }
}
