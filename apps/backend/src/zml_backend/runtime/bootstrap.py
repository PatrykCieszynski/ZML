from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from zml_backend.application.mining import MiningCoordinator
from zml_backend.application.mining.equipment.service import MiningEquipmentService
from zml_backend.application.mining.segments.session import (
    MiningSegmentSetup,
    RunSessionService,
)
from zml_backend.application.mining.settings import default_id_factory
from zml_backend.application.position.input_processor import PositionInputProcessor
from zml_backend.application.position.model import PositionSnapshot
from zml_backend.application.position.tracking import PositionTrackingService
from zml_backend.events.contracts import SignalSink
from zml_backend.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_backend.inputs.ocr_worker.config import build_desired_ocr_config
from zml_backend.inputs.ocr_worker.message_mapper import OcrWorkerMessageMapper
from zml_backend.persistence.event_projector import CompositeEventProjector
from zml_backend.persistence.mining_claims import MiningClaimProjector
from zml_backend.persistence.mining_drops import MiningDropProjector
from zml_backend.persistence.mining_loot import MiningLootProjector
from zml_backend.persistence.position_state import (
    SetLastKnownPlanetCommand,
    load_last_known_planet,
)
from zml_backend.persistence.runs import RunSegmentProjector
from zml_backend.resources.mining_resources import MiningResourceCatalog
from zml_backend.runtime.channels import EventChannel, RuntimeInputChannel
from zml_backend.runtime.cloud_sync import CloudSyncClient, CloudSyncWorker
from zml_backend.runtime.db_commands import DbCommandChannel
from zml_backend.runtime.db_writer import DbWriterWorker
from zml_backend.runtime.input_coordinator import InputCoordinator
from zml_backend.runtime.input_processor import CompositeInputProcessor
from zml_backend.runtime.ocr_input import OcrInputSource
from zml_backend.runtime.ocr_worker.process_transport import OcrWorkerProcessConfig
from zml_backend.runtime.ocr_worker.supervisor import (
    OcrWorkerSupervisor,
    OcrWorkerSupervisorConfig,
)
from zml_backend.runtime.restore import MiningLifecycleRestorer
from zml_backend.runtime.supervisor import WorkerSupervisor
from zml_backend.settings import Settings


@dataclass(slots=True)
class RuntimeComponents:
    pending_inputs: RuntimeInputChannel
    pending_events: EventChannel
    pending_db_commands: DbCommandChannel
    persisted_events: InMemoryPersistedEventBus
    position_service: PositionTrackingService
    ocr_input_source: OcrInputSource
    cloud_sync_worker: CloudSyncWorker
    mining_equipment_service: MiningEquipmentService
    run_session_service: RunSessionService
    mining_coordinator: MiningCoordinator
    input_coordinator: InputCoordinator
    db_writer_worker: DbWriterWorker
    lifecycle_restorer: MiningLifecycleRestorer


