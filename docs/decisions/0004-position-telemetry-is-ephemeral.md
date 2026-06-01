# 0004 - Position Telemetry Is Ephemeral

Date: 2026-06-01

## Status

Accepted.

## Context

OCR position updates arrive frequently, roughly several times per second. They
are useful for the live map and for attaching a position snapshot to mining
events, but a full persisted position stream would be noisy and not useful for
MVP accounting.

## Decision

Position OCR feeds `PositionTrackingService`. The service keeps latest trusted
position state, filters outliers, and publishes live updates through WebSocket.
Mining logic receives a fresh snapshot through `PositionProvider` when deriving
events.

Raw position ticks are not persisted to SQLite.

## Consequences

- Map movement stays responsive without DB pressure.
- Mining events can still capture the relevant position.
- Position model belongs in `application.position` / `domain.position`, not in
  OCR-specific input packages.
- Future trusted `/pos` chat events should enter the same application position
  path or a clearly defined trusted-position signal path.

