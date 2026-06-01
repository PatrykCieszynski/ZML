# Current State

Updated: 2026-06-01

This file is a compact handoff for future conversations. It should be updated
when a branch lands a meaningful architecture or product change.

## Product Shape

Z Mining Log is now a working local mining tracker prototype:

- Python backend observes Entropia Universe through OCR and chat log tailing.
- Electron/React UI shows dashboard, map, overlay, runs, segments, loot, claims,
  tools, health, and debug information.
- Map renders raster tiles, player position, drop circles, active claims, claim
  timers, hexgrid, follow mode, and context actions.
- Backend persists durable mining facts to SQLite and streams updates to UI.

## Recently Stabilized

- Signal/Event naming split:
  - input observations are `*Signal`;
  - durable facts are `*Event`.
- Runtime input flow:
  - OCR/chat/mock/API commands enter `RuntimeInputChannel`;
  - `InputCoordinator` calls `MiningCoordinator`;
  - durable events go to `EventChannel`;
  - `DbWriterWorker` persists and publishes.
- Single SQLite writer:
  - DB writes go through `DbWriterWorker`;
  - API read routes use separate read connections.
- Position telemetry:
  - OCR position goes through `PositionTrackingService`;
  - latest position is published via WebSocket;
  - mining logic receives position via `PositionProvider`;
  - raw position stream is not persisted.
- Mining drops and claim lifecycle:
  - `MiningDropEvent`
  - `MiningHitHintEvent`
  - `MiningNoResourcesEvent`
  - `MiningClaimCreatedEvent`
  - `MiningClaimDepletedEvent`
  - `MiningClaimIgnoredEvent`
- Manual claim repair:
  - map context menu can mark claim extracted/depleted;
  - map context menu can ignore false claim separately.
- Equipment profiles:
  - finder/amplifier/extractor profiles exist;
  - active setup changes go through runtime/API flow.
- Run/segment basics:
  - active run state exists;
  - segments have setup snapshots;
  - drop/claim/loot projections are exposed to UI.
- OCR backend:
  - finder OCR migrated toward `tesserocr` wrapper;
  - profiling and finder crop recording hooks exist;
  - position outlier filtering exists.

## Current Worktree Note

At the time this document was added, there was a pre-existing local modification
in:

```text
apps/electron-ui/src/windows/mapWindow.tsx
```

Treat it as user work unless proven otherwise.

## Important Open Problems

See `ROADMAP_2025-05-26.md` for the ordered roadmap. The highest-value items are:

1. Backend/Electron shutdown:
   - no orphan backend process;
   - no hanging DB connection;
   - clean close/restart from Electron.

2. Drop + segment correctness:
   - segment is a setup bucket, not just a chronological episode;
   - same setup inside one run should reuse the existing segment;
   - segment should be created/reused on valid drop, not on noisy finder changes;
   - `ammo_per_drop = 0` should be invalid/fallback, not a real zero-cost drop.

3. Event context completeness:
   - mining events need `run_id` / `segment_id` where possible;
   - event log should support emergency reconstruction.

4. Claim hardening:
   - active claims should expire automatically after expected expiry;
   - maintenance should run inside runtime through DbWriter, not an external cron.

5. Loot aggregation:
   - raw `MiningItemReceivedEvent` spam is too noisy long term;
   - target is run/segment item totals with debounced UI updates.

6. OCR stability:
   - FinderPresenceCheck before expensive finder OCR;
   - treasure mode classifier states;
   - compass latest-wins;
   - manual ROI calibration for finder and compass;
   - `/pos` chat event support.

## What Not To Rebuild Lightly

These decisions were made after several design turns and real-game testing:

- Do not persist every position tick.
- Do not let signals enter the persisted event bus.
- Do not write SQLite from input/API threads.
- Do not collapse false-positive ignored claims into depleted claims.
- Do not make extractor changes segment boundaries for MVP.
- Do not rely on claim-level loot/profit as the main accounting model yet.
  Run/segment totals are more robust because users can interrupt extraction.

## Current Backend Entry Points

- `zml_game_bridge.api.app.create_app`
- `zml_game_bridge.runtime.runtime.AppRuntime`
- `zml_game_bridge.runtime.bootstrap.build_runtime_components`
- `zml_game_bridge.application.mining.coordinator.MiningCoordinator`
- `zml_game_bridge.application.position.tracking.PositionTrackingService`
- `zml_game_bridge.runtime.db_writer.DbWriterWorker`

## Current UI Entry Points

- `apps/electron-ui/electron/main.ts`
- `apps/electron-ui/electron/runtime.ts`
- `apps/electron-ui/electron/ipc/registerIpc.ts`
- `apps/electron-ui/electron/agent/restClient.ts`
- `apps/electron-ui/src/state/zmlRendererStore.ts`
- `apps/electron-ui/src/windows/mainWindow.tsx`
- `apps/electron-ui/src/windows/mapWindow.tsx`
- `apps/electron-ui/src/widgets/map/mapViewport.tsx`

## Validation Preference

The user prefers not to spend local time/tokens on broad lint/pyright runs
unless requested. Use focused tests for touched backend behavior and TypeScript
checks for touched UI contracts/components. Full verification is expected in CI.

