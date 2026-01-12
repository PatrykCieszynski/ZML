import threading
from pathlib import Path

from zml_game_bridge.inputs.chat.interpreter import interpret_chat_line
from zml_game_bridge.inputs.chat.parser import parse_chat_line
from zml_game_bridge.inputs.chat.tailer import tail_lines

def main(path: Path, start_at_end: bool = False, poll_interval_s: float = 0.05) -> None:
    stop_event = threading.Event()
    try:
        for line in tail_lines(path, start_at_end=start_at_end, poll_interval_s=poll_interval_s, stop_event=stop_event):
            chatLine = parse_chat_line(line)
            if chatLine is None:
                continue
            chatEvent = interpret_chat_line(chatLine)
            print(chatEvent)
    except KeyboardInterrupt:
        stop_event.set()

if __name__ == "__main__":
    p = Path("../../testing/chat.log")
    a = "alfa"
    main(p, start_at_end=True)