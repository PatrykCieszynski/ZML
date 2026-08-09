# Current State

Updated: 2026-08-09

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
  - `apps/ocr-agent` now owns capture, pipelines, recording/profiling,
    finder debug tooling, native OCR dependencies, and tessdata;
  - OCR Agent has independent Ruff, Pyright, unit tests, `doctor`, `--version`,
    and `stdio` commands; protocol mode emits `hello`, waits for revisioned full
    configuration, and handles `shutdown` or stdin EOF;
  - finder OCR migrated toward `tesserocr` wrapper;
  - profiling and finder crop recording hooks exist;
  - position outlier filtering exists;
  - missing/lost Entropia window degrades health and retries instead of crashing OCR;
  - OCR still runs in-process by default, but `ZML_OCR_TRANSPORT=agent` now
    selects a managed child process and `ZML_OCR_AGENT_PATH` can select its executable;
  - source runs retain that embedded rollback default, while packaged Electron
    explicitly starts Game Bridge in agent mode with the bundled Agent path;
  - the subprocess supervisor validates `hello`, drains both output pipes,
    applies the complete desired config before accepting observations, monitors
    heartbeats, maps observations, and restarts with bounded backoff;
  - every restart resends the same desired config revision and health exposes
    desired/applied revisions;
  - deterministic real-process tests cover handshake/config, position/finder
    mapping, stderr flood, malformed NDJSON, heartbeat timeout, unavailable
    windows, crash/resync, EOF, and forced shutdown escalation;
  - structured worker health distinguishes process/protocol failure and restart
    state from an unavailable Entropia capture window;
  - the runner emits strict version 1 `packages/ocr-protocol` messages and
    imports no Game Bridge code;
  - `AppRuntime` owns only the `OcrInputSource` lifecycle while
    `EmbeddedOcrInputSource` maps agent messages to position snapshots, finder
    signals, preload, and worker health without changing runtime behavior;
  - finder application signals live under `application.mining.signals.finder`,
    so mining logic no longer imports signal types from `inputs.ocr`.
- Desktop lifecycle and packaging:
  - Electron starts the local backend from `.venv` in development;
  - Windows builds produce separate PyInstaller artifacts for Game Bridge and OCR Agent;
  - the Bridge artifact excludes the Agent package, Windows capture bindings,
    native OCR libraries, and tessdata;
  - packaged Electron stages both artifacts separately, starts the bundled Bridge,
    and passes the bundled Agent path through its managed environment;
  - backend exits through FastAPI lifespan when Electron sends `shutdown` on the parent pipe;
  - parent-pipe reads are non-blocking and Ctrl+C retains Uvicorn's handler despite
    `tesserocr`/`cysignals` initialization;
  - a runtime shutdown signal releases long-lived WS/SSE streams before connection drain;
  - unexpected backend exits use a bounded restart policy;
  - packaging verification checks both artifact layouts, the Agent protocol,
    config synchronization, and clean Bridge/Agent process-tree shutdown;
  - Windows release workflow builds and smoke-tests one NSIS installer containing both artifacts.
- Run accounting and utilities:
  - drop costs distinguish TT from markup-adjusted totals;
  - duplicate drop observations have a five-second lock;
  - run loot can be copied as Excel-ready TSV;
  - `/pos` planet information remains sticky across planet-less OCR positions.

## Important Open Problems

See `ROADMAP_2025-05-26.md` for the ordered roadmap. The highest-value items are:

1. Managed OCR Agent migration:
   - validate agent mode during real gameplay;
   - run a packaged gameplay smoke and soak before switching the source default
     or removing embedded OCR.

2. Runtime config and live settings:
   - move safe OCR/runtime options beyond env-only configuration;
   - expose controlled apply/restart behavior from UI.

3. ROI calibration:
   - finish finder calibration UX;
   - add separate compass/Lon/Lat calibration and presets.

4. Debug/operator UX:
   - replace the JSON-heavy debug tab with worker, OCR, run, event, and warning panels.

5. Persistence cleanup:
   - decide whether unused 3D claim fields should remain;
   - keep the event journal focused on durable reconstruction facts.

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
- `apps/electron-ui/electron/backend/backendProcessManager.ts`
- `apps/electron-ui/electron/runtime.ts`
- `apps/electron-ui/electron/ipc/registerIpc.ts`
- `apps/electron-ui/electron/agent/restClient.ts`
- `apps/electron-ui/src/state/zmlRendererStore.ts`
- `apps/electron-ui/src/windows/mainWindow.tsx`
- `apps/electron-ui/src/windows/mapWindow.tsx`
- `apps/electron-ui/src/widgets/map/mapViewport.tsx`

## Validation Preference

The user permits tests, Ruff, lint, and typechecks for the project/package being
changed, but not broad verification of the entire monorepo by default. Use
focused backend tests and package-scoped Python checks, or focused TypeScript
checks for touched UI contracts/components. Full monorepo verification remains
a CI concern unless explicitly requested.
