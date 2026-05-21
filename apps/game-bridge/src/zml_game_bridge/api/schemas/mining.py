from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from zml_game_bridge.domain.money import mpec_to_int
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.persistence.mining_claims import MiningClaimRow
from zml_game_bridge.persistence.mining_drops import MiningDropRow


class MiningDropPositionDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planet_name: str | None
    x: int
    y: int
    z: int | None = None


class MiningDropCostDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ammo_cost_mpec: int
    probes_cost_mpec: int
    finder_decay_mpec: int
    finder_enhancer_decay_mpec: int
    amp_decay_mpec: int
    total_mpec: int


class MiningDropDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drop_id: str
    drop_event_id: int
    observed_ts_ms: int
    position: MiningDropPositionDto | None
    drop_radius_m: float
    modes_mask: int | None
    probes_per_drop: int | None
    ammo_per_drop: int | None
    cost: MiningDropCostDto
    result: str
    result_event_id: int | None
    result_observed_ts_ms: int | None
    hit_id: str | None
    hit_event_id: int | None
    resource_name: str | None
    size_label: str | None
    size_index: int | None
    expected_expires_ts_ms: int | None
    range_m: float | None
    depth_m: float | None

    @classmethod
    def from_row(cls, row: MiningDropRow) -> MiningDropDto:
        position = (
            MiningDropPositionDto(
                planet_name=row.position.planet_name,
                x=row.position.x,
                y=row.position.y,
                z=row.position.z,
            )
            if row.position is not None
            else None
        )
        return cls(
            drop_id=row.drop_id,
            drop_event_id=row.drop_event_id,
            observed_ts_ms=row.observed_ts_ms,
            position=position,
            drop_radius_m=row.drop_radius_m,
            modes_mask=row.modes_mask,
            probes_per_drop=row.probes_per_drop,
            ammo_per_drop=row.ammo_per_drop,
            cost=MiningDropCostDto(
                ammo_cost_mpec=mpec_to_int(row.ammo_cost_mpec),
                probes_cost_mpec=mpec_to_int(row.probes_cost_mpec),
                finder_decay_mpec=mpec_to_int(row.finder_decay_mpec),
                finder_enhancer_decay_mpec=mpec_to_int(row.finder_enhancer_decay_mpec),
                amp_decay_mpec=mpec_to_int(row.amp_decay_mpec),
                total_mpec=mpec_to_int(row.total_cost_mpec),
            ),
            result=row.result,
            result_event_id=row.result_event_id,
            result_observed_ts_ms=row.result_observed_ts_ms,
            hit_id=row.hit_id,
            hit_event_id=row.hit_event_id,
            resource_name=row.resource_name,
            size_label=row.size_label,
            size_index=row.size_index,
            expected_expires_ts_ms=row.expected_expires_ts_ms,
            range_m=row.range_m,
            depth_m=row.depth_m,
        )


class MiningClaimPositionDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planet_name: str | None
    x: int
    y: int
    z: int | None = None


class MiningClaimDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    created_event_id: int
    hit_id: str | None
    drop_id: str | None
    observed_ts_ms: int
    position: MiningClaimPositionDto | None
    search_radius_m: float | None
    resource_name: str | None
    size_label: str | None
    size_index: int | None
    expected_expires_ts_ms: int | None
    range_m: float | None
    depth_m: float | None
    status: str
    depleted_event_id: int | None
    depleted_event_dt: str | None
    depleted_position: MiningClaimPositionDto | None
    depleted_distance_m: float | None

    @classmethod
    def from_row(cls, row: MiningClaimRow) -> MiningClaimDto:
        return cls(
            claim_id=row.claim_id,
            created_event_id=row.created_event_id,
            hit_id=row.hit_id,
            drop_id=row.drop_id,
            observed_ts_ms=row.observed_ts_ms,
            position=_claim_position_dto(row.position),
            search_radius_m=row.search_radius_m,
            resource_name=row.resource_name,
            size_label=row.size_label,
            size_index=row.size_index,
            expected_expires_ts_ms=row.expected_expires_ts_ms,
            range_m=row.range_m,
            depth_m=row.depth_m,
            status=row.status,
            depleted_event_id=row.depleted_event_id,
            depleted_event_dt=(
                row.depleted_event_dt.isoformat() if row.depleted_event_dt is not None else None
            ),
            depleted_position=_claim_position_dto(row.depleted_position),
            depleted_distance_m=row.depleted_distance_m,
        )


def _claim_position_dto(position: WorldPos | None) -> MiningClaimPositionDto | None:
    return (
        MiningClaimPositionDto(
            planet_name=position.planet_name,
            x=position.x,
            y=position.y,
            z=position.z,
        )
        if position is not None
        else None
    )
