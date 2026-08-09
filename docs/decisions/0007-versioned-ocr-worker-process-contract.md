# 0007 - Versioned OCR Worker Process Contract

Date: 2026-08-09

## Status

Accepted.

## Context

Screen capture and OCR originally ran inside Backend. The OCR code owns
native dependencies, CPU-heavy pipelines, capture retry behavior, debug
recording, and conversion of finder observations into backend signals. Moving
that work directly into a second process without a stable boundary would couple
the new process to Backend implementation modules and make incremental
migration difficult.

Finder `SignalBase` classes were also located under `inputs.ocr`, even though
application mining logic and mock input consume them. That made the application
layer depend on a specific noisy input implementation.

## Decision

Introduce `packages/ocr-protocol` as a small, independently tested Python
package shared by Backend and OCR Worker through local path
dependencies. Backend depends only on this contract package; the standalone
OCR Worker is a runtime process dependency rather than a Python dependency.

Protocol version 1 uses strict Pydantic discriminated unions and UTF-8 NDJSON:

- OCR Worker emits `hello`, `position`, `finder_signal`, `status`, `heartbeat`,
  and `command_result` messages;
- Backend sends `apply_config`, `capture_frame`, and `shutdown` commands;
- stdout is reserved for protocol messages and stderr is reserved for logs;
- the codec rejects malformed, oversized, directionally invalid, and
  unsupported-version messages;
- screenshots are represented by bounded file metadata and path tokens, never
  base64 image payloads.

The package imports no application modules and has no native OCR dependencies.
It contains transport DTOs and encoding only; it does not load environment
settings, start processes, perform I/O, or contain OCR/domain behavior.

Backend remains the owner of desired OCR configuration, mining application
logic, durable domain events, and persistence. OCR Worker owns applied
in-memory OCR configuration, capture, pipelines, and native OCR dependencies.

Move the six finder `SignalBase` classes to
`application.mining.signals.finder` without changing their fields or behavior.
The OCR runner emits protocol observations. A Backend input adapter maps
those observations to application signals. The backend runtime adapter knows
only process lifecycle, stdio transport, handshake, health, restart, and
shutdown behavior.

## Consequences

- Backend and OCR Worker can validate the same versioned contract without
  importing one another.
- Application mining code no longer imports finder signal types from
  `inputs.ocr`.
- Protocol fixtures can detect accidental wire-format changes before process
  integration exists.
- The repository gains another small Python package and lock file.
- Changes to required wire fields or semantics require an explicit protocol
  compatibility decision.
- The OCR pipelines live in an independently verified `apps/ocr-worker` project.
- Backend never imports `zml_ocr_worker` and does not install its native OCR
  dependencies; Electron/packaging supplies the Agent executable path.
- A missing or crashing Agent degrades OCR health and triggers bounded restart
  without terminating Backend.
