from __future__ import annotations

import asyncio
from typing import Any, cast

from fastapi import Request

from zml_backend.api.channels.sse_hub import SseClient
from zml_backend.api.routes.events import events_stream
from zml_backend.runtime.runtime import AppRuntime
from zml_backend.runtime.shutdown_signal import RuntimeShutdownSignal


class _FakeSseHub:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.unregistered = False

    def register(self) -> SseClient:
        return SseClient(client_id=1, queue=self.queue)

    def unregister(self, client_id: int) -> None:
        assert client_id == 1
        self.unregistered = True


def test_event_stream_exits_promptly_when_runtime_stops() -> None:
    async def scenario() -> None:
        hub = _FakeSseHub()
        shutdown_signal = RuntimeShutdownSignal()
        runtime = cast(
            AppRuntime,
            type(
                "Runtime",
                (),
                {"sse_hub": hub, "shutdown_signal": shutdown_signal},
            )(),
        )
        response = await events_stream(cast(Request, object()), runtime)
        iterator = response.body_iterator.__aiter__()

        assert await anext(iterator) == ": connected\n\n"
        next_chunk = asyncio.create_task(anext(iterator))
        shutdown_signal.request()

        try:
            await asyncio.wait_for(next_chunk, timeout=1.0)
        except StopAsyncIteration:
            pass
        else:
            raise AssertionError("SSE iterator should stop after runtime shutdown")

        assert hub.unregistered is True

    asyncio.run(scenario())
