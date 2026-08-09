from __future__ import annotations

import os
import threading
from io import StringIO
from typing import cast

import uvicorn

from zml_game_bridge.main import _watch_parent_commands_with_signal
from zml_game_bridge.runtime.shutdown_signal import RuntimeShutdownSignal


class _FakeServer:
    should_exit = False


def test_parent_shutdown_command_requests_graceful_server_exit() -> None:
    server = _FakeServer()
    shutdown_signal = RuntimeShutdownSignal()

    _watch_parent_commands_with_signal(
        server=cast(uvicorn.Server, server),
        stream=StringIO("ignored\nshutdown\n"),
        shutdown_signal=shutdown_signal,
    )

    assert server.should_exit is True
    assert shutdown_signal.is_requested() is True


def test_closed_parent_pipe_requests_graceful_server_exit() -> None:
    server = _FakeServer()
    shutdown_signal = RuntimeShutdownSignal()

    _watch_parent_commands_with_signal(
        server=cast(uvicorn.Server, server),
        stream=StringIO(""),
        shutdown_signal=shutdown_signal,
    )

    assert server.should_exit is True
    assert shutdown_signal.is_requested() is True


def test_parent_pipe_is_polled_without_blocking_the_interpreter() -> None:
    server = _FakeServer()
    shutdown_signal = RuntimeShutdownSignal()
    read_fd, write_fd = os.pipe()

    try:
        with os.fdopen(read_fd, "r", encoding="utf-8") as stream:
            watcher = threading.Thread(
                target=_watch_parent_commands_with_signal,
                kwargs={
                    "server": cast(uvicorn.Server, server),
                    "stream": stream,
                    "shutdown_signal": shutdown_signal,
                },
                daemon=True,
            )
            watcher.start()
            os.write(write_fd, b"shutdown\n")
            watcher.join(timeout=1.0)

            assert watcher.is_alive() is False
            assert server.should_exit is True
            assert shutdown_signal.is_requested() is True
    finally:
        os.close(write_fd)
