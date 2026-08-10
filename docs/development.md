# Development

Updated: 2026-08-10

Z Mining Log uses `just` as the repository command interface, `uv` for the Python workspace, and pnpm for the TypeScript workspace.

## Prerequisites

- Windows 10/11 for live OCR and Windows packaging.
- Python 3.13 (the root `pyproject.toml` requires `>=3.13,<3.14`).
- `uv`.
- Node.js 22.
- pnpm 10.27 (pinned by the root `package.json`).
- `just`.

Corepack is optional. Use it if it is your preferred way to activate the pnpm version declared by the repository, but ZML does not otherwise depend on Corepack.

## First setup

From the repository root:

```powershell
uv python install 3.13
pnpm install --frozen-lockfile
just python-sync
```

The Python workspace has one root lockfile and one root `.venv`. Do not create per-app virtual environments unless a specific experiment explicitly requires isolation.

Python workspace members:

```text
apps/backend
apps/ocr-worker
packages/ocr-protocol
```

TypeScript workspace members are discovered from `apps/*` and `packages/*`; the active JS packages are the Desktop and generated API contract.

## Start the application

```powershell
just dev
```

This performs:

1. `uv sync --locked --all-packages`;
2. REST contract generation from FastAPI/OpenAPI;
3. `pnpm --filter @zml/desktop dev`.

In the default development path Electron owns the Backend process and passes it the OCR Worker executable from the root `.venv`.

## Root commands

```text
just dev            Start Desktop; Desktop manages the local Backend
just verify         Full repository quality gate
just test           Run all test suites
just lint           Run configured linters
just format-python  Format Python components
just build          Generate API contract and build Desktop
just package        Build Python artifacts and Windows Desktop package
just python-sync    Sync all Python workspace members
just python-lock    Refresh the root uv lock
```

Use `just --list` for the exact current command set.

## Component commands

### Backend

```powershell
just backend dev
just backend mock
just backend ocr
just backend finder-debug
just backend config
just backend test
just backend verify
just backend package
```

Input modes are implemented by the backend developer CLI:

- `env`: use environment configuration as-is;
- `live`: OCR on, mock mining off;
- `mock`: OCR off, mock mining enabled;
- `hybrid`: OCR and mock mining enabled;
- `no-inputs`: neither source enabled.

See [`../apps/backend/README.md`](../apps/backend/README.md) for backend-specific configuration.

### OCR Worker

```powershell
just ocr doctor
just ocr stdio
just ocr finder-debug --help
just ocr test
just ocr verify
just ocr package
```

`stdio` is a protocol mode: stdout is reserved for NDJSON protocol traffic and logs go to stderr.

### OCR protocol

```powershell
just protocol test
just protocol verify
```

### API contract

```powershell
just api generate
```

This exports FastAPI OpenAPI and generates TypeScript wire types under `packages/api-contract`. Generated outputs are ignored by Git and should not be edited manually.

### Desktop

```powershell
just desktop dev
just desktop dev-mocks
just desktop typecheck
just desktop test
just desktop verify
just desktop package
```

## Development with mocks

For renderer/UI work without a live Backend/game process:

```powershell
just desktop dev-mocks
```

Backend also has a mock input mode when testing the real API/runtime path:

```powershell
just backend mock
```

Choose the smallest mode that exercises the boundary you are changing.

## Local application state

Development state is kept inside the repository so it cannot collide with an installed build:

```text
.tmp/appdata/backend/    SQLite, config, logs, OCR artifacts
.tmp/appdata/electron/   Electron preferences and window state
```

The packaged application uses `%LOCALAPPDATA%/z-mining-log` for Backend state unless `ZML_APP_DATA_DIR` overrides it.

## Backend URL and lifecycle overrides

Desktop defaults to `http://127.0.0.1:17171`.

- `ZML_BACKEND_URL` selects another Backend address.
- An explicit Backend URL is treated as externally managed by default.
- `ZML_MANAGE_BACKEND=0` disables Desktop process ownership.
- `ZML_MANAGE_BACKEND=1` can explicitly enable ownership where appropriate.

When Desktop owns the Backend, it performs health polling, bounded restart, and graceful shutdown through the parent stdin pipe.

## Focused verification

During normal iteration, prefer the component gate that corresponds to the change:

```powershell
just backend verify
just ocr verify
just protocol verify
just api generate
just desktop verify
```

The full repository gate is:

```powershell
just verify
```

CI additionally builds and smoke-tests the Windows Python process tree because that boundary cannot be fully validated by ordinary unit tests.

## Agent wrapper

`scripts/agent-env.cmd` and `scripts/agent-env.ps1` keep uv/pnpm temp/cache state under the repository and can be useful in restricted Windows agent shells.

Example:

```powershell
.\scripts\agent-env.cmd -- just backend test
```

This wrapper does not define architecture or dependency ownership; it only prepares a predictable command environment.

## Generated files and locks

- `uv.lock` is the Python dependency lock for the whole Python workspace.
- `pnpm-lock.yaml` is the JS/TS dependency lock and is required by frozen CI installs.
- `pnpm-workspace.yaml` defines JS workspace discovery and Electron build dependency policy.
- `packages/api-contract/openapi.json` and `schema.d.ts` are generated/ignored artifacts.

Do not delete lock/workspace files as cleanup unless the workspace topology actually changes.
