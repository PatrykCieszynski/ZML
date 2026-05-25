from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Query

from zml_game_bridge.api.dependencies import ReadConn
from zml_game_bridge.api.schemas.mining import MiningClaimDto, MiningDropDto
from zml_game_bridge.persistence.mining_claims import MiningClaimReader
from zml_game_bridge.persistence.mining_drops import MiningDropReader

router = APIRouter(prefix="/api/v1/mining", tags=["mining"])
logger = logging.getLogger(__name__)


@router.get("/drops", response_model=list[MiningDropDto])
def list_mining_drops(
    conn: ReadConn,
    window_minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 30,
) -> list[MiningDropDto]:
    since_ts_ms = _now_ms() - window_minutes * 60_000
    rows = MiningDropReader(conn).list_since(since_ts_ms=since_ts_ms)
    logger.debug("api_request_read_drops window_minutes=%s rows=%s", window_minutes, len(rows))
    return [MiningDropDto.from_row(row) for row in rows]


@router.get("/claims", response_model=list[MiningClaimDto])
def list_mining_claims(
    conn: ReadConn,
    active: Annotated[bool, Query()] = True,
) -> list[MiningClaimDto]:
    if not active:
        rows = MiningClaimReader(conn).list_all()
    else:
        rows = MiningClaimReader(conn).list_active(now_ts_ms=_now_ms())
    logger.debug("api_request_read_claims active=%s rows=%s", active, len(rows))
    return [MiningClaimDto.from_row(row) for row in rows]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
