from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from zml_backend.settings import Settings

app = typer.Typer(
    help="Developer CLI for running and inspecting the Z Mining Log Backend.",
    no_args_is_help=True,
)
console = Console()


class InputMode(StrEnum):
    ENV = "env"
    LIVE = "live"
    MOCK = "mock"
    HYBRID = "hybrid"
    NO_INPUTS = "no-inputs"


def _apply_env_overrides(
    *,
    mode: InputMode,
    db_path: Path | None,
    chat_log_path: Path | None,
    ocr_profile_path: Path | None,
    finder_debug: bool,
    finder_recording: str | None = None,
    finder_recording_dir: Path | None = None,
    finder_recording_interval_s: float | None = None,
    finder_recording_max_samples: int | None = None,
    finder_presence_check: bool | None = None,
    position_roi_snapshots: bool | None = None,
    position_roi_snapshot_dir: Path | None = None,
    position_roi_snapshot_interval_s: float | None = None,
    position_roi_snapshot_max_samples: int | None = None,
    ocr_profiling: bool = False,
    ocr_profiling_interval_s: float | None = None,
    log_level: str | None,
    mock_interval_ms: int | None,
) -> None:
    match mode:
        case InputMode.ENV:
            pass
        case InputMode.LIVE:
            os.environ["ZML_OCR_ENABLED"] = "1"
            os.environ["ZML_MOCK_INPUTS"] = "0"
        case InputMode.MOCK:
            os.environ["ZML_OCR_ENABLED"] = "0"
            os.environ["ZML_MOCK_INPUTS"] = "1"
        case InputMode.HYBRID:
            os.environ["ZML_OCR_ENABLED"] = "1"
            os.environ["ZML_MOCK_INPUTS"] = "1"
        case InputMode.NO_INPUTS:
            os.environ["ZML_OCR_ENABLED"] = "0"
            os.environ["ZML_MOCK_INPUTS"] = "0"

    if db_path is not None:
        os.environ["ZML_DB_PATH"] = str(db_path)
    if chat_log_path is not None:
        os.environ["ZML_CHAT_LOG_PATH"] = str(chat_log_path)
    if ocr_profile_path is not None:
        os.environ["ZML_OCR_PROFILE_PATH"] = str(ocr_profile_path)
    if finder_debug:
        os.environ["ZML_FINDER_DEBUG"] = "1"
    if finder_recording is not None:
        os.environ["ZML_FINDER_RECORDING"] = finder_recording
    if finder_recording_dir is not None:
        os.environ["ZML_FINDER_RECORDING_DIR"] = str(finder_recording_dir)
    if finder_recording_interval_s is not None:
        if finder_recording_interval_s <= 0:
            raise typer.BadParameter("finder recording interval must be greater than 0")
        os.environ["ZML_FINDER_RECORDING_INTERVAL_S"] = str(finder_recording_interval_s)
    if finder_recording_max_samples is not None:
        if finder_recording_max_samples < 0:
            raise typer.BadParameter("finder recording max samples cannot be negative")
        os.environ["ZML_FINDER_RECORDING_MAX_SAMPLES"] = str(finder_recording_max_samples)
    if finder_presence_check is not None:
        os.environ["ZML_FINDER_PRESENCE_CHECK"] = "1" if finder_presence_check else "0"
    if position_roi_snapshots is not None:
        os.environ["ZML_POSITION_ROI_SNAPSHOTS"] = "1" if position_roi_snapshots else "0"
    if position_roi_snapshot_dir is not None:
        os.environ["ZML_POSITION_ROI_SNAPSHOT_DIR"] = str(position_roi_snapshot_dir)
    if position_roi_snapshot_interval_s is not None:
        if position_roi_snapshot_interval_s <= 0:
            raise typer.BadParameter("position ROI snapshot interval must be greater than 0")
        os.environ["ZML_POSITION_ROI_SNAPSHOT_INTERVAL_S"] = str(position_roi_snapshot_interval_s)
    if position_roi_snapshot_max_samples is not None:
        if position_roi_snapshot_max_samples < 0:
            raise typer.BadParameter("position ROI snapshot max samples cannot be negative")
        os.environ["ZML_POSITION_ROI_SNAPSHOT_MAX_SAMPLES"] = str(position_roi_snapshot_max_samples)
    if ocr_profiling:
        os.environ["ZML_OCR_PROFILING"] = "1"
    if ocr_profiling_interval_s is not None:
        if ocr_profiling_interval_s <= 0:
            raise typer.BadParameter("OCR profiling interval must be greater than 0")
        os.environ["ZML_OCR_PROFILING_INTERVAL_S"] = str(ocr_profiling_interval_s)
    if log_level is not None:
        os.environ["ZML_LOG_LEVEL"] = log_level.upper()
    if mock_interval_ms is not None:
        if mock_interval_ms <= 0:
            raise typer.BadParameter("mock interval must be greater than 0")
        os.environ["ZML_MOCK_MINING_INTERVAL_MS"] = str(mock_interval_ms)


