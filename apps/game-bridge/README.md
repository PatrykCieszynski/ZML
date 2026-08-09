# Z Mining Log Game Bridge

Local Python backend for Z Mining Log. It watches Entropia inputs, derives mining domain events, persists durable state to SQLite, and exposes REST/SSE/WebSocket APIs for the Electron UI.

The backend is offline-first and currently designed for one local UI client.

## Current Shape

- Chat input tails Entropia `chat.log` and emits internal chat signals.
- OCR input reads position continuously and finder state periodically.
- Mock mining input can generate deterministic mining signals for UI/dev work.
- `InputCoordinator` receives signals and asks domain coordinators to derive durable events.
- `DbWriterWorker` is the only SQLite writer.
- Durable events are appended to `events` and projected into read-model tables such as mining drops and claims in the same DB transaction.
- Persisted event envelopes are published to SSE only after the DB write succeeds.
- High-frequency position updates bypass SQLite and go through `PositionTrackingService` to `/ws/position`.

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

Input modes:

- `env`: use current environment variables.
- `live`: OCR on, mocks off.
- `mock`: OCR off, mocks on.
- `hybrid`: OCR on, mocks on.
- `no-inputs`: OCR off, mocks off.

## Useful Environment Variables

- `ZML_LOG_LEVEL`: console log level, defaults to `INFO`.
- `ZML_APP_DATA_DIR`: optional override for the directory containing backend DB, config, logs, and OCR captures.
- `ZML_ERROR_LOG_PATH`: optional override for error-only log file.
- `ZML_DB_PATH`: optional override for SQLite DB path.
- `ZML_CHAT_LOG_PATH`: optional override for Entropia `chat.log`.
- `ZML_MINING_RESOURCE_CATALOG_PATH`: optional override for learned/user mining resources JSON.
- `ZML_CHAT_START_AT_END`: start tailing from the end of the file, defaults to `true`.
- `ZML_OCR_ENABLED`: enable live OCR input.
- `ZML_OCR_TRANSPORT`: `embedded` (default rollback path) or `agent` (managed child process).
- `ZML_OCR_AGENT_PATH`: optional path to a standalone OCR Agent executable; source runs use the
  current Python environment and `python -m zml_ocr_agent stdio` when this is unset.
- `ZML_MOCK_INPUTS`: enable mock mining input.
- `ZML_MOCK_MINING_INTERVAL_MS`: mock drop interval.
- `ZML_FINDER_DEBUG`: enable detailed finder OCR debug logging.
- `ZML_FINDER_RECORDING`: finder crop recording modes, comma-separated: `manual`, `state-change`, `low-confidence`, `interval`, or `all`.
- `ZML_FINDER_RECORDING_DIR`: output directory for finder crop PNG + JSON metadata.
- `ZML_FINDER_RECORDING_INTERVAL_S`: cadence for `interval` recording mode, defaults to `10`.
- `ZML_FINDER_RECORDING_LOW_CONFIDENCE_INTERVAL_S`: minimum cadence for low-confidence samples, defaults to `5`.
- `ZML_OCR_PROFILING`: enable OCR timing summaries in logs.
- `ZML_OCR_PROFILING_INTERVAL_S`: OCR profiling summary interval, defaults to `10`.

For manual finder recording, enable `manual` mode and create a `record-now.flag` file in `ZML_FINDER_RECORDING_DIR`; the OCR worker consumes the flag on the next finder frame.

Source development runs keep their state inside the repository:

```text
<repo>/.tmp/appdata/backend
```

The packaged backend keeps live application state under:

```text
%LOCALAPPDATA%\z-mining-log
```

Consequently, packaged error logs are written to:

```text
%LOCALAPPDATA%\z-mining-log\logs\errors.log
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
- Mining resources are seeded from package JSON and learned into user JSON from claim deed chat lines.
