# 0001 - Signals Vs Events

Date: 2026-06-01

## Status

Accepted.

## Context

Inputs are noisy. OCR can misread text, chat messages can arrive before finder
OCR, and mock/debug sources may emit temporary observations. Persisting every
technical observation made the event table confusing and forced UI/live buses to
carry data that was not a durable domain fact.

## Decision

Use two names consistently:

- `Signal`: internal observation from OCR/chat/mock/API-facing runtime input.
- `Event`: durable domain fact worth persisting and usually worth streaming.

Signals enter `RuntimeInputChannel`. `InputCoordinator` gives them to
`MiningCoordinator`. The coordinator and its sub-services decide whether to
produce durable events. Signals are not put in `EventEnvelope` and are not
published on the persisted event bus.

## Consequences

- The DB event log is cleaner.
- UI receives only persisted durable facts through SSE.
- Debug logging for OCR/chat signals stays in input/coordinator logs.
- New input sources should emit signals first, not durable events directly.