def _settings_table(settings: Settings) -> Table:
    table = Table(title="Z Mining Log Backend config", show_header=True, header_style="bold")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")

    table.add_row("host", settings.host)
    table.add_row("port", str(settings.port))
    table.add_row("reload", _format_bool(settings.reload))
    table.add_row("db_path", str(settings.db_path))
    table.add_row("chat_log_path", _format_path(settings.chat_log_path))
    table.add_row("mining_resource_catalog_path", str(settings.mining_resource_catalog_path))
    table.add_row("mining_tools_path", str(settings.mining_tools_path))
    table.add_row("ocr_profile_path", str(settings.ocr_profile_path))
    table.add_row(
        "chat_log_exists",
        _format_bool(settings.chat_log_path is not None and settings.chat_log_path.exists()),
    )
    table.add_row("chat_start_at_end", _format_bool(settings.chat_start_at_end))
    table.add_row("ocr_enabled", _format_bool(settings.ocr_enabled))
    table.add_row("ocr_worker_path", _format_path(settings.ocr_worker_path))
    table.add_row("ocr_capture_hz", str(settings.ocr_capture_hz))
    table.add_row("ocr_capture_artifacts_dir", str(settings.ocr_capture_artifacts_dir))
    table.add_row("mock_inputs_enabled", _format_bool(settings.mock_inputs_enabled))
    table.add_row("mock_mining_interval_ms", str(settings.mock_mining_interval_ms))
    table.add_row(
        "claim_expiration_maintenance_enabled",
        _format_bool(settings.claim_expiration_maintenance_enabled),
    )
    table.add_row(
        "claim_expiration_maintenance_interval_s",
        str(settings.claim_expiration_maintenance_interval_s),
    )
    table.add_row("finder_recording_modes", settings.finder_recording_modes or "[dim]<off>[/]")
    table.add_row("finder_debug_logging", _format_bool(settings.finder_debug_logging))
    table.add_row("finder_recording_dir", str(settings.finder_recording_dir))
    table.add_row("finder_recording_interval_s", str(settings.finder_recording_interval_s))
    table.add_row("finder_recording_max_samples", str(settings.finder_recording_max_samples))
    table.add_row(
        "finder_presence_check_enabled",
        _format_bool(settings.finder_presence_check_enabled),
    )
    table.add_row(
        "position_roi_snapshot_enabled",
        _format_bool(settings.position_roi_snapshot_enabled),
    )
    table.add_row("position_roi_snapshot_dir", str(settings.position_roi_snapshot_dir))
    table.add_row(
        "position_roi_snapshot_interval_s",
        str(settings.position_roi_snapshot_interval_s),
    )
    table.add_row(
        "position_roi_snapshot_max_samples",
        str(settings.position_roi_snapshot_max_samples),
    )
    table.add_row("ocr_profiling_enabled", _format_bool(settings.ocr_profiling_enabled))
    table.add_row("ocr_profiling_interval_s", str(settings.ocr_profiling_interval_s))
    return table


def _format_bool(value: bool) -> str:
    return "[green]yes[/]" if value else "[red]no[/]"


def _format_path(path: Path | None) -> str:
    return "[dim]<none>[/]" if path is None else str(path)


