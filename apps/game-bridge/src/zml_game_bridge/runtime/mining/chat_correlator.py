from __future__ import annotations

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.inputs.chat.signals import ChatSignalBase


class MiningChatCorrelator:
    def process(self, signal: EventBase) -> list[EventBase]:
        if not isinstance(signal, ChatSignalBase):
            return []

        # Chat signals are intentionally routed here, but durable mining events
        # will be added in focused steps per signal family: claimed, depleted,
        # item received, enhancer broke.
        return []
