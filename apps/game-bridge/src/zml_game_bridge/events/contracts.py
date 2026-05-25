from collections.abc import Callable

from zml_game_bridge.events.base import SignalBase

SignalSink = Callable[[SignalBase], None]
