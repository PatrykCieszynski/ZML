from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class EventBase:
    persist: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class SignalBase(EventBase):
    persist: ClassVar[bool] = False


def should_persist_event(event: EventBase) -> bool:
    return bool(getattr(type(event), "persist", True))
