from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from zml_game_bridge.domain.mining_cost import (
    FinderRangeEnhancerLoadout,
    MiningEquipmentProfile,
    MiningToolProfile,
)
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.domain.rate import percent
from zml_game_bridge.runtime.mining.settings import default_mining_equipment_profile

logger = logging.getLogger(__name__)

MiningToolKind = Literal["finder", "amp", "extractor"]


@dataclass(frozen=True, slots=True)
class MiningToolProfileRecord:
    tool_id: str
    kind: MiningToolKind
    name: str
    decay_mpec: Mpec
    markup_percent: str = "100"
    radius_m: float | None = None

    def to_tool_profile(self) -> MiningToolProfile:
        return MiningToolProfile(
            name=self.name,
            decay_mpec=self.decay_mpec,
            markup=percent(self.markup_percent),
            radius_m=self.radius_m,
        )


@dataclass(frozen=True, slots=True)
class ActiveMiningTools:
    finder_id: str | None = None
    amp_id: str | None = None
    extractor_id: str | None = None
    finder_range_enhancer_count: int = 0


class MiningToolService:
    def __init__(self, *, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._tools: dict[str, MiningToolProfileRecord] = {}
        self._active = ActiveMiningTools()
        self._load()

    def list_profiles(self) -> list[MiningToolProfileRecord]:
        with self._lock:
            return sorted(
                self._tools.values(),
                key=lambda tool: (_tool_kind_sort(tool.kind), tool.name, tool.tool_id),
            )

    def get_profile(self, tool_id: str) -> MiningToolProfileRecord | None:
        with self._lock:
            return self._tools.get(tool_id)

    def create_profile(
        self,
        *,
        kind: MiningToolKind,
        name: str,
        decay_mpec: Mpec,
        markup_percent: str = "100",
        radius_m: float | None = None,
    ) -> MiningToolProfileRecord:
        _validate_tool_profile(
            kind=kind,
            name=name,
            decay_mpec=decay_mpec,
            markup_percent=markup_percent,
            radius_m=radius_m,
        )
        record = MiningToolProfileRecord(
            tool_id=uuid4().hex,
            kind=kind,
            name=name.strip(),
            decay_mpec=decay_mpec,
            markup_percent=markup_percent.strip(),
            radius_m=radius_m,
        )
        with self._lock:
            self._tools[record.tool_id] = record
            self._save_locked()
        logger.info("mining_tool_created tool_id=%s kind=%s name=%r", record.tool_id, kind, name)
        return record

    def delete_profile(self, tool_id: str) -> bool:
        with self._lock:
            deleted = self._tools.pop(tool_id, None)
            if deleted is None:
                return False
            self._active = _active_without_deleted_tool(self._active, deleted)
            self._save_locked()
        logger.info("mining_tool_deleted tool_id=%s kind=%s name=%r", tool_id, deleted.kind, deleted.name)
        return True

    def active_tools(self) -> ActiveMiningTools:
        with self._lock:
            return self._active

    def set_active_tools(
        self,
        *,
        finder_id: str | None,
        amp_id: str | None,
        extractor_id: str | None,
        finder_range_enhancer_count: int,
    ) -> ActiveMiningTools:
        with self._lock:
            _validate_active_tool_id(self._tools, finder_id, "finder")
            _validate_active_tool_id(self._tools, amp_id, "amp")
            _validate_active_tool_id(self._tools, extractor_id, "extractor")
            if finder_range_enhancer_count < 0:
                raise ValueError("finder_range_enhancer_count must be non-negative")

            self._active = ActiveMiningTools(
                finder_id=finder_id,
                amp_id=amp_id,
                extractor_id=extractor_id,
                finder_range_enhancer_count=finder_range_enhancer_count,
            )
            self._save_locked()
            active = self._active
        logger.info(
            "mining_tools_active_set finder_id=%s amp_id=%s extractor_id=%s "
            "finder_range_enhancer_count=%s",
            active.finder_id,
            active.amp_id,
            active.extractor_id,
            active.finder_range_enhancer_count,
        )
        return active

    def get_equipment_profile(self) -> MiningEquipmentProfile:
        with self._lock:
            default_profile = default_mining_equipment_profile()
            finder = (
                self._tools[self._active.finder_id].to_tool_profile()
                if self._active.finder_id is not None
                else default_profile.finder
            )
            amp = (
                self._tools[self._active.amp_id].to_tool_profile()
                if self._active.amp_id is not None
                else None
            )
            extractor = (
                self._tools[self._active.extractor_id].to_tool_profile()
                if self._active.extractor_id is not None
                else None
            )
            return MiningEquipmentProfile(
                finder=finder,
                amp=amp,
                extractor=extractor,
                finder_range_enhancers=FinderRangeEnhancerLoadout(
                    count=self._active.finder_range_enhancer_count
                ),
                fallback_ammo_per_drop=default_profile.fallback_ammo_per_drop,
                fallback_probes_per_drop=default_profile.fallback_probes_per_drop,
            )

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        raw_obj: object = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw_obj, dict):
            raise ValueError(f"Invalid mining tools config: {self._path}")
        raw = cast(dict[str, Any], raw_obj)

        tools = cast(object, raw.get("tools", []))
        if not isinstance(tools, list):
            raise ValueError(f"Invalid mining tools list: {self._path}")
        tools_list = cast(list[object], tools)

        loaded_tools: dict[str, MiningToolProfileRecord] = {}
        for item in tools_list:
            if not isinstance(item, dict):
                continue
            record = _tool_from_json(cast(dict[str, object], item))
            loaded_tools[record.tool_id] = record

        active = _active_from_json(cast(object, raw.get("active")))
        with self._lock:
            self._tools = loaded_tools
            self._active = _sanitize_active_tools(active, loaded_tools)

    def _save_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tools": [_tool_to_json(tool) for tool in self.list_profiles()],
            "active": asdict(self._active),
        }
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)


