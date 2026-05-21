import logging
import threading
from pathlib import Path

from zml_game_bridge.events.contracts import SignalSink
from zml_game_bridge.inputs.chat.interpreter import interpret_chat_line
from zml_game_bridge.inputs.chat.parser import parse_chat_line
from zml_game_bridge.inputs.chat.tailer import tail_lines

logger = logging.getLogger(__name__)


def start_chat_input(
    path: Path,
    signal_sink: SignalSink,
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
    path_exists = path.exists()
    logger.info(
        "chat input started path=%s exists=%s start_at_end=%s",
        path,
        path_exists,
        start_at_end,
    )
    if not path_exists:
        logger.warning("chat log path does not exist yet: %s", path)

    for line in tail_lines(
        path, start_at_end=start_at_end, poll_interval_s=poll_interval_s, stop_event=stop_event
    ):
        chat_line = parse_chat_line(line)
        if chat_line is None:
            continue
        chat_event = interpret_chat_line(chat_line)
        if chat_event is None:
            continue
        logger.info(
            "chat signal type=%s event_dt=%s raw=%r",
            type(chat_event).__name__,
            chat_event.event_dt,
            chat_event.raw,
        )
        signal_sink(chat_event)
