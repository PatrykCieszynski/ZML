# 0006 - Manual Claim Repair Actions

Date: 2026-06-01

## Status

Accepted.

## Context

The app can miss extraction events or create a false claim from OCR. These are
different operational problems:

- missed extraction: the claim was real, but the app failed to close it;
- false claim: OCR/debug state produced a claim that should not count.

Using one status for both would make stats and debugging less clear.

## Decision

Provide two manual map actions:

- `Mark extracted`: emit `MiningClaimDepletedEvent` and close the claim as
  depleted/extracted.
- `Ignore false claim`: emit `MiningClaimIgnoredEvent` and exclude the claim
  from active/stat views as an ignored false positive.

Both actions go through runtime command flow and DB writer persistence.

## Consequences

- UI can repair active claim state without directly editing the DB.
- Stats can distinguish real extracted claims from ignored bad data.
- Event log preserves the repair action for later reconstruction/debugging.

