from collections.abc import Callable

from zml_game_bridge.events.base import EventBase

RuntimeMessageSink = Callable[[EventBase], None]
EventSink = RuntimeMessageSink
SignalSink = RuntimeMessageSink
