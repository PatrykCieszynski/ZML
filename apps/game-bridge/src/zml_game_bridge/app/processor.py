import os
import threading
from pathlib import Path
from threading import Thread

from zml_game_bridge.app.db_writer import DbWriter
from zml_game_bridge.app.event_gateway import EventGateway
from zml_game_bridge.events.bus_in_memory import InMemoryEventBus
from zml_game_bridge.inputs.chat.runner import start_chat_input

# TODO get path from config
local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home())
db_path = Path(local_app_data) / "zabu-mining-log" / "db" / "events.sqlite3"


if __name__ == "__main__":
    p = Path("../testing/chat.log")
    memory_bus = InMemoryEventBus()
    event_gateway = EventGateway()
    db_writer = DbWriter(db_path=db_path, gateway=event_gateway, bus=memory_bus)

    stop_event = threading.Event()
    t_db_writer = Thread(target=db_writer.run, kwargs={"stop_event": stop_event})
    t_chat = Thread(target=start_chat_input, kwargs={"path": p, "event_sink": event_gateway.emit, "stop_event": stop_event, "start_at_end": True})

    t_db_writer.start()
    t_chat.start()
    sub = memory_bus.subscribe(lambda env: print(f"New event stored: {env}"))
    try:
        while t_chat.is_alive() or t_db_writer.is_alive():
            t_chat.join(timeout=0.2)
            t_db_writer.join(timeout=0.2)
    except KeyboardInterrupt:
        stop_event.set()
        t_chat.join()
        t_db_writer.join()
    finally:
        stop_event.set()