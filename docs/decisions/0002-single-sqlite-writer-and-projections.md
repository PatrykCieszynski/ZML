# 0002 - Single SQLite Writer And Projections

Date: 2026-06-01

## Status

Accepted.

## Context

The app has multiple concurrent inputs: OCR, chat tailing, mock input, REST API,
SSE, WebSocket position updates, and Desktop commands. SQLite allows many
readers but only one writer at a time. Direct writes from multiple threads risk
`database is locked` errors and inconsistent state.

## Decision

All durable SQLite writes go through `DbWriterWorker`.

The writer persists the durable event to the event journal and updates read
model projections in the same transaction. API routes use read-only/read
connections for queries.

## Consequences

- Input threads and API routes must not write directly to mining tables.
- Projection tables are safe because they are written by the single writer.
- If event persistence fails, projection writes roll back with it.
- Read endpoints can be simple and fast because projections are query-shaped.

