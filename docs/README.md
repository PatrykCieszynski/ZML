# Z Mining Log Documentation

The documentation is intentionally split by ownership instead of duplicating the same architecture description in multiple files.

## Current documentation

- [`architecture.md`](architecture.md) — runtime boundaries, data flow, contracts, persistence, and lifecycle.
- [`development.md`](development.md) — setup, common commands, local state, generated contracts, and focused verification.
- [`packaging.md`](packaging.md) — Python artifacts, Electron staging, Windows installer, and release CI.
- [`current-state.md`](current-state.md) — compact handoff of what works now and the next high-value work.
- [`decisions/`](decisions/) — historical architecture decision records.

Component-specific details live beside the component:

- [`../apps/backend/README.md`](../apps/backend/README.md)
- [`../apps/desktop/README.md`](../apps/desktop/README.md)
- [`../apps/ocr-worker/README.md`](../apps/ocr-worker/README.md)
- [`../packages/api-contract/README.md`](../packages/api-contract/README.md)
- [`../packages/ocr-protocol/README.md`](../packages/ocr-protocol/README.md)

## Source-of-truth rule

Current code/configuration is authoritative. These documents should describe the current system. ADRs are historical records and can intentionally describe older names or superseded approaches.
