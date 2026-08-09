# Z Mining Log - Agent Handoff

This repository is a local-first Entropia Universe mining tracker. It has a
Python backend (`apps/game-bridge`), an Electron/React UI (`apps/electron-ui`),
and shared TypeScript contracts (`packages/shared`).

Use this file as the first stop for future Codex/agent work. The deeper project
notes live in:

- `docs/architecture.md`
- `docs/current-state.md`
- `docs/decisions/`
- `ROADMAP_2025-05-26.md`

## Working Rules

- Do not revert user changes. The worktree may be dirty.
- Prefer reading the current code before changing it. A lot of design was
  refined during real gameplay testing.
- Use `rg` / `rg --files` for searches.
- Use `apply_patch` for manual edits.
- Keep changes small and scoped. This project has several moving parts and
  accidental cross-layer rewrites are expensive.
- The user prefers not to run local `ruff`, `pyright`, or broad lint pipelines
  unless explicitly requested. CI/PR checks cover those. Focused tests or
  TypeScript checks are fine when useful.
- Do not start the Electron UI, Vite dev server, Browser tooling, or mock UI
  preview for routine verification unless the user explicitly asks. Prefer
  focused tests, typechecks, and builds.

## Agent Environment

For one-shot commands, prefer the wrapper so Windows execution policy does not
block the setup:

```powershell
.\scripts\agent-env.cmd -- pnpm --filter @zml/electron-ui typecheck
.\scripts\agent-env.cmd -- just test
```

For an interactive PowerShell session, initialize the repo-local agent
environment first:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. .\scripts\agent-env.ps1
```

This sets `UV_CACHE_DIR` to `apps/game-bridge/.uv-cache`, keeps temporary files
in repo-local `.tmp`, prefers local tools from `Y:\Software`, and defines
`pnpm` as a `corepack pnpm` wrapper. For one-shot commands, use
`scripts\agent-env.cmd`.

## High-Level Architecture

The backend has three important flows:

1. High-frequency position telemetry:
   - OCR position input
   - `PositionTrackingService`
   - WebSocket to Electron
   - not persisted as a position stream

2. Mining domain flow:
   - OCR/chat/mock input signals
   - `RuntimeInputChannel`
   - `InputCoordinator`
   - `MiningCoordinator`
   - durable domain events
   - `DbWriterWorker`
   - SQLite event journal + projection tables
   - SSE to Electron

3. UI command flow:
   - React renderer
   - Electron IPC
   - Electron REST client
   - FastAPI route
   - runtime command through the input queue when it changes mining state
   - durable events through the DB writer when persistence is needed

4. Desktop process lifecycle:
   - Electron starts the default local backend from `.venv` in development
   - packaged Electron starts `resources/backend/zml-game-bridge.exe`
   - backend shutdown travels through the parent stdin pipe and FastAPI lifespan
   - explicit/custom backends remain externally owned

See `docs/architecture.md` for details.

## Core Naming Rules

- `Signal`: an internal observation from OCR, chat, mock input, or another
  noisy input source. Signals are not persisted.
- `Event`: a durable domain fact. Events may be persisted, projected, and sent
  to the UI.
- `Command`: a user/API/runtime intent. Commands that affect mining state should
  enter the runtime input queue and be handled by the coordinator/service layer.
- `Projection`: a query table derived from durable events inside the DB writer
  transaction. Projections are read models, not a second independent write path.

## Important Boundaries

- `inputs/*` parses or observes external sources and emits signals.
- `application/*` contains business/application logic.
- `domain/*` contains durable event/value objects and pure domain helpers.
- `runtime/*` owns queues, workers, startup/shutdown, and threading.
- `persistence/*` owns SQLite schema, event store, readers, projections, and
  writer-side SQL.
- `api/*` owns FastAPI routes, dependencies, schemas, and live channels.
- `packages/shared/*` owns TypeScript DTOs and IPC contracts shared by Electron
  main and renderer.

Avoid importing input-specific OCR models into `application/*`. Convert to an
application/domain model first. `PositionProvider` is intentionally in
`application.position`, not in mining claims.

## SQLite And Threading

- SQLite writes go through one writer thread: `DbWriterWorker`.
- API reads open separate read connections via `api.dependencies`.
- Runtime commands may synchronously wait for their durable events to be
  persisted when the UI needs read-after-write behavior.
- Do not add ad hoc SQLite writes from input threads, API handlers, or UI code.

## Current Hot Areas

Check `docs/current-state.md` and `ROADMAP_2025-05-26.md` before touching these:

- run/segment correctness and setup snapshots
- claim lifecycle and manual claim repair actions
- loot aggregation vs raw `MiningItemReceivedEvent` spam
- OCR finder/position stability
- ROI calibration for finder and compass
- Electron UI map/dashboard polish

## Useful Commands

Root:

```bash
corepack pnpm dev
corepack pnpm bridge:verify
corepack pnpm frontend:verify
corepack pnpm verify
```

Backend:

```bash
cd apps/game-bridge
just test
just ocr
```

Frontend:

```bash
corepack pnpm --filter @zml/electron-ui dev
corepack pnpm --filter @zml/electron-ui typecheck
corepack pnpm --filter @zml/electron-ui build
```

Use focused checks during agent work unless the user asks for full verification.
