from collections.abc import Callable

from zml_backend.events.base import SignalBase

SignalSink = Callable[[SignalBase], None]
