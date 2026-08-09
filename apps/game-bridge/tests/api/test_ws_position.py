from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from fastapi import WebSocket

from zml_game_bridge.api.routes.ws_position import ws_position
from zml_game_bridge.runtime.shutdown_signal import RuntimeShutdownSignal


class _FakePositionHub:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        self.unsubscribed = False

    def subscribe(self) -> tuple[asyncio.Queue[Any], None]:
        return self.queue, None

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        assert queue is self.queue
        self.unsubscribed = True


class _FakeWebSocket:
    def __init__(self, hub: _FakePositionHub) -> None:
        runtime = SimpleNamespace(
            position_hub=hub,
            shutdown_signal=RuntimeShutdownSignal(),
        )
        self.app = SimpleNamespace(state=SimpleNamespace(runtime=runtime))
        self.incoming: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict[str, str]:
        return await self.incoming.get()

    async def send_json(self, _data: object) -> None:
        return


def test_position_websocket_exits_when_client_disconnects() -> None:
    async def scenario() -> None:
        hub = _FakePositionHub()
        websocket = _FakeWebSocket(hub)
        handler = asyncio.create_task(ws_position(cast(WebSocket, websocket)))

        while not websocket.accepted:
            await asyncio.sleep(0)
        await websocket.incoming.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(handler, timeout=1.0)

        assert hub.unsubscribed is True

    asyncio.run(scenario())