def build_runtime_components(
    settings: Settings,
    *,
    supervisor: WorkerSupervisor,
) -> RuntimeComponents:
    pending_inputs = RuntimeInputChannel()
    pending_events = EventChannel()
    pending_db_commands = DbCommandChannel()
    persisted_events = InMemoryPersistedEventBus()
    position_service = PositionTrackingService(
        initial_planet_name=load_last_known_planet(settings.db_path)
    )

    def ingest_ocr_position(snapshot: PositionSnapshot) -> None:
        position_service.ingest_snapshot(snapshot)

    def persist_trusted_planet(planet_name: str) -> None:
        pending_db_commands.execute(SetLastKnownPlanetCommand(planet_name=planet_name))

    ocr_input_source = build_ocr_input_source(
        settings,
        supervisor=supervisor,
        position_sink=ingest_ocr_position,
        signal_sink=pending_inputs.emit,
    )
    resource_catalog = MiningResourceCatalog(user_path=settings.mining_resource_catalog_path)
    mining_equipment_service = MiningEquipmentService(path=settings.mining_tools_path)
    run_session_service = RunSessionService(
        db_path=settings.db_path,
        id_factory=default_id_factory,
    )

    def run_context_for_drop(observed_ts_ms: int, setup: MiningSegmentSetup):
        return run_session_service.context_for_drop(
            observed_ts_ms=observed_ts_ms,
            setup=setup,
        )

    def current_run_id() -> int | None:
        return run_session_service.current_run_id()

    def current_segment_id() -> str | None:
        return run_session_service.current_segment_id()

    mining_coordinator = MiningCoordinator(
        profile_provider=mining_equipment_service.get_equipment_profile,
        position_provider=position_service.get_latest_world_pos,
        resource_catalog=resource_catalog,
        run_context_provider=run_context_for_drop,
        run_id_provider=current_run_id,
        segment_id_provider=current_segment_id,
        db_command_executor=pending_db_commands.execute,
        mining_equipment_service=mining_equipment_service,
    )
    input_coordinator = InputCoordinator(
        pending_inputs=pending_inputs,
        pending_events=pending_events,
        input_processor=CompositeInputProcessor(
            [
                PositionInputProcessor(
                    position_service,
                    planet_observer=persist_trusted_planet,
                ),
                mining_coordinator,
            ]
        ),
        live_events=persisted_events,
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
                MiningLootProjector(),
            ]
        ),
    )
    cloud_sync_worker = build_cloud_sync_worker(
        settings,
        pending_db_commands=pending_db_commands,
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
        position_service=position_service,
        ocr_input_source=ocr_input_source,
        cloud_sync_worker=cloud_sync_worker,
        mining_equipment_service=mining_equipment_service,
        run_session_service=run_session_service,
        mining_coordinator=mining_coordinator,
        input_coordinator=input_coordinator,
        db_writer_worker=db_writer_worker,
        lifecycle_restorer=lifecycle_restorer,
    )


def build_ocr_input_source(
    settings: Settings,
    *,
    supervisor: WorkerSupervisor,
    position_sink: Callable[[PositionSnapshot], None],
    signal_sink: SignalSink,
) -> OcrInputSource:
    command = (
        (str(settings.ocr_worker_path), "stdio")
        if settings.ocr_worker_path is not None
        else ("zml-ocr-worker", "stdio")
    )
    mapper = OcrWorkerMessageMapper(
        position_sink=position_sink,
        signal_sink=signal_sink,
    )
    return OcrWorkerSupervisor(
        config=OcrWorkerSupervisorConfig(
            enabled=settings.ocr_enabled,
            desired_config=build_desired_ocr_config(settings),
            process=OcrWorkerProcessConfig(
                command=command,
                environment={},
            ),
        ),
        supervisor=supervisor,
        position_message_sink=mapper.map_position,
        finder_message_sink=mapper.map_finder,
    )


def build_cloud_sync_worker(
    settings: Settings,
    *,
    pending_db_commands: DbCommandChannel,
) -> CloudSyncWorker:
    base_url = settings.cloud_sync_base_url
    token = settings.cloud_sync_token
    client = (
        CloudSyncClient(base_url=base_url, token=token)
        if base_url is not None and token is not None
        else None
    )

    return CloudSyncWorker(
        db_path=settings.db_path,
        pending_db_commands=pending_db_commands,
        client=client,
        interval_s=settings.cloud_sync_interval_s,
        batch_size=settings.cloud_sync_batch_size,
    )


def build_worker_supervisor(settings: Settings) -> WorkerSupervisor:
    supervisor = WorkerSupervisor()
    supervisor.register("db_writer", enabled=True)
    supervisor.register("input_coordinator", enabled=True)
    supervisor.register(
        "claim_expiration_maintenance",
        enabled=settings.claim_expiration_maintenance_enabled,
    )
    supervisor.register("cloud_sync", enabled=True)
    supervisor.register("chat_tail", enabled=True)
    supervisor.register("ocr_worker", enabled=settings.ocr_enabled)
    supervisor.register("mock_mining_input", enabled=settings.mock_inputs_enabled)
    return supervisor
