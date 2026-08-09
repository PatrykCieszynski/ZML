default:
    just --list

# Component task modules. Each module runs from its own project directory.
mod api 'packages/api-contract'
mod backend 'apps/game-bridge'
mod desktop 'apps/electron-ui'
mod ocr 'apps/ocr-agent'
mod protocol 'packages/ocr-protocol'
mod shared 'packages/shared'

# Resolve the complete Python workspace into the root lockfile.
python-lock:
    uv lock

# Synchronize all Python workspace members into the root .venv.
python-sync:
    uv sync --locked --all-packages

# Start the desktop development process. Electron owns the local backend lifecycle.
dev: python-sync api::generate shared::build
    pnpm --filter @zml/electron-ui dev

# Run the complete repository quality gate.
verify: python-sync protocol::verify ocr::verify backend::verify api::generate shared::verify desktop::verify

# Run all test suites that exist today.
test: protocol::test ocr::test backend::test desktop::test

# Run all configured linters.
lint: protocol::lint ocr::lint backend::lint desktop::lint

# Format Python components. TypeScript formatting is not enforced repository-wide yet.
format-python: protocol::format ocr::format backend::format

# Build TypeScript workspace artifacts.
build: api::generate shared::build desktop::build

# Stage already-packaged Python components into Electron resources.
stage-python:
    node scripts/stage-python-components.mjs

# Package both Python processes, stage them, then build the desktop installer.
package: python-sync ocr::package backend::package api::generate shared::build
    node scripts/stage-python-components.mjs
    just desktop package
