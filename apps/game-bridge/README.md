# ZML Game Bridge (Python Agent)

Local headless backend (“agent”) for **Z Mining Log**.  
It tails `chat.log`, turns raw lines into structured domain events, persists them to SQLite, and exposes them via REST + SSE for the UI (Electron/React).

> Goal: one local backend process, one client (Electron Main), offline-first.

---

## Features (current)

- Tails `chat.log` (continuous append-only read)
- Parses log lines into `ChatLine`
- Interprets lines into domain events (`EventBase`)
- Persists events to SQLite (single-writer thread)
- Publishes persisted `EventEnvelope` to an in-memory fan-out bus
- API:
  - `GET /health`
  - `GET /events/latest`
  - `GET /events/after/{id}`
  - `GET /events/stream?after={id}` (SSE)

---

## Runtime architecture

### Data flow

```text
chat.log
  -> tailer -> parser(ChatLine) -> interpreter(EventBase)
  -> EventChannel (Queue, cross-thread boundary)
  -> DbWriter thread:
        EventStore.append(EventBase) -> EventEnvelope
        PersistedEventBus.publish(EventEnvelope)
  -> API:
        REST: DbReader queries SQLite
        SSE: SseHub subscribes to PersistedEventBus
```

### Why two “buses”

- **EventChannel** is a *thread boundary* (producer threads → single DB writer). It provides backpressure via `Queue.put`.
- **PersistedEventBus** is *fan-out* for already-persisted envelopes (broadcast to SSE, logging, future processors).

This keeps SQLite writes single-threaded and predictable.

---

## Monetary amounts: mPEC

All monetary amounts are stored as integer **mPEC** (milli-PEC) to avoid float/Decimal drift.

- `1 PED = 100 PEC = 100000 mPEC`
- `1 mPEC = 0.001 PEC = 0.00001 PED`
- Example: `0.123 PEC = 123 mPEC = 0.00123 PED`

In code you’ll typically see a:

```python
from typing import NewType
Mpec = NewType("Mpec", int)
```

---

## Configuration & paths

- Config is read from `Settings` (see `zml_game_bridge/settings.py`).
- Database is stored under **LocalAppData** (Windows) by default.
- `chat.log` path can be configured (supports non-default “Documents” drive).

---

## Running locally

### Run API (dev)

```bash
uv run python -m zml_game_bridge.main
```

This starts Uvicorn using the factory:

- `uvicorn.run("zml_game_bridge.api.app:create_app", factory=True, ...)`

### Test SSE quickly

```bash
curl -N "http://127.0.0.1:17171/events/stream?after=0"
```

You should see `id: ...`, `event: ...`, `data: ...` frames.

---

## SQLite schema (events)

Table: `events`

- `event_id` (INTEGER PRIMARY KEY)
- `created_ts_ms` (INTEGER) — local creation timestamp (ingestion time)
- `event_type` (TEXT)
- `payload_json` (TEXT) — JSON object
- optional helpers:
  - `event_dt` (TEXT | NULL) — timestamp from log line (naive)
  - `raw` (TEXT | NULL) — raw line for debugging / forensics

Indexes:

- `idx_events_created_ts_ms`
- `idx_events_event_type`

---

## API semantics

### REST

- `GET /events/latest?limit=...`
  - Returns last N events (ascending order)
- `GET /events/after/{event_id}?limit=...`
  - Returns events with `event_id > after`, ascending

### SSE

- `GET /events/stream?after={event_id}`
  - Streams live events from `PersistedEventBus`
  - Each SSE message:
    - `id:` = `event_id`
    - `event:` = `event_type`
    - `data:` = DTO JSON (you may exclude duplicated fields)

---

## Testing

Unit tests cover:

- chat parser (`parse_chat_line`)
- interpreter regex matching (`interpret_chat_line`)
- runner wiring (monkeypatch tailer/parser/interpreter)
- DB store/reader basics (SQLite temp DB)

> Tailer tests are intentionally minimal right now (file-system tailing is annoying; keep it pragmatic).

---

## Notes / planned work

- OCR input producer (radar/position/probe fired) feeding into `EventChannel`
- Filtering noisy events (e.g. deed items) via config whitelist
- “Runs” aggregation (derived state) built on top of persisted events
- WS channel for high-frequency position updates (non-persisted)

---

## Developer guidelines

- SQLite writes must go through the single DB writer thread.
- Event producers (`chat`, `ocr`, etc.) emit `EventBase` into `EventChannel`.
- Anything that goes to the UI must be an `EventEnvelope` (persisted, stable id).
- Avoid putting “state” into the SSE stream; stream deltas, resync via REST when needed.
