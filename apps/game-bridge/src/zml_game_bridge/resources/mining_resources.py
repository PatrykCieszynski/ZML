from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any, Literal, cast

MiningResourceType = Literal["ore", "enmatter", "treasure", "other", "unknown"]
MiningResourceSource = Literal["seed", "user", "learned"]

logger = logging.getLogger(__name__)

_RESOURCE_TYPES: set[str] = {"ore", "enmatter", "treasure", "other", "unknown"}
_RESOURCE_SOURCES: set[str] = {"seed", "user", "learned"}
_GROUP_TYPES: Mapping[str, MiningResourceType] = {
    "ores": "ore",
    "ore": "ore",
    "enmatters": "enmatter",
    "enmatter": "enmatter",
    "treasure": "treasure",
    "treasures": "treasure",
    "other": "other",
}


@dataclass(frozen=True, slots=True)
class MiningResource:
    name: str
    resource_type: MiningResourceType
    track_as_loot: bool = True
    source: MiningResourceSource = "seed"
    first_seen_event_dt: str | None = None
    last_seen_event_dt: str | None = None


class MiningResourceCatalog:
    def __init__(
        self,
        *,
        seed_path: Path | None = None,
        user_path: Path | None = None,
    ) -> None:
        self._user_path = user_path
        self._lock = threading.Lock()
        self._seed_entries = _load_seed_entries(seed_path)
        self._user_entries = _load_entries_from_path(user_path, default_source="user")

    def get(self, name: str) -> MiningResource | None:
        key = normalize_resource_name(name)
        return self._user_entries.get(key) or self._seed_entries.get(key)

    def is_tracked_loot(self, name: str) -> bool:
        resource = self.get(name)
        return bool(resource is not None and resource.track_as_loot)

    def learn_resource(
        self,
        *,
        name: str,
        resource_type: str | MiningResourceType,
        event_dt: datetime | None,
    ) -> MiningResource:
        key = normalize_resource_name(name)
        if not key:
            raise ValueError("resource name must not be blank")

        seen_event_dt = event_dt.isoformat() if event_dt is not None else None
        learned_type = _coerce_resource_type(resource_type)

        with self._lock:
            current_user = self._user_entries.get(key)
            current = current_user or self._seed_entries.get(key)
            if current_user is not None and current_user.source == "user":
                entry = MiningResource(
                    name=current_user.name,
                    resource_type=current_user.resource_type,
                    track_as_loot=current_user.track_as_loot,
                    source="user",
                    first_seen_event_dt=current_user.first_seen_event_dt or seen_event_dt,
                    last_seen_event_dt=seen_event_dt or current_user.last_seen_event_dt,
                )
            else:
                entry = MiningResource(
                    name=current.name if current is not None else " ".join(name.split()),
                    resource_type=learned_type,
                    track_as_loot=current.track_as_loot if current is not None else True,
                    source="learned",
                    first_seen_event_dt=(
                        current.first_seen_event_dt if current is not None else seen_event_dt
                    ),
                    last_seen_event_dt=seen_event_dt
                    or (current.last_seen_event_dt if current is not None else None),
                )

            self._user_entries[key] = entry
            self._write_user_entries()
            return entry

    def _write_user_entries(self) -> None:
        if self._user_path is None:
            return

        resources = [
            _resource_to_json(entry)
            for entry in sorted(self._user_entries.values(), key=lambda resource: resource.name)
        ]
        payload = {
            "version": 1,
            "resources": resources,
        }
        self._user_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._user_path.with_name(f"{self._user_path.name}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self._user_path)


def normalize_resource_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _load_seed_entries(seed_path: Path | None) -> dict[str, MiningResource]:
    if seed_path is not None:
        return _load_entries_from_path(seed_path, default_source="seed")

    try:
        seed_text = (
            importlib_resources.files("zml_game_bridge.resources")
            .joinpath("mining_resources.seed.json")
            .read_text(encoding="utf-8")
        )
        payload = json.loads(seed_text)
    except Exception:
        logger.exception("mining_resource_seed_load_failed")
        return {}
    return _entries_from_payload(payload, default_source="seed")


def _load_entries_from_path(
    path: Path | None,
    *,
    default_source: MiningResourceSource,
) -> dict[str, MiningResource]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("mining_resource_catalog_load_failed path=%s", path)
        return {}
    return _entries_from_payload(payload, default_source=default_source)


def _entries_from_payload(
    payload: object,
    *,
    default_source: MiningResourceSource,
) -> dict[str, MiningResource]:
    if not isinstance(payload, dict):
        return {}

    entries: dict[str, MiningResource] = {}
    raw = cast(dict[str, Any], payload)

    resources = raw.get("resources", [])
    if isinstance(resources, list):
        for item in cast(list[object], resources):
            entry = _entry_from_resource_item(item, default_source=default_source)
            if entry is not None:
                entries[normalize_resource_name(entry.name)] = entry

    for group_key, resource_type in _GROUP_TYPES.items():
        group = raw.get(group_key) or raw.get(group_key.capitalize())
        if not isinstance(group, list):
            continue
        for name in cast(list[object], group):
            if not isinstance(name, str) or not normalize_resource_name(name):
                continue
            entry = MiningResource(
                name=" ".join(name.split()),
                resource_type=resource_type,
                track_as_loot=True,
                source=default_source,
            )
            entries[normalize_resource_name(entry.name)] = entry

    return entries


def _entry_from_resource_item(
    item: object,
    *,
    default_source: MiningResourceSource,
) -> MiningResource | None:
    if isinstance(item, str):
        name = " ".join(item.split())
        if not name:
            return None
        return MiningResource(name=name, resource_type="unknown", source=default_source)

    if not isinstance(item, dict):
        return None

    raw = cast(dict[str, Any], item)
    name_value = raw.get("name")
    if not isinstance(name_value, str):
        return None
    name = " ".join(name_value.split())
    if not name:
        return None

    return MiningResource(
        name=name,
        resource_type=_coerce_resource_type(raw.get("type") or raw.get("resource_type")),
        track_as_loot=_coerce_bool(raw.get("track_as_loot"), default=True),
        source=_coerce_source(raw.get("source"), default=default_source),
        first_seen_event_dt=_coerce_optional_str(raw.get("first_seen_event_dt")),
        last_seen_event_dt=_coerce_optional_str(raw.get("last_seen_event_dt")),
    )


def _resource_to_json(resource: MiningResource) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": resource.name,
        "type": resource.resource_type,
        "track_as_loot": resource.track_as_loot,
        "source": resource.source,
    }
    if resource.first_seen_event_dt is not None:
        payload["first_seen_event_dt"] = resource.first_seen_event_dt
    if resource.last_seen_event_dt is not None:
        payload["last_seen_event_dt"] = resource.last_seen_event_dt
    return payload


def _coerce_resource_type(value: object) -> MiningResourceType:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _RESOURCE_TYPES:
            return cast(MiningResourceType, normalized)
    return "unknown"


def _coerce_source(value: object, *, default: MiningResourceSource) -> MiningResourceSource:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _RESOURCE_SOURCES:
            return cast(MiningResourceSource, normalized)
    return default


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
