# 0005 - Run Segments Are Setup Buckets

Date: 2026-06-01

## Status

Accepted as target behavior.

## Context

Users can change finder, amplifier, mode, ammo/probes, or extractor while
mining. The app needs run/segment stats, but finder UI can also emit temporary
mode/ammo changes when a tool runs out or the game toggles states.

Early segment behavior risked creating duplicate active segments or splitting a
run into too many chronological pieces.

## Decision

A segment is a setup bucket inside a run. It is created or reused when a valid
drop is recorded.

Segment-relevant setup:

- finder
- amplifier
- mining modes
- ammo/probes configuration

Extractor is not a segment boundary for MVP.

If the same setup hash appears again in the same run, the existing segment for
that setup should be reused instead of creating a duplicate. If chronological
episodes become important later, add separate `segment_episodes` rather than
overloading segment aggregation.

## Consequences

- No segment should be created from noisy setup changes alone.
- Drop context should include run and segment identifiers.
- Stats can aggregate reliably by setup.
- Implementation is still being hardened; check the roadmap before editing this
  area.

