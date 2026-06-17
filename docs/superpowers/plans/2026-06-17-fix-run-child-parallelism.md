# Fix-Run Child Parallelism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded child-level parallelism to local and remote `fix_run` workflows using `Spectre Settings.parallel_jobs`.

**Architecture:** Keep the product CLI and Spectre/OCEAN adapters unchanged. Add small scheduler helpers inside `fix_run_flow.py` and `remote_fix_run_flow.py` that run child `testbench x corner` adapters with `ThreadPoolExecutor(max_workers=min(parallel_jobs, len(children)))`, then collect results on the main thread in deterministic child order.

**Tech Stack:** Python 3.11, `concurrent.futures.ThreadPoolExecutor`, existing Hermes workflow modules, pytest, ruff.

---

## File Structure

- Modify `src/hermes_workflow/fix_run_flow.py` for local child scheduling.
- Modify `src/hermes_workflow/remote_fix_run_flow.py` for remote child scheduling.
- Modify `tests/test_fix_run_flow.py` for local concurrency and failure tests.
- Modify `tests/test_remote_fix_run_flow.py` for remote concurrency and failure tests.
- Modify release-facing docs only after code tests pass:
  - `README.md`
  - `docs/USER_GUIDE_CN.md`
  - `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
  - `docs/AGENT_USER_QUICKSTART_CN.md`
  - `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
  - `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`
  - `skills/ic-opt/SKILL.md`

Do not edit `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1` in this plan. This is dev-package implementation work.

## Task 1: Add Local Fix-Run Child Parallelism Tests

**Files:**

- Modify: `tests/test_fix_run_flow.py`

- [ ] **Step 1: Add test imports**

Add these imports near the top of `tests/test_fix_run_flow.py`:

```python
import threading
import time
```

- [ ] **Step 2: Add local child directory helper**

Add this helper near the existing mock helpers:

```python
def _write_fix_run_child_dirs(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    testbench_id: str = "cg_nf",
    corner_ids: tuple[str, str, str] = ("tt", "ss", "ff"),
) -> None:
    for corner_id in corner_ids:
        child_dir = (
            project_dir
            / "runs"
            / "real"
            / run_id
            / "testbenches"
            / testbench_id
            / "corners"
            / corner_id
        )
        child_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Add spectre parallel_jobs helper for tests**

Add this helper near `_write_fix_run_child_dirs`:

```python
def _set_spectre_parallel_jobs(project_dir: Path, parallel_jobs: int) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    payload["spectre"]["parallel_jobs"] = parallel_jobs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 4: Add failing local concurrency test**

Add this test near the existing child-run adapter tests:

```python
def test_fix_run_uses_parallel_jobs_for_child_runs(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    _set_spectre_parallel_jobs(project_dir, 2)

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_fix_run_child_dirs(project_dir, run_id=run_id)
        return _mock_prepare_result(project_dir, run_id=run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active > 1
    assert report.points[0].testbench_corner_count == 3
```

- [ ] **Step 5: Add failing local serial regression test**

Add this test below the previous one:

```python
def test_fix_run_parallel_jobs_one_keeps_child_runs_serial(tmp_path: Path) -> None:
    from hermes_workflow.fix_run_flow import run_fix_run_project

    project_dir = _create_fix_run_project(tmp_path)
    _set_spectre_parallel_jobs(project_dir, 1)

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_fix_run_child_dirs(project_dir, run_id=run_id)
        return _mock_prepare_result(project_dir, run_id=run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    with (
        patch("hermes_workflow.fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.fix_run_flow.prepare_from_requirement") as mock_prep,
        patch("hermes_workflow.fix_run_flow.run_product_doctor") as mock_doctor,
        patch("hermes_workflow.fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.fix_run_flow.run_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_fix_run_project(project_dir, real=True, cadence_cshrc=None)

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active == 1
```

- [ ] **Step 6: Run local tests and verify they fail**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
```

Expected: the new parallel test fails because `max_active` stays `1`.

## Task 2: Implement Local Fix-Run Child Parallelism

**Files:**

- Modify: `src/hermes_workflow/fix_run_flow.py`
- Test: `tests/test_fix_run_flow.py`

- [ ] **Step 1: Add imports**

Add these imports near the top of `src/hermes_workflow/fix_run_flow.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any
```

- [ ] **Step 2: Add local child outcome model**

Add this after `REPORT_RELATIVE`:

```python
@dataclass(frozen=True)
class _ChildAdapterOutcome:
    testbench_id: str | None
    corner_id: str | None
    adapter_result: Any | None = None
    issue: ChildRunIssue | None = None
