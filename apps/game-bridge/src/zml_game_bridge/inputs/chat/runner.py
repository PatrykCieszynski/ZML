import threading
from pathlib import Path

from zml_game_bridge.events.contracts import EventSink
from zml_game_bridge.inputs.chat.interpreter import interpret_chat_line
from zml_game_bridge.inputs.chat.parser import parse_chat_line
from zml_game_bridge.inputs.chat.tailer import tail_lines

def start_chat_input(
    path: Path,
    event_sink: EventSink,
    stop_event: threading.Event,
    start_at_end: bool = False,
    poll_interval_s: float = 0.05,
) -> None:
    # TODO: Decide whether to swallow interpreter exceptions or fail-fast.
    # TODO translate deeds in ItemReceived lines to resource type for multi resource mining (It seems the order is preserved)
    # 2026-01-12 15:18:40 [System] [] You received Mineral Resource Deed x (1) Value: 0.0000 PED
    # 2026-01-12 15:18:40 [System] [] You received Energy Matter Resource Deed x (1) Value: 0.0000 PED
    # 2026-01-12 15:18:40 [System] [] You have claimed a resource! (Zorn Star Ore)
    # 2026-01-12 15:18:40 [System] [] You have claimed a resource! (Blue Crystal)
    for line in tail_lines(path, start_at_end=start_at_end, poll_interval_s=poll_interval_s, stop_event=stop_event):
        chat_line = parse_chat_line(line)
        if chat_line is None:
            continue
        chat_event = interpret_chat_line(chat_line)
        if chat_event is None:
            continue
        event_sink(chat_event)
