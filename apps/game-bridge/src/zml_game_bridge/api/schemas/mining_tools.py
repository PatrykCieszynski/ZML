from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from zml_game_bridge.domain.mining_cost import (
    MiningEquipmentProfile,
    calculate_extraction_cost,
    effective_finder_radius_m,
)
from zml_game_bridge.domain.money import mpec_to_int
from zml_game_bridge.runtime.mining.tools import (
    ActiveMiningTools,
    MiningToolKind,
    MiningToolProfileRecord,
)


class MiningToolProfileDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str
    kind: MiningToolKind
    name: str
    decay_mpec: int
    markup_percent: str
    radius_m: float | None = None

    @classmethod
    def from_record(cls, record: MiningToolProfileRecord) -> MiningToolProfileDto:
        return cls(
            tool_id=record.tool_id,
            kind=record.kind,
            name=record.name,
            decay_mpec=mpec_to_int(record.decay_mpec),
            markup_percent=record.markup_percent,
            radius_m=record.radius_m,
        )


class CreateMiningToolProfileRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MiningToolKind
    name: str
    decay_mpec: int
    markup_percent: str = "100"
    radius_m: float | None = None


class SetActiveMiningToolsRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finder_id: str | None = None
    amp_id: str | None = None
    extractor_id: str | None = None
    finder_range_enhancer_count: int = 0


class ActiveMiningToolsDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finder_id: str | None
    amp_id: str | None
    extractor_id: str | None
    finder_range_enhancer_count: int
    effective_finder_radius_m: float | None
    extraction_cost_mpec: int | None

    @classmethod
    def from_active(
        cls,
        active: ActiveMiningTools,
        *,
        effective_finder_radius_m: float | None,
        extraction_cost_mpec: int | None,
    ) -> ActiveMiningToolsDto:
        return cls(
            finder_id=active.finder_id,
            amp_id=active.amp_id,
            extractor_id=active.extractor_id,
            finder_range_enhancer_count=active.finder_range_enhancer_count,
            effective_finder_radius_m=effective_finder_radius_m,
            extraction_cost_mpec=extraction_cost_mpec,
        )


def active_tools_dto(
    active: ActiveMiningTools,
    *,
    equipment_profile: MiningEquipmentProfile,
) -> ActiveMiningToolsDto:
    extraction_cost = calculate_extraction_cost(equipment_profile)
    return ActiveMiningToolsDto.from_active(
        active,
        effective_finder_radius_m=effective_finder_radius_m(equipment_profile),
        extraction_cost_mpec=mpec_to_int(extraction_cost) if extraction_cost is not None else None,
    )