```

- [ ] **Step 3: Add parallel job resolver**

Add this helper before `run_fix_run_project()`:

```python
def _fix_run_parallel_jobs(project_dir: Path) -> int:
    bundle = assert_valid_project(project_dir)
    return max(1, int(bundle.spectre.spectre.parallel_jobs))
```

- [ ] **Step 4: Add local child adapter wrapper**

Add this helper before `run_fix_run_project()`:

```python
def _run_local_child_adapter(
    project_root: Path,
    *,
    run_id: str,
    child: dict[str, str | None],
    cadence_cshrc: Path | None,
) -> _ChildAdapterOutcome:
    tb_id = child["testbench_id"]
    corner_id = child["corner_id"]
    try:
        adapter_result = run_spectre_ocean_adapter(
            project_root,
            run_id=run_id,
            testbench_id=tb_id,
            corner_id=corner_id,
            cadence_cshrc=cadence_cshrc,
        )
    except Exception as exc:  # noqa: BLE001
        return _ChildAdapterOutcome(
            testbench_id=tb_id,
            corner_id=corner_id,
            issue=ChildRunIssue(
                testbench_id=tb_id,
                corner_id=corner_id,
                message=f"adapter failed: {exc}",
            ),
        )
    return _ChildAdapterOutcome(
        testbench_id=tb_id,
        corner_id=corner_id,
        adapter_result=adapter_result,
    )
```

- [ ] **Step 5: Add bounded local scheduler helper**

Add this helper below `_run_local_child_adapter()`:

```python
def _run_local_child_adapters(
    project_root: Path,
    *,
    run_id: str,
    children: list[dict[str, str | None]],
    cadence_cshrc: Path | None,
    parallel_jobs: int,
) -> list[_ChildAdapterOutcome]:
    if not children:
        return []
    max_workers = min(max(1, parallel_jobs), len(children))
    outcomes: list[_ChildAdapterOutcome | None] = [None] * len(children)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                _run_local_child_adapter,
                project_root,
                run_id=run_id,
                child=child,
                cadence_cshrc=cadence_cshrc,
            ): index
            for index, child in enumerate(children)
        }
        for future in as_completed(future_to_index):
            outcomes[future_to_index[future]] = future.result()
    return [outcome for outcome in outcomes if outcome is not None]
```

- [ ] **Step 6: Replace the serial child loop**

In `run_fix_run_project()`, replace the current `for child in children:` adapter
loop with:

```python
            parallel_jobs = _fix_run_parallel_jobs(project_root)
            child_outcomes = _run_local_child_adapters(
                project_root,
                run_id=run_id,
                children=children,
                cadence_cshrc=cadence_cshrc,
                parallel_jobs=parallel_jobs,
            )

            for outcome in child_outcomes:
                if outcome.issue is not None:
                    child_issues.append(outcome.issue)
                    continue

                adapter_result = outcome.adapter_result
                if adapter_result is None:
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=outcome.testbench_id,
                            corner_id=outcome.corner_id,
                            message="adapter produced no result",
                        )
                    )
                    continue

                if adapter_result.status != "succeeded":
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=outcome.testbench_id,
                            corner_id=outcome.corner_id,
                            message=f"adapter status: {adapter_result.status}",
                        )
                    )

                if adapter_result.metric_result_manifest_path is not None:
                    scalar_manifest_paths.append(
                        _relative_artifact_path(
                            project_root,
                            adapter_result.metric_result_manifest_path,
                        )
                    )
```

- [ ] **Step 7: Run local tests**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_fix_run_flow.py -q
```

Expected: all local fix-run tests pass.

- [ ] **Step 8: Commit local implementation**

Run:

```bash
rtk git add src/hermes_workflow/fix_run_flow.py tests/test_fix_run_flow.py
rtk git commit -m "feat: parallelize local fix-run child runs"
```

If the worktree contains unrelated pre-existing changes, do not commit them.
Stage only the two files listed above.

## Task 3: Add Remote Fix-Run Child Parallelism Tests

**Files:**

- Modify: `tests/test_remote_fix_run_flow.py`

