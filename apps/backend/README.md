# Z Mining Log Backend

The Backend is the local Python application that turns noisy game inputs into durable mining state and exposes that state to the Desktop.

It owns FastAPI, application/domain logic, runtime orchestration, SQLite persistence, chat-log input, supervision of the standalone OCR Worker, and optional background claim synchronization to ZML Cloud.

## Boundary

```mermaid
flowchart TB
    Chat[chat.log] --> Inputs[Backend inputs]
    Worker[OCR Worker] -->|zml-ocr-protocol| Inputs
    Inputs --> App[Application / domain]

    App -->|writes durable events + projections| DB[(SQLite)]
    DB -.->|reads projections + history| API[FastAPI]
    App -->|commands / live state| API
    DB -.->|complete unsynced claims| CloudSync[Cloud sync worker]
    CloudSync -->|privacy-minimized HTTP batches| Cloud[ZML Cloud]

    API -->|REST / SSE / WebSocket| Desktop[Desktop]
```

The Backend **does not import the OCR Worker package or native OCR stack**. `zml-ocr-worker` is a child-process runtime dependency. The Python dependency shared across the boundary is only `zml-ocr-protocol`.

## Source layout

```text
src/zml_backend/
  api/          FastAPI routes, schemas, dependencies, SSE/WS channels
  application/  use cases, mining coordination, position tracking
  domain/       durable events, value objects, pure domain behavior
  inputs/       chat, OCR protocol, and mock adapters
  persistence/  SQLite schema, readers, journal, projections
  runtime/      queues, workers, lifecycle, supervision, bootstrap
  resources/    packaged seed/reference data
```

See [`../../docs/architecture.md`](../../docs/architecture.md) for cross-component flows.

## Runtime flow

```mermaid
flowchart TB
    Observations[OCR / chat / mock / UI command] --> Queue[RuntimeInputChannel]
    Queue --> Input[InputCoordinator]
    Input --> Mining[MiningCoordinator + services]
    Mining --> Events[Durable events]
    Events --> Writer[DbWriterWorker]
    Writer --> Journal[(events)]
    Writer --> Projections[(read models)]
    Writer --> SSE[PersistedEventBus / SSE]
```

Signals are transient observations. Events are durable facts. Do not persist raw input signals simply to make them observable.

## Commands

From the repository root:

```powershell
just backend --list
just backend config
just backend dev
just backend mock
just backend ocr
just backend finder-debug
just backend test
just backend verify
just backend package
```

`just backend verify` runs Ruff lint, Ruff format check, Pyright, and Pytest.

### Input modes

The developer CLI supports:

- `env` — use current environment configuration;
- `live` — OCR enabled, mock mining disabled;
- `mock` — OCR disabled, mock mining enabled;
- `hybrid` — OCR and mock mining enabled;
- `no-inputs` — both disabled.

The root `just dev` path normally starts Backend through Electron rather than running it manually.

## OCR Worker supervision

Backend starts the worker through `runtime/ocr_worker` and adapts protocol observations under `inputs/ocr_worker`.

The supervisor provides:

- child-process stdin/stdout/stderr transport;
- hello/capability validation;
- complete revisioned `apply_config` handshake;
- sequence-ID validation;
- heartbeat monitoring;
- structured worker health;
- bounded restart/backoff;
- graceful shutdown with terminate/kill escalation.

A missing Entropia window is treated as a recoverable capture condition rather than a reason to crash/restart the process.

The architecture test `tests/test_ocr_process_boundary.py` protects this separation.

## Cloud claim synchronization

Cloud synchronization is opt-in and runs in a background worker. Local SQLite remains the source of truth and recording a claim never waits for the network.

A claim becomes eligible when the local projection contains all public-map fields required by ZML Cloud:

```text
claim_id
planet_name
x / y
resource_name
size_index
observed_ts_ms
```

The worker uploads up to 250 pending claims at a time to `POST /api/v1/sync/claims`. Server outcomes are stored durably in `cloud_claim_sync` through `DbWriterWorker`; `accepted` and `already_present` are both terminal successful outcomes, while permanent per-item rejection is retained with its reason.

Transient HTTP/network failures do not change local claim state and are retried on a later interval. No cost, ammo, finder, amplifier, run-return, or bankroll data is included in the cloud payload.

For development against a local ZML Cloud instance:

```text
ZML_CLOUD_BASE_URL=http://localhost:8080
ZML_CLOUD_SYNC_TOKEN=zml_<secret>
```

Optional tuning:

```text
ZML_CLOUD_SYNC_INTERVAL_S=600
ZML_CLOUD_SYNC_BATCH_SIZE=250
```

The sync token is treated as a secret and is never written to logs or SQLite by this feature. Browser-based device pairing will replace manual token configuration later; the cloud transport intentionally does not depend on Discord credentials.

## Persistence rules

SQLite has one writer: `DbWriterWorker`.

- Durable events and their projections are written in the same transaction.
- API routes and background workers may open separate read connections.
- Input threads, API handlers, and background workers must not create a second ad-hoc write path.
- Player-position ticks are live telemetry and are not persisted as a raw stream.

Monetary amounts are stored as integer mPEC to avoid floating-point drift:

```text
1 PED = 100 PEC = 100000 mPEC
```

## API surfaces

The Backend exposes three categories of local transport:

- **REST** for queries, snapshots, and commands;
- **SSE** (`/events/stream`) for persisted event notifications;
- **WebSocket** (`/ws/position`) for high-frequency position telemetry.

FastAPI/Pydantic HTTP schemas are the source of truth for `packages/api-contract`. When a REST schema changes, regenerate the TypeScript contract with:

```powershell
just api generate
```

## Key configuration

Most runtime configuration is environment-driven through `zml_backend.settings.Settings`.

Common variables:

```text
ZML_HOST / ZML_PORT
ZML_APP_DATA_DIR
ZML_DB_PATH
ZML_CHAT_LOG_PATH
ZML_OCR_ENABLED
ZML_OCR_WORKER_PATH
ZML_OCR_CAPTURE_HZ
ZML_OCR_PROFILE_PATH
ZML_MOCK_INPUTS
ZML_CLOUD_BASE_URL
ZML_CLOUD_SYNC_TOKEN
ZML_LOG_LEVEL
```

OCR recording/profiling and path overrides are also available; `settings.py` is the authoritative configuration source.

## Application data

Default development Backend state:

```text
<repo>/.tmp/appdata/backend
```

Packaged state:

```text
%LOCALAPPDATA%/z-mining-log
```

`ZML_APP_DATA_DIR` overrides the base directory, while explicit path variables such as `ZML_DB_PATH` take precedence for their individual resource.

## Packaging

```powershell
just backend package
```

produces:

```text
apps/backend/dist/zml-backend/zml-backend.exe
```

The artifact intentionally excludes OCR-native dependencies. Full artifact/process-tree verification is documented in [`../../docs/packaging.md`](../../docs/packaging.md).