@app.command("config")
def show_config(
    mode: Annotated[
        InputMode,
        typer.Option(
            "--mode",
            "-m",
            case_sensitive=False,
            help="Preview config after applying input mode overrides.",
        ),
    ] = InputMode.ENV,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override ZML_DB_PATH.")] = None,
    chat_log_path: Annotated[
        Path | None,
        typer.Option("--chat-log", help="Override ZML_CHAT_LOG_PATH."),
    ] = None,
    ocr_profile_path: Annotated[
        Path | None,
        typer.Option("--ocr-profile", help="Override ZML_OCR_PROFILE_PATH."),
    ] = None,
    finder_debug: Annotated[
        bool,
        typer.Option("--finder-debug", help="Enable finder OCR debug logging."),
    ] = False,
    finder_recording: Annotated[
        str | None,
        typer.Option(
            "--finder-record",
            help="Finder crop recording modes: manual,interval,all.",
        ),
    ] = None,
    finder_recording_dir: Annotated[
        Path | None,
        typer.Option("--finder-record-dir", help="Override ZML_FINDER_RECORDING_DIR."),
    ] = None,
    finder_recording_interval_s: Annotated[
        float | None,
        typer.Option("--finder-record-interval-s", help="Interval recording cadence in seconds."),
    ] = None,
    finder_recording_max_samples: Annotated[
        int | None,
        typer.Option(
            "--finder-record-max-samples",
            help="Maximum finder crop samples per OCR worker session.",
        ),
    ] = None,
    finder_presence_check: Annotated[
        bool | None,
        typer.Option(
            "--finder-presence-check/--no-finder-presence-check",
            help="Skip finder OCR when a cheap visual check says the panel is not visible.",
        ),
    ] = None,
    position_roi_snapshots: Annotated[
        bool | None,
        typer.Option(
            "--position-roi-snapshots/--no-position-roi-snapshots",
            help="Write fixed compass/lon/lat OCR ROI snapshots.",
        ),
    ] = None,
    position_roi_snapshot_dir: Annotated[
        Path | None,
        typer.Option(
            "--position-roi-snapshot-dir",
            help="Override ZML_POSITION_ROI_SNAPSHOT_DIR.",
        ),
    ] = None,
    position_roi_snapshot_interval_s: Annotated[
        float | None,
        typer.Option(
            "--position-roi-snapshot-interval-s",
            help="Seconds between overwrites of position ROI snapshots.",
        ),
    ] = None,
    position_roi_snapshot_max_samples: Annotated[
        int | None,
        typer.Option(
            "--position-roi-snapshot-max-samples",
            help="Maximum position ROI snapshot batches per OCR worker session.",
        ),
    ] = None,
    ocr_profiling: Annotated[
        bool,
        typer.Option("--ocr-profiling", help="Log OCR profiling summaries."),
    ] = False,
    ocr_profiling_interval_s: Annotated[
        float | None,
        typer.Option("--ocr-profiling-interval-s", help="OCR profiling summary interval."),
    ] = None,
    log_level: Annotated[
        str | None, typer.Option("--log-level", help="Override ZML_LOG_LEVEL.")
    ] = None,
    mock_interval_ms: Annotated[
        int | None,
        typer.Option("--mock-interval-ms", help="Override mock mining interval in milliseconds."),
    ] = None,
) -> None:
    _apply_env_overrides(
        mode=mode,
        db_path=db_path,
        chat_log_path=chat_log_path,
        ocr_profile_path=ocr_profile_path,
        finder_debug=finder_debug,
        finder_recording=finder_recording,
        finder_recording_dir=finder_recording_dir,
        finder_recording_interval_s=finder_recording_interval_s,
        finder_recording_max_samples=finder_recording_max_samples,
        finder_presence_check=finder_presence_check,
        position_roi_snapshots=position_roi_snapshots,
        position_roi_snapshot_dir=position_roi_snapshot_dir,
        position_roi_snapshot_interval_s=position_roi_snapshot_interval_s,
        position_roi_snapshot_max_samples=position_roi_snapshot_max_samples,
        ocr_profiling=ocr_profiling,
        ocr_profiling_interval_s=ocr_profiling_interval_s,
        log_level=log_level,
        mock_interval_ms=mock_interval_ms,
    )
    console.print(_settings_table(Settings()))