- [ ] **Step 1: Add test imports**

Add these imports near the top of `tests/test_remote_fix_run_flow.py`:

```python
import threading
import time
```

- [ ] **Step 2: Add remote child directory helper**

Add this helper near the existing mock helpers:

```python
def _write_remote_fix_run_child_dirs(
    project_dir: Path,
    *,
    run_id: str = "real_001",
    testbench_id: str = "cg_nf",
    corner_ids: tuple[str, str, str] = ("tt", "ss", "ff"),
) -> None:
    for corner_id in corner_ids:
        child_dir = (
            project_dir
            / "runs"
            / "real"
            / run_id
            / "testbenches"
            / testbench_id
            / "corners"
            / corner_id
        )
        child_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Add remote spectre parallel_jobs helper**

Add:

```python
def _set_remote_spectre_parallel_jobs(project_dir: Path, parallel_jobs: int) -> None:
    spectre_path = project_dir / "config" / "spectre.yaml"
    payload = yaml.safe_load(spectre_path.read_text(encoding="utf-8"))
    payload["spectre"]["parallel_jobs"] = parallel_jobs
    spectre_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 4: Add failing remote concurrency test**

Add:

```python
def test_remote_fix_run_uses_parallel_jobs_for_child_runs(tmp_path: Path) -> None:
    from hermes_workflow.package import create_project_from_template
    from hermes_workflow.remote_fix_run_flow import run_remote_fix_run_project

    import yaml

    project_dir = tmp_path / "remote_fix_run_parallel"
    create_project_from_template(project_dir)
    (project_dir / "netlists" / "templates").mkdir(parents=True, exist_ok=True)
    (project_dir / "netlists" / "templates" / "template.scs").write_text(
        "simulator lang=spectre\nparameters FN={{FN}} WN={{WN}}\ntran tran stop=10n\n",
        encoding="utf-8",
    )
    (project_dir / "config" / "workflow.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": "1.0", "mode": "fix_run", "starting_run_id": "real_001"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "config" / "fixed_points.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "points": [
                    {
                        "candidate_id": "user_point_001",
                        "parameters": {"FN": "2", "WN": "0.3u"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _set_remote_spectre_parallel_jobs(project_dir, 2)

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_side_effect(*args, **kwargs):
        run_id = kwargs["run_id"]
        _write_remote_fix_run_child_dirs(project_dir, run_id=run_id)
        return MagicMock(run_id=run_id, run_dir=project_dir / "runs" / "real" / run_id)

    def adapter_side_effect(*args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return _mock_adapter_result(project_dir, run_id=kwargs["run_id"])

    ref = RemoteProjectRef("lab", PurePosixPath("/remote/project"))
    mock_runner = MagicMock()
    mock_runner.run.return_value = MagicMock(return_code=0)

    with (
        patch("hermes_workflow.remote_fix_run_flow.run_remote_doctor") as mock_doctor,
        patch("hermes_workflow.remote_fix_run_flow.prepare_remote_project_cache") as mock_prep,
        patch("hermes_workflow.remote_fix_run_flow.check_requirement") as mock_check,
        patch("hermes_workflow.remote_fix_run_flow.prepare_from_requirement") as mock_prep_req,
        patch("hermes_workflow.remote_fix_run_flow.prepare_explicit_candidate_real_run") as mock_prepare,
        patch("hermes_workflow.remote_fix_run_flow.run_remote_spectre_ocean_adapter") as mock_adapter,
    ):
        mock_doctor.return_value = MagicMock(status="pass", issues=[])
        mock_prep.return_value = _mock_preparation(project_dir)
        mock_check.return_value = _mock_intake(project_dir)
        mock_prep_req.return_value = MagicMock(status="pass", issues=[])
        mock_prepare.side_effect = prepare_side_effect
        mock_adapter.side_effect = adapter_side_effect

        report = run_remote_fix_run_project(
            ref,
            remote_cadence_cshrc=PurePosixPath("/remote/project/cadence_env.csh"),
            real=True,
            runner=mock_runner,
        )

    assert report.status == "pass"
    assert mock_adapter.call_count == 3
    assert max_active > 1
    assert report.points[0].testbench_corner_count == 3
```

- [ ] **Step 5: Run remote tests and verify they fail**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected: the new parallel test fails because `max_active` stays `1`.

## Task 4: Implement Remote Fix-Run Child Parallelism

