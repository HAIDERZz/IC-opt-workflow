from __future__ import annotations

from pathlib import Path


ALLOWED_TEMPLATE_CALLERS = {
    # Product/template behavior.
    "tests/test_package.py",
    # Not yet migrated. Shrink this list in follow-up waves.
    "tests/real_run_smoke_helpers.py",
    "tests/test_approvals.py",
    "tests/test_dry_run.py",
    "tests/test_fix_run_flow.py",
    "tests/test_metric_results.py",
    "tests/test_mock_optimizer.py",
    "tests/test_multi_testbench_aggregation.py",
    "tests/test_native_turbo.py",
    "tests/test_netlists.py",
    "tests/test_next_real_run.py",
    "tests/test_openbox_backend.py",
    "tests/test_optimizer_progress_state.py",
    "tests/test_optimizer_task_package.py",
    "tests/test_real_result_record.py",
    "tests/test_real_run.py",
    "tests/test_real_run_recovery.py",
    "tests/test_remote_fix_run_flow.py",
    "tests/test_remote_optimizer_flow.py",
    "tests/test_remote_spectre_ocean.py",
    "tests/test_result_handoff.py",
    "tests/test_run_retention.py",
    "tests/test_spectre_ocean_adapter.py",
}


def test_create_project_from_template_usage_is_explicitly_allowlisted() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in sorted((root / "tests").glob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "tests/test_template_coupling_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "create_project_from_template" in text and relative not in ALLOWED_TEMPLATE_CALLERS:
            offenders.append(relative)

    assert offenders == []