@app.command()
def serve(
    mode: Annotated[
        InputMode,
        typer.Option(
            "--mode",
            "-m",
            case_sensitive=False,
            help="Input mode: env, live, mock, hybrid, or no-inputs.",
        ),
    ] = InputMode.ENV,
    db_path: Annotated[Path | None, typer.Option("--db", help="Override ZML_DB_PATH.")] = None,
    chat_log_path: Annotated[
        Path | None,
        typer.Option("--chat-log", help="Override ZML_CHAT_LOG_PATH."),
    ] = None,
    ocr_profile_path: Annotated[
        Path | None,
        typer.Option("--ocr-profile", help="Override ZML_OCR_PROFILE_PATH."),
    ] = None,
    finder_debug: Annotated[
        bool,
        typer.Option("--finder-debug", help="Enable finder OCR debug logging."),
    ] = False,
    finder_recording: Annotated[
        str | None,
        typer.Option(
            "--finder-record",
            help="Finder crop recording modes: manual,interval,all.",
        ),
    ] = None,
    finder_recording_dir: Annotated[
        Path | None,
        typer.Option("--finder-record-dir", help="Override ZML_FINDER_RECORDING_DIR."),
    ] = None,
    finder_recording_interval_s: Annotated[
        float | None,
        typer.Option("--finder-record-interval-s", help="Interval recording cadence in seconds."),
    ] = None,
    finder_recording_max_samples: Annotated[
        int | None,
        typer.Option(
            "--finder-record-max-samples",
            help="Maximum finder crop samples per OCR worker session.",
        ),
    ] = None,
    finder_presence_check: Annotated[
        bool | None,
        typer.Option(
            "--finder-presence-check/--no-finder-presence-check",
            help="Skip finder OCR when a cheap visual check says the panel is not visible.",
        ),
    ] = None,
    position_roi_snapshots: Annotated[
        bool | None,
        typer.Option(
            "--position-roi-snapshots/--no-position-roi-snapshots",
            help="Write fixed compass/lon/lat OCR ROI snapshots.",
        ),
    ] = None,
    position_roi_snapshot_dir: Annotated[
        Path | None,
        typer.Option(
            "--position-roi-snapshot-dir",
            help="Override ZML_POSITION_ROI_SNAPSHOT_DIR.",
        ),
    ] = None,
    position_roi_snapshot_interval_s: Annotated[
        float | None,
        typer.Option(
            "--position-roi-snapshot-interval-s",
            help="Seconds between overwrites of position ROI snapshots.",
        ),
    ] = None,
    position_roi_snapshot_max_samples: Annotated[
        int | None,
        typer.Option(
            "--position-roi-snapshot-max-samples",
            help="Maximum position ROI snapshot batches per OCR worker session.",
        ),
    ] = None,
    ocr_profiling: Annotated[
        bool,
        typer.Option("--ocr-profiling", help="Log OCR profiling summaries."),
    ] = False,
    ocr_profiling_interval_s: Annotated[
        float | None,
        typer.Option("--ocr-profiling-interval-s", help="OCR profiling summary interval."),
    ] = None,
    log_level: Annotated[
        str | None, typer.Option("--log-level", help="Override ZML_LOG_LEVEL.")
    ] = None,
    mock_interval_ms: Annotated[
        int | None,
        typer.Option("--mock-interval-ms", help="Override mock mining interval in milliseconds."),
    ] = None,
) -> None:
    _apply_env_overrides(
        mode=mode,
        db_path=db_path,
        chat_log_path=chat_log_path,
        ocr_profile_path=ocr_profile_path,
        finder_debug=finder_debug,
        finder_recording=finder_recording,
        finder_recording_dir=finder_recording_dir,
        finder_recording_interval_s=finder_recording_interval_s,
        finder_recording_max_samples=finder_recording_max_samples,
        finder_presence_check=finder_presence_check,
        position_roi_snapshots=position_roi_snapshots,
        position_roi_snapshot_dir=position_roi_snapshot_dir,
        position_roi_snapshot_interval_s=position_roi_snapshot_interval_s,
        position_roi_snapshot_max_samples=position_roi_snapshot_max_samples,
        ocr_profiling=ocr_profiling,
        ocr_profiling_interval_s=ocr_profiling_interval_s,
        log_level=log_level,
        mock_interval_ms=mock_interval_ms,
    )
    console.print(_settings_table(Settings()))

    from zml_backend.main import main

    main()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