**Files:**

- Modify: `src/hermes_workflow/remote_fix_run_flow.py`
- Test: `tests/test_remote_fix_run_flow.py`

- [ ] **Step 1: Add imports**

Add:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
```

Keep the existing `from typing import Any`.

- [ ] **Step 2: Add remote child outcome model**

Add after `REPORT_RELATIVE`:

```python
@dataclass(frozen=True)
class _RemoteChildAdapterOutcome:
    testbench_id: str | None
    corner_id: str | None
    adapter_result: Any | None = None
    issue: ChildRunIssue | None = None
```

- [ ] **Step 3: Add remote parallel job resolver**

Add before `run_remote_fix_run_project()`:

```python
def _fix_run_parallel_jobs(project_dir: Path) -> int:
    from hermes_workflow.validate import assert_valid_project

    bundle = assert_valid_project(project_dir)
    return max(1, int(bundle.spectre.spectre.parallel_jobs))
```

- [ ] **Step 4: Add remote child adapter wrapper**

Add:

```python
def _run_remote_child_adapter(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
    child: dict[str, str | None],
) -> _RemoteChildAdapterOutcome:
    tb_id = child["testbench_id"]
    corner_id = child["corner_id"]
    try:
        adapter_result = run_remote_spectre_ocean_adapter(
            project_dir,
            run_id=run_id,
            remote_ref=remote_ref,
            remote_cadence_cshrc=remote_cadence_cshrc,
            runner=runner,
            testbench_id=tb_id,
            corner_id=corner_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _RemoteChildAdapterOutcome(
            testbench_id=tb_id,
            corner_id=corner_id,
            issue=ChildRunIssue(
                testbench_id=tb_id,
                corner_id=corner_id,
                message=f"adapter failed: {exc}",
            ),
        )
    return _RemoteChildAdapterOutcome(
        testbench_id=tb_id,
        corner_id=corner_id,
        adapter_result=adapter_result,
    )
```

- [ ] **Step 5: Add remote bounded scheduler helper**

Add:

```python
def _run_remote_child_adapters(
    project_dir: Path,
    *,
    run_id: str,
    remote_ref: RemoteProjectRef,
    remote_cadence_cshrc: PurePosixPath,
    runner: Any,
    children: list[dict[str, str | None]],
    parallel_jobs: int,
) -> list[_RemoteChildAdapterOutcome]:
    if not children:
        return []
    max_workers = min(max(1, parallel_jobs), len(children))
    outcomes: list[_RemoteChildAdapterOutcome | None] = [None] * len(children)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                _run_remote_child_adapter,
                project_dir,
                run_id=run_id,
                remote_ref=remote_ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=runner,
                child=child,
            ): index
            for index, child in enumerate(children)
        }
        for future in as_completed(future_to_index):
            outcomes[future_to_index[future]] = future.result()
    return [outcome for outcome in outcomes if outcome is not None]
```

- [ ] **Step 6: Replace the remote serial child loop**

In `run_remote_fix_run_project()`, replace the current `for child in children:`
adapter loop with:

```python
            parallel_jobs = _fix_run_parallel_jobs(project_dir)
            child_outcomes = _run_remote_child_adapters(
                project_dir,
                run_id=run_id,
                remote_ref=remote_ref,
                remote_cadence_cshrc=remote_cadence_cshrc,
                runner=ssh,
                children=children,
                parallel_jobs=parallel_jobs,
            )

            for outcome in child_outcomes:
                if outcome.issue is not None:
                    child_issues.append(outcome.issue)
                    continue

                adapter_result = outcome.adapter_result
                if adapter_result is None:
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=outcome.testbench_id,
                            corner_id=outcome.corner_id,
                            message="adapter produced no result",
                        )
                    )
                    continue

                if adapter_result.status != "succeeded":
                    adapter_detail = (
                        "; ".join(adapter_result.issues)
                        if adapter_result.issues
                        else adapter_result.status
                    )
                    child_issues.append(
                        ChildRunIssue(
                            testbench_id=outcome.testbench_id,
                            corner_id=outcome.corner_id,
                            message=adapter_detail,
                        )
                    )

                if adapter_result.metric_result_manifest_path is not None:
                    scalar_manifest_paths.append(
                        _relative_artifact_path(
                            project_dir,
                            adapter_result.metric_result_manifest_path,
                        )
                    )
