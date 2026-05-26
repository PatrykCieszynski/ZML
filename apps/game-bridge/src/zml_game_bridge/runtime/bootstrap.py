from __future__ import annotations

from dataclasses import dataclass

from zml_game_bridge.application.mining import MiningCoordinator
from zml_game_bridge.application.mining.equipment.service import MiningEquipmentService
from zml_game_bridge.application.mining.segments.session import RunSessionService
from zml_game_bridge.application.mining.settings import default_id_factory
from zml_game_bridge.application.position.latest_position import LatestPositionState
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_game_bridge.persistence.event_projector import CompositeEventProjector
from zml_game_bridge.persistence.mining_claims import MiningClaimProjector
from zml_game_bridge.persistence.mining_drops import MiningDropProjector
from zml_game_bridge.persistence.runs import RunSegmentProjector
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog
from zml_game_bridge.runtime.channels import EventChannel, RuntimeInputChannel
from zml_game_bridge.runtime.db_commands import DbCommandChannel
from zml_game_bridge.runtime.db_writer import DbWriterWorker
from zml_game_bridge.runtime.input_coordinator import InputCoordinator
from zml_game_bridge.runtime.restore import MiningLifecycleRestorer
from zml_game_bridge.runtime.supervisor import WorkerSupervisor
from zml_game_bridge.settings import Settings


@dataclass(slots=True)
class RuntimeComponents:
    pending_inputs: RuntimeInputChannel
    pending_events: EventChannel
    pending_db_commands: DbCommandChannel
    persisted_events: InMemoryPersistedEventBus
    latest_position: LatestPositionState
    mining_equipment_service: MiningEquipmentService
    run_session_service: RunSessionService
    mining_coordinator: MiningCoordinator
    input_coordinator: InputCoordinator
    db_writer_worker: DbWriterWorker
    lifecycle_restorer: MiningLifecycleRestorer


def build_runtime_components(settings: Settings) -> RuntimeComponents:
    pending_inputs = RuntimeInputChannel()
    pending_events = EventChannel()
    pending_db_commands = DbCommandChannel()
    persisted_events = InMemoryPersistedEventBus()
    latest_position = LatestPositionState()
    resource_catalog = MiningResourceCatalog(user_path=settings.mining_resource_catalog_path)
    mining_equipment_service = MiningEquipmentService(path=settings.mining_tools_path)
    run_session_service = RunSessionService(
        db_path=settings.db_path,
        id_factory=default_id_factory,
    )

    def current_position() -> WorldPos | None:
        position = latest_position.get()
        return position.position if position is not None else None

    def run_context_for_drop(observed_ts_ms: int, profile: MiningEquipmentProfile):
        return run_session_service.context_for_drop(
            observed_ts_ms=observed_ts_ms,
            profile=profile,
        )

    mining_coordinator = MiningCoordinator(
        profile_provider=mining_equipment_service.get_equipment_profile,
        position_provider=current_position,
        resource_catalog=resource_catalog,
        run_context_provider=run_context_for_drop,
        db_command_executor=pending_db_commands.execute,
        mining_equipment_service=mining_equipment_service,
    )
    input_coordinator = InputCoordinator(
        pending_inputs=pending_inputs,
        pending_events=pending_events,
        input_processor=mining_coordinator,
    )
    db_writer_worker = DbWriterWorker(
        db_path=settings.db_path,
        pending_events=pending_events,
        pending_commands=pending_db_commands,
        persisted_events=persisted_events,
        projector=CompositeEventProjector(
            [
                RunSegmentProjector(),
                MiningDropProjector(),
                MiningClaimProjector(),
            ]
        ),
    )
    lifecycle_restorer = MiningLifecycleRestorer(
        db_path=settings.db_path,
        mining_coordinator=mining_coordinator,
    )

    return RuntimeComponents(
        pending_inputs=pending_inputs,
        pending_events=pending_events,
        pending_db_commands=pending_db_commands,
        persisted_events=persisted_events,
        latest_position=latest_position,
        mining_equipment_service=mining_equipment_service,
        run_session_service=run_session_service,
        mining_coordinator=mining_coordinator,
        input_coordinator=input_coordinator,
        db_writer_worker=db_writer_worker,
        lifecycle_restorer=lifecycle_restorer,
    )


def build_worker_supervisor(settings: Settings) -> WorkerSupervisor:
    supervisor = WorkerSupervisor()
    supervisor.register("db_writer", enabled=True)
    supervisor.register("input_coordinator", enabled=True)
    supervisor.register("chat_tail", enabled=True)
    supervisor.register("ocr_worker", enabled=settings.ocr_enabled)
    supervisor.register("mock_mining_input", enabled=settings.mock_inputs_enabled)
    return supervisor
