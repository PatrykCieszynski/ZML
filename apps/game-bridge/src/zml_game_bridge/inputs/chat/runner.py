import threading
from collections.abc import Callable
from pathlib import Path

from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.inputs.chat.interpreter import interpret_chat_line
from zml_game_bridge.inputs.chat.parser import parse_chat_line
from zml_game_bridge.inputs.chat.tailer import tail_lines
from zml_game_bridge.storage.event_store import EventStore

def start_chat_input(path: Path, sink: Callable[[EventEnvelope], None], db_store: EventStore, start_at_end: bool = False, poll_interval_s: float = 0.05) -> None:
    stop_event = threading.Event()
    try:
        for line in tail_lines(path, start_at_end=start_at_end, poll_interval_s=poll_interval_s, stop_event=stop_event):
            chat_line = parse_chat_line(line)
            if chat_line is None:
                continue
            chat_event = interpret_chat_line(chat_line)
            if chat_event is None:
                continue
            event_envelop = db_store.append(chat_event)
            sink(event_envelop)
    except KeyboardInterrupt:
        stop_event.set()