```

- [ ] **Step 7: Run remote tests**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_remote_fix_run_flow.py -q
```

Expected: all remote fix-run tests pass.

- [ ] **Step 8: Commit remote implementation**

Run:

```bash
rtk git add src/hermes_workflow/remote_fix_run_flow.py tests/test_remote_fix_run_flow.py
rtk git commit -m "feat: parallelize remote fix-run child runs"
```

If the worktree contains unrelated pre-existing changes, stage only the two
files listed above.

## Task 5: Add Failure Preservation Regression Tests

**Files:**

- Modify: `tests/test_fix_run_flow.py`
- Modify: `tests/test_remote_fix_run_flow.py`

- [ ] **Step 1: Add local child failure regression**

Add a test that uses three child dirs and an adapter side effect that returns:

- success for `tt`
- failed status with `issues=["sim failed"]` for `ss`
- success for `ff`

Assert:

```python
assert report.status == "fail"
assert report.points[0].testbench_corner_count == 3
assert any("failed" in issue.message or "sim failed" in issue.message for issue in report.points[0].child_issues)
```

- [ ] **Step 2: Add remote child failure regression**

Add the same scenario to `tests/test_remote_fix_run_flow.py`, using
`run_remote_spectre_ocean_adapter` side effects.

- [ ] **Step 3: Run both test files**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_remote_fix_run_flow.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit failure regression**

Run:

```bash
rtk git add tests/test_fix_run_flow.py tests/test_remote_fix_run_flow.py
rtk git commit -m "test: preserve fix-run child failures under parallelism"
```

If the previous commits were skipped due to a dirty worktree, skip this commit
too and report the files changed.

## Task 6: Update Dev Documentation

**Files:**

- Modify: `README.md`
- Modify: `docs/USER_GUIDE_CN.md`
- Modify: `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- Modify: `docs/AGENT_USER_QUICKSTART_CN.md`
- Modify: `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- Modify: `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- Modify: `skills/ic-opt/SKILL.md`

- [ ] **Step 1: Add the required wording**

In every listed document that describes fix-run or Spectre settings, add this
contract in the document's language:

```text
In fix-run mode, Spectre Settings.parallel_jobs controls how many
testbench/corner child runs for one fixed point may run concurrently.
Spectre Settings.threads_per_run remains the thread count for each Spectre
process. Fixed points are still processed serially in this version.
```

Do not add any CLI flag. Do not describe this as optimizer candidate
parallelism in the fix-run section.

- [ ] **Step 2: Run wording scan**

Run:

```bash
rtk rg -n "fix-run mode|fix_run|parallel_jobs|threads_per_run" README.md docs examples skills
```

Expected: fix-run docs mention child-run concurrency and do not advertise a new
CLI override.

- [ ] **Step 3: Commit docs**

Run:

```bash
rtk git add README.md docs/USER_GUIDE_CN.md docs/AGENT_OPTIMIZER_USAGE_MANUAL.md docs/AGENT_USER_QUICKSTART_CN.md docs/OPTIMIZER_PRODUCTION_QUICKSTART.md examples/spectre_maestro_project/OPT_REQUIREMENT_README.md skills/ic-opt/SKILL.md
rtk git commit -m "docs: explain fix-run child parallelism"
```

If the worktree contains unrelated pre-existing changes, stage only the listed
docs.

## Task 7: Final Verification

**Files:**

- No code changes unless verification finds a defect.

- [ ] **Step 1: Run focused tests**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_fix_run_flow.py tests/test_remote_fix_run_flow.py tests/test_product_cli.py tests/test_validate.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full tests**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run ruff**

Run:

```bash
rtk proxy /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests
```

Expected: `All checks passed!`

- [ ] **Step 4: Run whitespace check**

Run:

```bash
rtk git diff --check
```

Expected: no output.

- [ ] **Step 5: Report final status**

Report:

- changed files
- whether commits were made
- focused test output
- full test output
- ruff output
- diff-check output
- whether release sync is still pending

Do not edit or publish the release package unless the user explicitly asks for
release sync after dev verification.

## Self-Review Notes

- The plan implements the spec's minimum-change approach.
- No CLI flags are added.
- Local and remote flows are covered.
- Tests detect actual overlap with `max_active > 1`.
- Failure preservation is explicitly tested.
- Documentation is updated only after code passes.
