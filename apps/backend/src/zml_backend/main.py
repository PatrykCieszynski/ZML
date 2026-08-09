from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import TextIO

import uvicorn

from zml_backend.runtime.shutdown_signal import (
    RuntimeShutdownSignal,
    process_shutdown_signal,
)
from zml_backend.settings import Settings, configure_logging_from_env

logger = logging.getLogger(__name__)

_PARENT_MANAGED_ENV = "ZML_PARENT_MANAGED"
_SHUTDOWN_COMMAND = "shutdown"
_PARENT_PIPE_POLL_INTERVAL_S = 0.05
_PARENT_PIPE_READ_SIZE = 4096
_GRACEFUL_SHUTDOWN_TIMEOUT_S = 15


def main() -> None:
    configure_logging_from_env()
    process_shutdown_signal.reset()
    s = Settings()
    if not _parent_managed():
        # Uvicorn factory: module:function + factory=True
        uvicorn.run(
            "zml_backend.api.app:create_app",
            factory=True,
            host=s.host,
            port=s.port,
            reload=s.reload,
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT_S,
        )
        return

    config = uvicorn.Config(
        "zml_backend.api.app:create_app",
        factory=True,
        host=s.host,
        port=s.port,
        reload=False,
        timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT_S,
    )
    server = uvicorn.Server(config)
    parent_watcher = threading.Thread(
        target=_watch_parent_commands,
        kwargs={"server": server, "stream": sys.stdin},
        name="zml-parent-watch",
        daemon=True,
    )
    parent_watcher.start()
    logger.info("backend_parent_management_enabled")
    server.run()


def _parent_managed() -> bool:
    value = os.getenv(_PARENT_MANAGED_ENV)
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def _watch_parent_commands(*, server: uvicorn.Server, stream: TextIO) -> None:
    _watch_parent_commands_with_signal(
        server=server,
        stream=stream,
        shutdown_signal=process_shutdown_signal,
    )


def _watch_parent_commands_with_signal(
    *,
    server: uvicorn.Server,
    stream: TextIO,
    shutdown_signal: RuntimeShutdownSignal,
) -> None:
    try:
        fd = stream.fileno()
        os.set_blocking(fd, False)
    except (AttributeError, OSError, ValueError):
        _watch_parent_text_stream(
            server=server,
            stream=stream,
            shutdown_signal=shutdown_signal,
        )
        return

    pending = b""
    while not server.should_exit:
        try:
            chunk = os.read(fd, _PARENT_PIPE_READ_SIZE)
        except BlockingIOError:
            time.sleep(_PARENT_PIPE_POLL_INTERVAL_S)
            continue
        except OSError as exc:
            logger.info("backend_parent_pipe_closed error=%s", exc)
            shutdown_signal.request()
            server.should_exit = True
            return

        if not chunk:
            logger.info("backend_parent_pipe_closed")
            shutdown_signal.request()
            server.should_exit = True
            return

        pending += chunk
        lines = pending.split(b"\n")
        pending = lines.pop()
        for line in lines:
            if line.strip().lower() != _SHUTDOWN_COMMAND.encode("ascii"):
                continue
            logger.info("backend_shutdown_requested_by_parent")
            shutdown_signal.request()
            server.should_exit = True
            return


def _watch_parent_text_stream(
    *,
    server: uvicorn.Server,
    stream: TextIO,
    shutdown_signal: RuntimeShutdownSignal,
) -> None:
    for line in stream:
        if line.strip().lower() != _SHUTDOWN_COMMAND:
            continue
        logger.info("backend_shutdown_requested_by_parent")
        shutdown_signal.request()
        server.should_exit = True
        return

    logger.info("backend_parent_pipe_closed")
    shutdown_signal.request()
    server.should_exit = True


if __name__ == "__main__":
    main()
