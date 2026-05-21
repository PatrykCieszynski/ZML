# Z Mining Log

Work-in-progress local mining assistant for Entropia Universe.

The project is intentionally local-first: a Python backend reads game inputs,
persists durable mining facts to SQLite, and an Electron/React UI renders the
map, player position, drops, claims, timers, and run state.

This README is a living project map, not a polished product document yet.

## Project Status

What is already taking shape:

- Python game bridge backend with FastAPI, SQLite, SSE, and WebSocket position updates.
- OCR position input for live player coordinates.
- OCR mining finder pipeline for drops, hit hints, no-resource results, and claim timers.
- Chat log input for deed received, resource claimed, item received, enhancer, and depleted messages.
- Single-writer SQLite runtime with event journal plus read-model projections.
- Electron/React UI with a deck.gl map, raster tiles, player position, drop radii, and active claims.
- Shared TypeScript DTO package for Electron main, renderer, and backend contracts.
- Mock mining input for UI/backend development without the game running.

Still very much in progress:

- Run and segment profit aggregation.
- Claim deed OCR and precise claim confirmation.
- Tool/finder profiles, radius selection, decay, markup, and user configuration.
- Better resource coloring/icons and richer claim UI.
- CI, packaging, release flow, and stronger end-to-end test coverage.
- Cleanup of old OCR experiments and temporary mock/debug assets.

## Repository Layout

```text
apps/
  game-bridge/      Python backend: inputs, runtime, persistence, REST/SSE/WS API
  electron-ui/      Electron main process and React renderer

packages/
  shared/           Shared TypeScript DTOs and IPC contracts

ZML.pdf             Early project notes; partly outdated
```

## Architecture Snapshot

Backend flow:

```text
OCR / chat.log / mocks
  -> internal signals
  -> InputCoordinator
  -> MiningCoordinator
  -> durable mining events
  -> DbWriterWorker
  -> SQLite event journal + read-model projections
  -> SSE to Electron main
  -> renderer store
```

Important conventions:

- Signals are internal observations from inputs. They are not persisted.
- Events are durable domain facts. They are persisted and may be streamed to the UI.
- SQLite writes go through one writer thread only.
- API read endpoints open separate read connections.
- High-frequency position updates bypass SQLite and go through WebSocket.
- Read-model projections are query tables derived from persisted events in the same DB transaction.

## Inputs And Threading

The backend receives data from several independent inputs:

- `chat.log` tailing for system messages, deeds, loot, enhancers, and depletion.
- OCR position scanning for live player coordinates.
- OCR finder scanning for drops, hit hints, no-resource results, modes, and units.
- Optional mock mining input for local development without the game.
- REST/SSE/WebSocket API traffic from Electron.

These inputs can run concurrently, but they do not write directly to SQLite. Input threads emit
signals into a runtime queue. The coordinator processes those signals sequentially and emits only
durable events. The DB writer then persists those events and their read-model projections in order.

This keeps the noisy and timing-sensitive parts of the app parallel, while the domain decisions and
database writes stay predictable.

## Verification

Backend:

```bash
npm run bridge:verify
```

This runs:

```text
ruff
pyright
pytest
```

Frontend:

```bash
pnpm --filter @zml/electron-ui lint
pnpm --filter @zml/electron-ui build
```

Note: the full Electron build may depend on local Electron/electron-builder cache permissions.
For quick TypeScript-only validation, run `tsc` in `apps/electron-ui`.

## Runtime Notes

Default backend port:

```text
127.0.0.1:17171
```

Useful backend endpoints:

```text
GET /health
GET /events/latest
GET /events/stream
GET /api/v1/mining/drops?window_minutes=30
GET /api/v1/mining/claims?active=true
GET /api/v1/runs/active
WS  /ws/position
```

Useful environment variables:

```text
ZML_LOG_LEVEL
ZML_ERROR_LOG_PATH
ZML_DB_PATH
ZML_CHAT_LOG_PATH
ZML_MINING_RESOURCE_CATALOG_PATH
ZML_CHAT_START_AT_END
ZML_OCR_ENABLED
ZML_MOCK_INPUTS
ZML_MOCK_MINING_INTERVAL_MS
ZML_FINDER_DEBUG
```

Only `ERROR` and `CRITICAL` logs are written to the backend error log file by default.
Normal `INFO` logs stay on the console.

## Current Mining Model

Current durable mining facts include:

- `MiningDropEvent`: a probe/drop was fired with position, modes, cost, and drop radius.
- `MiningHitHintEvent`: finder saw a preclaim hint with resource, size, range/depth, and expected expiry.
- `MiningNoResourcesEvent`: finder reported no resources for a pending drop.
- `MiningClaimCreatedEvent`: map-facing active claim created from a hit hint.
- `MiningClaimDepletedEvent`: active claim was marked depleted from chat + nearest position.
- `MiningClaimDeedReceivedEvent`: chat reported a deed entering inventory.
- `MiningItemReceivedEvent`: chat reported loot entering inventory.
- `MiningEnhancerBrokeEvent`: chat reported enhancer breakage.

Profit tracking should primarily aggregate by run/segment, not by claim. Claim lifecycle is mostly for map state, timers, and operational decisions.

Mining resources are loaded from a seed JSON in the backend package and a user JSON under
LocalAppData. Claim deed chat messages can learn/update resources in the user JSON, which lets the
loot whitelist grow from real gameplay while still allowing manual overrides later.

## Known Rough Edges

- The root app still mixes npm scripts and pnpm workspaces.
- Backend README is more detailed than the root README, but both are still WIP.
- Some OCR testing assets and old experiments need cleanup.
- Mock inputs are useful but should be made more explicit and discoverable.
- CI is not wired yet.
- Packaging is not production-ready.
- The original PDF/confluence-style notes are no longer fully accurate.

## Next Likely Work

- Finish run/segment ledger for costs and loot.
- Add claim deed OCR and `ClaimConfirmedEvent`.
- Add user-configurable finder/tool profiles.
- Improve map claim UI and resource styling.
- Add GitHub Actions for backend and frontend checks.
- Clean OCR experiment folders and document the remaining fixtures.
