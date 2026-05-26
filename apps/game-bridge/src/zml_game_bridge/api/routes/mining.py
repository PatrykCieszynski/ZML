from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Query

from zml_game_bridge.api.dependencies import ReadConn
from zml_game_bridge.api.schemas.mining import MiningClaimDto, MiningDropDto
from zml_game_bridge.persistence.mining_claims import MiningClaimReader
from zml_game_bridge.persistence.mining_drops import MiningDropReader
from zml_game_bridge.persistence.run_state import RunState

router = APIRouter(prefix="/api/v1/mining", tags=["mining"])
logger = logging.getLogger(__name__)


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


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
