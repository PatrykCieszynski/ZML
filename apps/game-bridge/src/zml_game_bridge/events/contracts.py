from collections.abc import Callable

from zml_game_bridge.events.base import EventBase

EventSink = Callable[[EventBase], None]