def _validate_tool_profile(
    *,
    kind: MiningToolKind,
    name: str,
    decay_mpec: Mpec,
    markup_percent: str,
    radius_m: float | None,
) -> None:
    if kind not in ("finder", "amp", "extractor"):
        raise ValueError(f"Unsupported tool kind: {kind}")
    if not name.strip():
        raise ValueError("Tool name must not be empty")
    if mpec_to_int(decay_mpec) < 0:
        raise ValueError("decay_mpec must be non-negative")
    if percent(markup_percent).ppm < 0:
        raise ValueError("markup_percent must be non-negative")
    if kind == "finder" and (radius_m is None or radius_m <= 0):
        raise ValueError("Finder radius_m must be positive")
    if kind != "finder" and radius_m is not None:
        raise ValueError("Only finder profiles can define radius_m")


def _validate_active_tool_id(
    tools: dict[str, MiningToolProfileRecord],
    tool_id: str | None,
    expected_kind: MiningToolKind,
) -> None:
    if tool_id is None:
        return
    tool = tools.get(tool_id)
    if tool is None:
        raise ValueError(f"Unknown {expected_kind} tool id: {tool_id}")
    if tool.kind != expected_kind:
        raise ValueError(f"Tool {tool_id} is {tool.kind}, expected {expected_kind}")


def _tool_to_json(tool: MiningToolProfileRecord) -> dict[str, object]:
    return {
        "tool_id": tool.tool_id,
        "kind": tool.kind,
        "name": tool.name,
        "decay_mpec": mpec_to_int(tool.decay_mpec),
        "markup_percent": tool.markup_percent,
        "radius_m": tool.radius_m,
    }


def _tool_from_json(item: dict[str, object]) -> MiningToolProfileRecord:
    kind = item.get("kind")
    if kind not in ("finder", "amp", "extractor"):
        raise ValueError(f"Unsupported tool kind in config: {kind}")
    tool_id = item.get("tool_id")
    name = item.get("name")
    decay_mpec = item.get("decay_mpec")
    markup_percent = item.get("markup_percent", "100")
    radius_m = item.get("radius_m")
    if not isinstance(tool_id, str) or not isinstance(name, str) or not isinstance(decay_mpec, int):
        raise ValueError("Invalid tool profile config")
    if not isinstance(markup_percent, str):
        raise ValueError("Invalid tool markup config")
    if radius_m is not None and not isinstance(radius_m, int | float):
        raise ValueError("Invalid tool radius config")
    record = MiningToolProfileRecord(
        tool_id=tool_id,
        kind=kind,
        name=name,
        decay_mpec=Mpec(decay_mpec),
        markup_percent=markup_percent,
        radius_m=float(radius_m) if radius_m is not None else None,
    )
    _validate_tool_profile(
        kind=record.kind,
        name=record.name,
        decay_mpec=record.decay_mpec,
        markup_percent=record.markup_percent,
        radius_m=record.radius_m,
    )
    return record


def _active_from_json(value: object) -> ActiveMiningTools:
    if not isinstance(value, dict):
        return ActiveMiningTools()
    item = cast(dict[str, object], value)
    finder_id = item.get("finder_id")
    amp_id = item.get("amp_id")
    extractor_id = item.get("extractor_id")
    enhancer_count = item.get("finder_range_enhancer_count", 0)
    return ActiveMiningTools(
        finder_id=finder_id if isinstance(finder_id, str) else None,
        amp_id=amp_id if isinstance(amp_id, str) else None,
        extractor_id=extractor_id if isinstance(extractor_id, str) else None,
        finder_range_enhancer_count=enhancer_count if isinstance(enhancer_count, int) else 0,
    )


def _sanitize_active_tools(
    active: ActiveMiningTools,
    tools: dict[str, MiningToolProfileRecord],
) -> ActiveMiningTools:
    return ActiveMiningTools(
        finder_id=_valid_active_id(active.finder_id, tools, "finder"),
        amp_id=_valid_active_id(active.amp_id, tools, "amp"),
        extractor_id=_valid_active_id(active.extractor_id, tools, "extractor"),
        finder_range_enhancer_count=max(active.finder_range_enhancer_count, 0),
    )


def _active_without_deleted_tool(
    active: ActiveMiningTools,
    deleted: MiningToolProfileRecord,
) -> ActiveMiningTools:
    if deleted.tool_id == active.finder_id:
        return ActiveMiningTools(
            finder_id=None,
            amp_id=active.amp_id,
            extractor_id=active.extractor_id,
            finder_range_enhancer_count=0,
        )
    if deleted.tool_id == active.amp_id:
        return ActiveMiningTools(
            finder_id=active.finder_id,
            amp_id=None,
            extractor_id=active.extractor_id,
            finder_range_enhancer_count=active.finder_range_enhancer_count,
        )
    if deleted.tool_id == active.extractor_id:
        return ActiveMiningTools(
            finder_id=active.finder_id,
            amp_id=active.amp_id,
            extractor_id=None,
            finder_range_enhancer_count=active.finder_range_enhancer_count,
        )
    return active


def _valid_active_id(
    tool_id: str | None,
    tools: dict[str, MiningToolProfileRecord],
    expected_kind: MiningToolKind,
) -> str | None:
    if tool_id is None:
        return None
    tool = tools.get(tool_id)
    if tool is None or tool.kind != expected_kind:
        return None
    return tool_id


def _tool_kind_sort(kind: MiningToolKind) -> int:
    match kind:
        case "finder":
            return 0
        case "amp":
            return 1
        case "extractor":
            return 2
    raise ValueError(f"Unsupported tool kind: {kind}")
