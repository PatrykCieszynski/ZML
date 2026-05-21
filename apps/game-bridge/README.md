# ZML Game Bridge

Local Python backend for Zabu Mining Log. It watches Entropia inputs, derives mining domain events, persists durable state to SQLite, and exposes REST/SSE/WebSocket APIs for the Electron UI.

The backend is offline-first and currently designed for one local UI client.

## Current Shape

- Chat input tails Entropia `chat.log` and emits internal chat signals.
- OCR input reads position continuously and finder state periodically.
- Mock mining input can generate deterministic mining signals for UI/dev work.
- `InputCoordinator` receives signals and asks domain coordinators to derive durable events.
- `DbWriterWorker` is the only SQLite writer.
- Durable events are appended to `events` and projected into read-model tables such as mining drops and claims in the same DB transaction.
- Persisted event envelopes are published to SSE only after the DB write succeeds.
- High-frequency position updates bypass SQLite and go through `/ws/position`.

## Runtime Flow

```text
chat.log / OCR / mocks
  -> SignalChannel
  -> InputCoordinator
  -> MiningCoordinator
       -> FinderDropCorrelator
       -> MiningChatCorrelator
       -> ClaimLifecycleCorrelator
  -> EventChannel
  -> DbWriterWorker
       -> EventStore.append(...)
       -> read-model projectors
  -> PersistedEventBus
       -> SSE fan-out to UI
```

Signals are internal observations. They are not persisted.

Events are durable domain facts. They are persisted and can be streamed to the UI.

Read models are query-friendly tables derived from events, for example active mining claims. They are written by the same single DB writer, so they do not introduce a second SQLite writer.

## Running

From the repository root:

```bash
npm run bridge:config
npm run bridge:dev
npm run bridge:ocr
npm run bridge:mock
npm run bridge:finder-debug
```

Directly from `apps/game-bridge`:

```bash
uv run python -m zml_game_bridge.dev_cli config
uv run python -m zml_game_bridge.dev_cli serve
uv run python -m zml_game_bridge.dev_cli serve --mode live
uv run python -m zml_game_bridge.dev_cli serve --mode mock
uv run python -m zml_game_bridge.dev_cli serve --mode live --finder-debug
```

Input modes:

- `env`: use current environment variables.
- `live`: OCR on, mocks off.
- `mock`: OCR off, mocks on.
- `hybrid`: OCR on, mocks on.
- `no-inputs`: OCR off, mocks off.

## Useful Environment Variables

- `ZML_LOG_LEVEL`: console log level, defaults to `INFO`.
- `ZML_ERROR_LOG_PATH`: optional override for error-only log file.
- `ZML_DB_PATH`: optional override for SQLite DB path.
- `ZML_CHAT_LOG_PATH`: optional override for Entropia `chat.log`.
- `ZML_CHAT_START_AT_END`: start tailing from the end of the file, defaults to `true`.
- `ZML_OCR_ENABLED`: enable live OCR input.
- `ZML_MOCK_INPUTS`: enable mock mining input.
- `ZML_MOCK_MINING_INTERVAL_MS`: mock drop interval.
- `ZML_FINDER_DEBUG`: enable detailed finder OCR debug logging.

By default, error logs are written to:

```text
%LOCALAPPDATA%\zabu-mining-log\logs\errors.log
```

Only `ERROR` and `CRITICAL` records go to that file. Normal `INFO` runtime logs stay on the console.

## APIs

- `GET /health`
- `GET /events/latest?limit=200`
- `GET /events/after/{event_id}?limit=200`
- `GET /events/stream`
- `GET /api/v1/mining/drops?window_minutes=30`
- `GET /api/v1/mining/claims?active=true`
- `POST /api/v1/runs/start`
- `POST /api/v1/runs/stop`
- `GET /api/v1/runs/active`
- `WS /ws/position`

## SQLite Rules

- SQLite writes must go through `DbWriterWorker`.
- API routes may open their own read connections.
- Events and projections are written in one transaction.
- Position is live state and is not written to SQLite.

This keeps the app safe from multiple concurrent writers while still allowing REST reads.

## Monetary Amounts

Amounts are stored as integer mPEC to avoid float drift.

```text
1 PED = 100 PEC = 100000 mPEC
1 mPEC = 0.001 PEC = 0.00001 PED
```

## Verification

From the repository root:

```bash
npm run bridge:lint
npm run bridge:typecheck
npm run bridge:test
npm run bridge:verify
```

`bridge:verify` runs Ruff, Pyright, and Pytest.

## Notes

- Finder OCR currently creates `MiningDropEvent`, `MiningHitHintEvent`, and `MiningNoResourcesEvent`.
- Claim lifecycle creates map-facing claim events such as `MiningClaimCreatedEvent` and `MiningClaimDepletedEvent`.
- Chat currently contributes deed, item received, enhancer, and depleted signals/events.
- Loot/profit aggregation should primarily happen at run/segment level, not claim level.
