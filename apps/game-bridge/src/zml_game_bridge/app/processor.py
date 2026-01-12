import os
from pathlib import Path

from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.inputs.chat.runner import start_chat_input
from zml_game_bridge.storage.event_store import EventStore

# TODO get path from config
local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home())
db_path = Path(local_app_data) / "zabu-mining-log" / "db" / "events.sqlite3"

def open_event_store() -> EventStore:
    store = EventStore(db_path)
    store.open()
    return store

def sink_print(envelope: EventEnvelope) -> None:
    print(envelope)

if __name__ == "__main__":
    event_store = open_event_store()
    p = Path("../testing/chat.log")
    start_chat_input(p, sink=sink_print, db_store=event_store, start_at_end=True)