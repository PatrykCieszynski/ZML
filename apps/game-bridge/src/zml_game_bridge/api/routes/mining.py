from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request

from zml_game_bridge.api.schemas.mining import MiningDropDto
from zml_game_bridge.persistence.mining_drops import MiningDropReader
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite
from zml_game_bridge.runtime.runtime import AppRuntime

router = APIRouter(prefix="/api/v1/mining", tags=["mining"])


def get_mining_conn(request: Request) -> Iterator[sqlite3.Connection]:
    runtime = cast(AppRuntime, request.app.state.runtime)
    conn = open_sqlite(runtime.db_path)
    ensure_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


MiningConn = Annotated[sqlite3.Connection, Depends(get_mining_conn)]


@router.get("/drops", response_model=list[MiningDropDto])
def list_mining_drops(
    conn: MiningConn,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> list[MiningDropDto]:
    rows = MiningDropReader(conn).list_latest(limit=limit)
    return [MiningDropDto.from_row(row) for row in rows]
