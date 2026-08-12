from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def optimizer_trace_identity_issues(
    traces: Sequence[Mapping[str, Any]],
    *,
    is_fake: bool,
) -> list[str]:
    """Validate ordered evaluation identity without assuming gap-free run dirs."""
    issues: list[str] = []
    prefix = "fake_" if is_fake else "real_"
    seen_run_ids: set[str] = set()
    previous_run_number = 0
    for expected_index, row in enumerate(traces, start=1):
        evaluation_index = row.get("evaluation_index")
        if (
            not isinstance(evaluation_index, int)
            or isinstance(evaluation_index, bool)
            or evaluation_index != expected_index
        ):
            issues.append(
                "trace evaluation_index sequence is invalid: "
                f"expected={expected_index}, actual={evaluation_index!r}"
            )

        run_id = row.get("run_id")
        if not isinstance(run_id, str) or not run_id.startswith(prefix):
            issues.append(
                f"trace run_id is not a numbered {prefix} identity: {run_id!r}"
            )
            continue
        suffix = run_id.removeprefix(prefix)
        if len(suffix) != 3 or not suffix.isdecimal():
            issues.append(
                f"trace run_id is not a numbered {prefix} identity: {run_id!r}"
            )
            continue
        run_number = int(suffix)
        if run_id in seen_run_ids:
            issues.append(f"trace has duplicate run_id: {run_id}")
        seen_run_ids.add(run_id)
        if run_number <= previous_run_number:
            issues.append(
                "trace run_id sequence is not strictly increasing: "
                f"previous={prefix}{previous_run_number:03d}, current={run_id}"
            )
        if run_number < expected_index:
            issues.append(
                "trace run_id number precedes its evaluation_index: "
                f"evaluation_index={expected_index}, run_id={run_id}"
            )
        previous_run_number = max(previous_run_number, run_number)
    return issues
