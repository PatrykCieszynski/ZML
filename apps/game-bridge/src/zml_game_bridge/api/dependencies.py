from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request

from zml_game_bridge.persistence.events import EventReader
from zml_game_bridge.persistence.sqlite import open_read_connection
from zml_game_bridge.runtime.runtime import AppRuntime


def get_runtime(request: Request) -> AppRuntime:
    return cast(AppRuntime, request.app.state.runtime)


RuntimeDep = Annotated[AppRuntime, Depends(get_runtime)]


def get_read_conn(runtime: RuntimeDep) -> Iterator[sqlite3.Connection]:
    conn = open_read_connection(runtime.db_path)
    try:
        yield conn
    finally:
        conn.close()


ReadConn = Annotated[sqlite3.Connection, Depends(get_read_conn)]


def get_event_reader(runtime: RuntimeDep) -> Iterator[EventReader]:
    event_reader = EventReader(db_path=runtime.db_path, check_same_thread=False)
    event_reader.open()
    try:
        yield event_reader
    finally:
        event_reader.close()


EventReaderDep = Annotated[EventReader, Depends(get_event_reader)]
