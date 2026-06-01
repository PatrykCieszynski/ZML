from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from zml_game_bridge.api.dependencies import ReadConn, RuntimeDep
from zml_game_bridge.api.schemas.mining import MiningClaimDto, MiningDropDto, MiningLootItemDto
from zml_game_bridge.application.mining.claims.commands import (
    IgnoreMiningClaimCommand,
    MarkMiningClaimDepletedCommand,
)
from zml_game_bridge.persistence.mining_claims import MiningClaimReader
from zml_game_bridge.persistence.mining_drops import MiningDropReader
from zml_game_bridge.persistence.mining_loot import MiningLootReader
from zml_game_bridge.persistence.run_state import RunState

router = APIRouter(prefix="/api/v1/mining", tags=["mining"])
logger = logging.getLogger(__name__)


class IgnoreMiningClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class MarkMiningClaimDepletedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


@router.get("/drops", response_model=list[MiningDropDto])
def list_mining_drops(
    conn: ReadConn,
    window_minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 30,
    run_id: Annotated[int | None, Query(ge=1)] = None,
    active_run: Annotated[bool, Query()] = False,
) -> list[MiningDropDto]:
    reader = MiningDropReader(conn)
    if active_run:
        active_run_id = RunState(conn).try_get_active_run_id()
        rows = [] if active_run_id is None else reader.list_for_run(run_id=active_run_id)
        logger.debug(
            "api_request_read_drops active_run=true run_id=%s rows=%s", active_run_id, len(rows)
        )
    elif run_id is not None:
        rows = reader.list_for_run(run_id=run_id)
        logger.debug("api_request_read_drops run_id=%s rows=%s", run_id, len(rows))
    else:
        since_ts_ms = _now_ms() - window_minutes * 60_000
        rows = reader.list_since(since_ts_ms=since_ts_ms)
        logger.debug("api_request_read_drops window_minutes=%s rows=%s", window_minutes, len(rows))
    return [MiningDropDto.from_row(row) for row in rows]


@router.get("/claims", response_model=list[MiningClaimDto])
def list_mining_claims(
    conn: ReadConn,
    active: Annotated[bool, Query()] = True,
    run_id: Annotated[int | None, Query(ge=1)] = None,
    active_run: Annotated[bool, Query()] = False,
) -> list[MiningClaimDto]:
    resolved_run_id = run_id
    if active_run:
        resolved_run_id = RunState(conn).try_get_active_run_id()
        if resolved_run_id is None:
            return []

    if not active:
        rows = MiningClaimReader(conn).list_all(run_id=resolved_run_id)
    else:
        rows = MiningClaimReader(conn).list_active(now_ts_ms=_now_ms(), run_id=resolved_run_id)
    logger.debug(
        "api_request_read_claims active=%s active_run=%s run_id=%s rows=%s",
        active,
        active_run,
        resolved_run_id,
        len(rows),
    )
    return [MiningClaimDto.from_row(row) for row in rows]


@router.post("/claims/{claim_id}/deplete", response_model=MiningClaimDto)
def mark_mining_claim_depleted(
    claim_id: str,
    runtime: RuntimeDep,
    conn: ReadConn,
    request: MarkMiningClaimDepletedRequest | None = None,
) -> MiningClaimDto:
    reader = MiningClaimReader(conn)
    row = reader.get(claim_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mining claim not found")
    if row.status == "depleted":
        return MiningClaimDto.from_row(row)
    if row.status == "ignored":
        raise HTTPException(status_code=409, detail="Cannot mark an ignored mining claim depleted")
    if row.position is None:
        raise HTTPException(
            status_code=409,
            detail="Cannot mark a mining claim depleted without a claim position",
        )

    reason = request.reason if request is not None else None
    runtime.execute_runtime_command(
        MarkMiningClaimDepletedCommand(
            claim_id=claim_id,
            event_dt=_now_dt(),
            position=row.position,
            distance_m=0.0,
            raw=reason,
            drop_id=row.drop_id,
            hit_id=row.hit_id,
            run_id=row.run_id,
            segment_id=row.segment_id,
        )
    )
    logger.debug("api_request_deplete_claim claim_id=%s reason=%r", claim_id, reason)
    updated = reader.get(claim_id)
    return MiningClaimDto.from_row(updated if updated is not None else row)


@router.post("/claims/{claim_id}/ignore", response_model=MiningClaimDto)
def ignore_mining_claim(
    claim_id: str,
    runtime: RuntimeDep,
    conn: ReadConn,
    request: IgnoreMiningClaimRequest | None = None,
) -> MiningClaimDto:
    reader = MiningClaimReader(conn)
    row = reader.get(claim_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mining claim not found")
    if row.status == "depleted":
        raise HTTPException(status_code=409, detail="Cannot ignore a depleted mining claim")
    if row.status == "ignored":
        return MiningClaimDto.from_row(row)

    reason = request.reason if request is not None else None
    runtime.execute_runtime_command(
        IgnoreMiningClaimCommand(
            claim_id=claim_id,
            ignored_ts_ms=_now_ms(),
            reason=reason,
            drop_id=row.drop_id,
            hit_id=row.hit_id,
            run_id=row.run_id,
            segment_id=row.segment_id,
        )
    )
    logger.debug("api_request_ignore_claim claim_id=%s reason=%r", claim_id, reason)
    updated = reader.get(claim_id)
    return MiningClaimDto.from_row(updated if updated is not None else row)


@router.get("/loot", response_model=list[MiningLootItemDto])
def list_mining_loot(
    conn: ReadConn,
    run_id: Annotated[int | None, Query(ge=1)] = None,
    active_run: Annotated[bool, Query()] = False,
) -> list[MiningLootItemDto]:
    resolved_run_id = run_id
    if active_run:
        resolved_run_id = RunState(conn).try_get_active_run_id()
        if resolved_run_id is None:
            return []

    rows = MiningLootReader(conn).list_all(run_id=resolved_run_id)
    logger.debug(
        "api_request_read_loot active_run=%s run_id=%s rows=%s",
        active_run,
        resolved_run_id,
        len(rows),
    )
    return [MiningLootItemDto.from_row(row) for row in rows]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _now_dt() -> datetime:
    return datetime.now().replace(microsecond=0)
