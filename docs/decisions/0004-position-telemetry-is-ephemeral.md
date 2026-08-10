# 0004 - Position Telemetry Is Ephemeral

Date: 2026-06-01

## Status

Accepted.

## Context

OCR position updates arrive frequently, roughly several times per second. They
are useful for the live map and for attaching a position snapshot to mining
events, but a full persisted position stream would be noisy and not useful for
MVP accounting.

The planet name is different from the high-frequency coordinates. ZML needs a
stable planet context across restarts so that OCR-derived positions and mining
claims do not lose their planet merely because the user has not issued a fresh
`/pos` command since startup.

## Decision

Position OCR feeds `PositionTrackingService`. The service keeps latest trusted
position state, filters outliers, and publishes live updates through WebSocket.
Mining logic receives a fresh snapshot through `PositionProvider` when deriving
events.

Raw position ticks and coordinates are not persisted to SQLite.

ZML may persist only the **last known planet name** as low-frequency application
state. For the MVP, a trusted in-game `/pos` chat message is the authoritative
way for the user to change that planet context. A new trusted `/pos` overwrites
the stored planet. On restart, the stored planet is restored before OCR position
updates arrive, but no historical X/Y/Z coordinate is restored.

ZML does not guess the current planet from coordinates and does not silently
fall back to a fixed default planet.

## Consequences

- Map movement stays responsive without DB pressure.
- Mining events can still capture the relevant position.
- Position model belongs in `application.position` / `domain.position`, not in
  OCR-specific input packages.
- Trusted `/pos` chat events enter the same application position path and update
  the persisted last-known-planet context.
- After changing planets, the user is expected to issue `/pos` before mining so
  ZML can authoritatively switch planet context.
- Restarts no longer require another `/pos` when the user is still on the same
  planet.
- Persisting the planet does not turn position telemetry into durable history;
  coordinates and high-frequency samples remain ephemeral.
