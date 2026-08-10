# Current State

Updated: 2026-08-10

This is a short handoff for the current product state. Architecture details belong in `architecture.md`; component commands belong in component READMEs.

## Current product

Z Mining Log is a working local mining-tracker prototype with the complete default process chain:

```text
Desktop -> Backend -> OCR Worker
```

Current capabilities include:

- live player-position OCR and WebSocket map updates;
- finder OCR for drops/hits/no-resource/claim timing data;
- Entropia `chat.log` parsing for claim, loot, enhancer, and depletion information;
- SQLite event journal plus read-model projections;
- runs and setup segments;
- mining-tool profiles and active setup state;
- drop, claim, and loot views;
- dashboard, map, overlay, health, and debugging UI;
- opt-in background upload of complete claim observations to ZML Cloud;
- browser-based ZML Cloud device pairing through Atlas, with an encrypted Desktop credential;
- mock input paths for development;
- Windows installer packaging with both Python processes bundled.

## Architecture recently stabilized

The large OCR/repository refactor is complete:

- OCR is a standalone `apps/ocr-worker` process.
- Backend depends only on `packages/ocr-protocol`, not OCR implementation/native libraries.
- Backend owns worker supervision, config handshake, heartbeat/restart, and protocol-to-application adaptation.
- Desktop owns Backend lifecycle.
- Python projects share one uv workspace, one root lock, and one root `.venv`.
- `just` is the root task interface.
- FastAPI/OpenAPI generates the Desktop REST wire contract through `packages/api-contract`.
- Desktop-internal shared TypeScript moved under `apps/desktop/shared`.
- application names are now consistently `desktop`, `backend`, and `ocr-worker`.
- Windows CI verifies both raw and Electron-bundled Backend/OCR process trees.

The ZML Cloud write boundary is intentionally narrow:

- local SQLite remains the source of truth for the user's mining history;
- a cloud outage never blocks OCR, claim persistence, or local UI updates;
- only complete claim map observations are uploaded;
- no ammo, cost, finder, amplifier, bankroll, or run-return data is sent;
- per-claim cloud outcomes are written back through `DbWriterWorker`, not an ad-hoc SQLite writer;
- normal Desktop connection uses short-lived browser/device pairing through ZML Atlas;
- Discord credentials never enter Electron and the final `zml_...` credential never enters the renderer;
- the Desktop credential is encrypted with Electron `safeStorage` and restored before the managed Backend starts;
- manual `ZML_CLOUD_SYNC_TOKEN` configuration remains only as a development/operator override.

## Stable design rules

Do not rebuild these casually:

- Position telemetry stays live and is not persisted tick-by-tick.
- Signals stay transient; durable events enter the event journal/projections.
- SQLite keeps one writer (`DbWriterWorker`).
- Ignored/false claims are not collapsed into depleted claims.
- Backend does not import OCR implementation.
- OCR observations are rejected until the full desired config revision is acknowledged.
- Desktop renderer remains behind the preload/IPC boundary.
- Cloud synchronization stays asynchronous and local-first.
- Desktop pairing credentials stay in Electron main / Backend process boundaries, never renderer state.

## Highest-value next work

1. **Cloud connection production smoke**
   - run the packaged Desktop through Connect -> Discord -> approve -> automatic exchange;
   - verify the managed Backend restarts with the encrypted credential and pending complete claims upload;
   - restart Desktop and verify the connection restores without a second Discord login;
   - verify Disconnect removes the local credential and restarts without cloud sync.

2. **Operational gameplay validation**
   - longer packaged gameplay smoke/soak sessions;
   - observe worker restart/health behavior under real game conditions;
   - tune OCR based on captured evidence rather than architecture churn.

3. **Public Atlas read path**
   - expose purpose-built anonymous claim reads from ZML Cloud;
   - query by planet and visible viewport rather than downloading the whole dataset;
   - replace Atlas sample points with real observations before adding clustering/heatmaps.

4. **Runtime configuration UX**
   - expose safe OCR/runtime settings beyond environment-only configuration;
   - define which changes apply live and which require worker restart.

5. **ROI calibration**
   - finish finder calibration UX;
   - add compass/lon/lat calibration and reusable presets.

6. **Debug/operator UX**
   - replace JSON-heavy diagnostics with concise worker/OCR/run/event/warning panels.

7. **Persistence/domain cleanup as features demand it**
   - keep the event journal focused on durable reconstruction facts;
   - revisit unused fields only when product behavior makes the decision clear.

## Known technical follow-ups

These are useful but do not justify another large refactor by themselves:

- server-side revocation/account management for paired Desktop credentials beyond local Disconnect;
- move the `openapi-typescript` generator into the pnpm lock instead of invoking it through `pnpm dlx`;
- consider a stronger typed contract for SSE event payloads if manual runtime validators become costly;
- clean remaining non-protocol `Agent` naming where it still means Backend rather than OCR protocol vocabulary;
- remove confirmed unused dependencies such as `pydantic-settings` if a final code search still shows no consumer;
- make invalid explicit environment values fail more visibly instead of silently falling back to defaults.

## Main entry points

Backend:

```text
zml_backend.api.app.create_app
zml_backend.runtime.runtime.AppRuntime
zml_backend.runtime.bootstrap.build_runtime_components
zml_backend.runtime.cloud_sync.CloudSyncWorker
zml_backend.application.mining.coordinator.MiningCoordinator
zml_backend.application.position.tracking.PositionTrackingService
zml_backend.runtime.db_writer.DbWriterWorker
```

Desktop:

```text
apps/desktop/electron/main.ts
apps/desktop/electron/backend/backendProcessManager.ts
apps/desktop/electron/cloud/cloudConnectionService.ts
apps/desktop/electron/cloud/cloudCredentialStore.ts
apps/desktop/electron/ipc/registerIpc.ts
apps/desktop/electron/preload.ts
apps/desktop/src/state/zmlRendererStore.ts
```

OCR Worker:

```text
zml_ocr_worker.cli
zml_ocr_worker.runtime
zml_ocr_worker.pipelines
zml_ocr_worker.capture
```