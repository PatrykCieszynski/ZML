from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

from zml_game_bridge.events.base import EventBase


def event_payload_json(event: EventBase) -> str:
    payload = serialize_event_payload(event)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def serialize_event_payload(event: EventBase) -> dict[str, Any]:
    if is_dataclass(event):
        payload = asdict(event)
        payload.pop("event_dt", None)
        payload.pop("channel_type", None)
        payload.pop("channel_token", None)
        payload.pop("raw", None)
    else:
        payload = dict(getattr(event, "__dict__", {}))
    return _to_jsonable(payload)


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return str(obj)

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in cast(dict[object, object], obj).items():
            result[str(key)] = _to_jsonable(value)
        return result

    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(value) for value in cast(list[object] | tuple[object, ...], obj)]

    return str(obj)
