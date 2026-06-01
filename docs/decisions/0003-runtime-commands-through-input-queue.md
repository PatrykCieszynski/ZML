# 0003 - Runtime Commands Through Input Queue

Date: 2026-06-01

## Status

Accepted, with some transitional code remaining.

## Context

UI actions can affect mining state: starting/stopping runs, changing active
equipment, marking a claim depleted, ignoring a false claim, and eventually
segment/run controls. If these actions bypass the mining coordinator, business
rules split between API routes and runtime services.

## Decision

State-changing mining actions should enter `RuntimeInputChannel` as runtime
commands. `InputCoordinator` processes commands sequentially through
`MiningCoordinator` and its command handlers. Commands may return a value to the
API and may emit durable events. When the UI needs read-after-write behavior,
the command path can wait until emitted events are persisted.

## Consequences

- Commands share ordering with input signals.
- Mining business logic stays in application services.
- API routes remain thin.
- Existing run commands still include transitional DB-backed command behavior.
  Do not copy that pattern into new domains unless deliberately extending the
  transitional bridge.

