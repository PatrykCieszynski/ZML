from __future__ import annotations

from zml_ocr_worker.calibration.recovery import CompassRecoveryConfig, CompassRecoveryPolicy


def test_recovery_ignores_single_bad_frames_and_then_shifts_coordinate_layout() -> None:
    policy = CompassRecoveryPolicy(
        layout_count=3,
        config=CompassRecoveryConfig(consecutive_failures_before_adjust=3),
    )

    assert policy.observe(read_healthy=False).action == "keep"
    assert policy.observe(read_healthy=False).action == "keep"
    decision = policy.observe(read_healthy=False)

    assert decision.action == "use_layout"
    assert decision.layout_index == 1


def test_successful_unchanged_read_resets_failure_streak() -> None:
    policy = CompassRecoveryPolicy(
        layout_count=3,
        config=CompassRecoveryConfig(consecutive_failures_before_adjust=3),
    )

    policy.observe(read_healthy=False)
    policy.observe(read_healthy=False)
    decision = policy.observe(read_healthy=True)

    assert decision.action == "keep"
    assert policy.consecutive_failures == 0
    assert policy.layout_index == 0


def test_recovery_relocates_compass_after_all_line_layouts_fail() -> None:
    policy = CompassRecoveryPolicy(
        layout_count=2,
        config=CompassRecoveryConfig(consecutive_failures_before_adjust=2),
    )

    policy.observe(read_healthy=False)
    shifted = policy.observe(read_healthy=False)
    assert shifted.action == "use_layout"
    assert shifted.layout_index == 1

    policy.observe(read_healthy=False)
    relocated = policy.observe(read_healthy=False)
    assert relocated.action == "relocate_compass"
    assert relocated.layout_index == 0


def test_relocation_reset_returns_to_nominal_layout() -> None:
    policy = CompassRecoveryPolicy(
        layout_count=2,
        config=CompassRecoveryConfig(consecutive_failures_before_adjust=1),
    )
    policy.observe(read_healthy=False)
    assert policy.layout_index == 1

    policy.reset_after_relocation()

    assert policy.layout_index == 0
    assert policy.consecutive_failures == 0
