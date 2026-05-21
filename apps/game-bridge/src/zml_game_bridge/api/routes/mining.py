from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request

from zml_game_bridge.api.schemas.mining import MiningClaimDto, MiningDropDto
from zml_game_bridge.persistence.mining_claims import MiningClaimReader
from zml_game_bridge.persistence.mining_drops import MiningDropReader
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite
from zml_game_bridge.runtime.runtime import AppRuntime

router = APIRouter(prefix="/api/v1/mining", tags=["mining"])
logger = logging.getLogger(__name__)


def get_mining_conn(request: Request) -> Iterator[sqlite3.Connection]:
    runtime = cast(AppRuntime, request.app.state.runtime)
    conn = open_sqlite(runtime.db_path, check_same_thread=False)
    ensure_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


MiningConn = Annotated[sqlite3.Connection, Depends(get_mining_conn)]


@router.get("/drops", response_model=list[MiningDropDto])
def list_mining_drops(
    conn: MiningConn,
    window_minutes: Annotated[int, Query(ge=1, le=24 * 60)] = 30,
) -> list[MiningDropDto]:
    since_ts_ms = _now_ms() - window_minutes * 60_000
    rows = MiningDropReader(conn).list_since(since_ts_ms=since_ts_ms)
    logger.debug("api_request_read_drops window_minutes=%s rows=%s", window_minutes, len(rows))
    return [MiningDropDto.from_row(row) for row in rows]


@router.get("/claims", response_model=list[MiningClaimDto])
def list_mining_claims(
    conn: MiningConn,
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
