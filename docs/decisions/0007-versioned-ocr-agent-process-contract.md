# 0007 - Versioned OCR Agent Process Contract

Date: 2026-08-09

## Status

Accepted.

## Context

Screen capture and OCR currently run inside Game Bridge. The OCR code owns
native dependencies, CPU-heavy pipelines, capture retry behavior, debug
recording, and conversion of finder observations into backend signals. Moving
that work directly into a second process without a stable boundary would couple
the new process to Game Bridge implementation modules and make incremental
migration difficult.

Finder `SignalBase` classes were also located under `inputs.ocr`, even though
application mining logic and mock input consume them. That made the application
layer depend on a specific noisy input implementation.

## Decision

Introduce `packages/ocr-protocol` as a small, independently tested Python
package shared by Game Bridge and the future OCR Agent through local path
dependencies.

Protocol version 1 uses strict Pydantic discriminated unions and UTF-8 NDJSON:

- OCR Agent emits `hello`, `position`, `finder_signal`, `status`, `heartbeat`,
  and `command_result` messages;
- Game Bridge sends `apply_config`, `capture_frame`, and `shutdown` commands;
- stdout is reserved for protocol messages and stderr is reserved for logs;
- the codec rejects malformed, oversized, directionally invalid, and
  unsupported-version messages;
- screenshots are represented by bounded file metadata and path tokens, never
  base64 image payloads.

The package imports no application modules and has no native OCR dependencies.
It contains transport DTOs and encoding only; it does not load environment
settings, start processes, perform I/O, or contain OCR/domain behavior.

Game Bridge remains the owner of desired OCR configuration, mining application
logic, durable domain events, and persistence. OCR Agent will own applied
in-memory OCR configuration, capture, pipelines, and native OCR dependencies.

Move the six finder `SignalBase` classes to
`application.mining.signals.finder` without changing their fields or behavior.
The OCR runner emits protocol observations. During the embedded migration
phase, a Game Bridge adapter maps those observations to application signals.

## Consequences

- Game Bridge and OCR Agent can validate the same versioned contract without
  importing one another.
- Application mining code no longer imports finder signal types from
  `inputs.ocr`.
- Protocol fixtures can detect accidental wire-format changes before process
  integration exists.
- The repository gains another small Python package and lock file.
- Changes to required wire fields or semantics require an explicit protocol
  compatibility decision.
- The OCR pipelines now live in an independently verified `apps/ocr-agent`
  project, while runtime startup remains embedded until subprocess supervision
  is introduced.
