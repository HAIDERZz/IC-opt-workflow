# Continuation Requirement Strategy Pass-Through Implementation Plan

> Current contract notice: this plan may mention obsolete first-run workload
> flags as negative tests. Current release product first runs read those values
> only from `opt_requirement.md`; only `ic-opt PROJECT --real --continue N`
> remains as a product CLI budget delta.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ic-opt PROJECT --real --continue N` and remote continuation pass
only the continuation delta from CLI while preserving optimizer strategy and
OpenBox advanced settings from `opt_requirement.md` / generated config.

**Architecture:** Keep the existing continuation entrypoints and closeout flow.
Remove hardcoded PRF/EIC/local-random strategy-detail arguments from product
local/remote continuation helpers so `run_openbox_real_optimization()` resolves
strategy through the existing requirement-backed resolver. Update tests that
encoded the old hardcoded behavior.

**Tech Stack:** Python 3.11, Typer, pytest, Pydantic configs, existing
`run_openbox_real_optimization`, `resolve_optimizer_strategy`, local
`continue_local_project`, remote `continue_remote_project`.

**Hard Rules:**

- Develop only in `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`.
- Do not edit or sync `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`.
- Do not reintroduce product CLI workload/resource/strategy override flags.
- Do not modify `opt_requirement.md` automatically.
- Do not change adapter routing or candidate/testbench/corner concurrency.
- Use TDD: write failing tests before implementation.

## Task 1: Local Continuation Passes No Strategy Overrides

**Files:**

- Modify: `tests/test_product_cli.py`
- Modify: `src/hermes_workflow/optimizer_continuation_flow.py`

**Step 1: Add a failing local helper test**

Add a test that monkeypatches
`hermes_workflow.optimizer_continuation_flow.run_openbox_real_optimization`,
calls `continue_local_project(...)`, and captures kwargs.

Expected assertions:

```python
assert captured["max_evals"] is None
assert captured["additional_evals"] == 20
assert captured["continue_from_existing"] is True
assert captured["batch_size"] is None
assert captured["parallel_jobs"] is None
assert captured["strategy"] is None
assert captured["surrogate_type"] is None
assert captured["acq_type"] is None
assert captured["acq_optimizer_type"] is None
assert captured["initial_trials"] is None
```

Use existing closeout monkeypatch patterns so the test does not run real
Spectre/OpenBox.

**Step 2: Run the new test and confirm RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_product_cli.py::<new_test_name> -q
```

Expected failure before the fix:

```text
assert captured["surrogate_type"] is None
E AssertionError: assert 'prf' is None
```

**Step 3: Implement the minimal local fix**

In `src/hermes_workflow/optimizer_continuation_flow.py`:

- Remove the imports of `CONTINUATION_SURROGATE_TYPE`,
  `CONTINUATION_ACQ_TYPE`, and `CONTINUATION_ACQ_OPTIMIZER_TYPE`.
- Change the `run_openbox_real_optimization(...)` call in `local_openbox()` to:

```python
strategy=None,
surrogate_type=None,
acq_type=None,
acq_optimizer_type=None,
initial_trials=None,
```

Keep:

```python
max_evals=None
additional_evals=additional_evals
continue_from_existing=True
batch_size=None
parallel_jobs=None
```

**Step 4: Run local continuation tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_openbox_backend.py -q
```

Expected: local continuation tests pass or expose old assertions to update in
Task 3.

- [ ] Task 1 complete

## Task 2: Remote Continuation Passes No Strategy Overrides

**Files:**

- Modify: `tests/test_remote_optimizer_flow.py`
- Modify: `src/hermes_workflow/remote_optimizer_flow.py`

**Step 1: Update the existing remote hardcoded-default test to RED**

Replace the current expectation in
`test_continue_remote_project_passes_openbox_strategy_defaults` with a new
contract name such as:

```python
def test_continue_remote_project_does_not_pass_strategy_detail_overrides(...):
    ...
    assert captured_kwargs["strategy"] is None
    assert captured_kwargs["surrogate_type"] is None
    assert captured_kwargs["acq_type"] is None
    assert captured_kwargs["acq_optimizer_type"] is None
    assert captured_kwargs["initial_trials"] is None
```

Keep assertions that continuation still passes:

```python
assert captured_kwargs["max_evals"] is None
assert captured_kwargs["additional_evals"] == 4
assert captured_kwargs["continue_from_existing"] is True
assert captured_kwargs["batch_size"] is None
assert captured_kwargs["parallel_jobs"] is None
```

**Step 2: Run the updated remote test and confirm RED**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py::<updated_test_name> -q
```

Expected failure before the fix:

```text
assert captured_kwargs["surrogate_type"] is None
E AssertionError: assert 'prf' is None
```

**Step 3: Implement the minimal remote fix**

In `src/hermes_workflow/remote_optimizer_flow.py`:

- Remove imports of `CONTINUATION_SURROGATE_TYPE`,
  `CONTINUATION_ACQ_TYPE`, and `CONTINUATION_ACQ_OPTIMIZER_TYPE` if they are no
  longer used.
- In `continue_remote_project.remote_openbox()`, pass:

```python
strategy=None,
surrogate_type=None,
acq_type=None,
acq_optimizer_type=None,
initial_trials=None,
```

Keep:

```python
max_evals=None
additional_evals=additional_evals
continue_from_existing=True
batch_size=batch_size
parallel_jobs=parallel_jobs
```

If `continue_remote_project()` still has optional `batch_size` and
`parallel_jobs` parameters only for tests/internal call compatibility, product
CLI must continue to pass `None`. Do not add product CLI flags.

**Step 4: Run remote continuation tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py -q
```

Expected: pass after updating the old hardcoded-default expectation.

- [ ] Task 2 complete

## Task 3: Backend Behavior Proves Requirement Strategy Is Used

**Files:**

- Modify: `tests/test_openbox_backend.py`

**Step 1: Add fake continuation test for `openbox_gp_eic`**

Create or reuse a real-approved fake project with existing optimizer history.
Set `config/optimizer.yaml` to:

```yaml
optimizer:
  algorithm: openbox
  strategy: openbox_gp_eic
  initialization: sobol
  max_evaluations: 10
  batch_size: 2
  random_seed: 20260528
  failure_penalty: 1000000.0
  deduplicate_candidates: true
```

Run continuation with:

```python
run_openbox_fake_optimization(
    project_dir,
    max_evals=None,
    additional_evals=2,
    continue_from_existing=True,
    batch_size=None,
    advisor_factory=lambda _space, _seed: FakeAdvisor(),
)
```

Assert report:

```python
assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
assert report["openbox"]["resolved_strategy"]["surrogate_type"] == "gp"
assert report["openbox"]["resolved_strategy"]["acq_type"] == "eic"
assert report["openbox"]["resolved_strategy"]["acq_optimizer_type"] == "random_scipy"
assert report["openbox"]["continuation"]["budget_source"] == "cli_continuation_delta"
```

**Step 2: Run the test and confirm it fails before Tasks 1/2 are fixed if routed
through the continuation helper**

Run:

```bash
./.venv/bin/python -m pytest tests/test_openbox_backend.py::<new_test_name> -q
```

If the direct backend already passes, add a second assertion through
`continue_local_project()` with the OpenBox call monkeypatched less deeply so the
helper path is exercised. The RED must prove the helper no longer injects
strategy details.

**Step 3: Add preservation test for nested `optimizer.openbox` settings**

Use `optimizer.strategy: openbox_gp_eic` plus:

```yaml
openbox:
  surrogate_type: prf
  acq_type: eic
  acq_optimizer_type: local_random
  initial_trials: 5
```

Assert continuation report preserves those exact values:

```python
assert report["openbox"]["resolved_strategy"] == {
    "surrogate_type": "prf",
    "acq_type": "eic",
    "acq_optimizer_type": "local_random",
    "initial_trials": 5,
}
```

**Step 4: Run backend tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_openbox_backend.py tests/test_optimizer_strategy.py -q
```

Expected: pass.

- [ ] Task 3 complete

## Task 4: CLI Contract Regression

**Files:**

- Modify: `tests/test_product_cli.py`
- Modify: `tests/test_product_cli_remote.py`

**Step 1: Keep existing fail-closed CLI tests**

Verify existing tests still assert:

```python
ic-opt PROJECT --continue 20
```

fails with `--continue requires --real`.

Verify:

```python
ic-opt PROJECT --real --continue 20 --strategy openbox_gp_eic
```

fails with `continuation uses requirement strategy`.

Repeat for remote:

```python
ic-opt --ssh-profile lab /remote/project --continue 20
ic-opt --ssh-profile lab /remote/project --real --continue 20 --strategy openbox_gp_eic
```

**Step 2: Add no-default continuation assertion if missing**

Ensure `ic-opt PROJECT --real` does not pass `additional_evals` anywhere and does
not route to continuation.

**Step 3: Run CLI tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_product_cli_remote.py -q
```

Expected: pass.

- [ ] Task 4 complete

## Task 5: Documentation Cleanup For Product Contract

**Files:**

- Modify: `README.md`
- Modify: `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- Modify: `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- Modify: `docs/USER_GUIDE_CN.md`
- Modify: `docs/TROUBLESHOOTING_CN.md`
- Modify: `skills/ic-opt/SKILL.md`
- Modify: `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`

**Step 1: Remove stale product examples**

Replace product examples that show:

```bash
ic-opt PROJECT --continue N
ic-opt ... --max-evals ...
ic-opt ... --batch-size ...
ic-opt ... --parallel-jobs ...
```

with requirement-driven examples:

```bash
ic-opt PROJECT --real
ic-opt PROJECT --real --continue N
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real --continue N
```

**Step 2: State the contract explicitly**

Add concise wording:

- Initial real run uses `opt_requirement.md` for workload and resources.
- Continuation CLI accepts only `--continue N`; it does not override
  requirement strategy, batch size, candidate parallelism, threads, Spectre
  settings, retention, timeout, testbench, or corner settings.
- `opt_requirement.md` is never auto-edited by continuation.

**Step 3: Keep skill files byte-identical**

Run:

```bash
cmp -s skills/ic-opt/SKILL.md src/hermes_workflow/agent_skills/ic-opt/SKILL.md
```

Expected: exit 0.

**Step 4: Run doc/skill tests**

Run:

```bash
./.venv/bin/python -m pytest tests/test_agent_skill.py -q
```

Expected: pass.

- [ ] Task 5 complete

## Task 6: Verification

**Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_product_cli.py \
  tests/test_product_cli_remote.py \
  tests/test_remote_optimizer_flow.py \
  tests/test_openbox_backend.py \
  tests/test_optimizer_strategy.py \
  tests/test_agent_skill.py \
  -q
```

Expected: pass.

**Step 2: Run broader optimizer regression tests**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/test_next_real_run.py \
  tests/test_real_run.py \
  tests/test_optimizer_progress_state.py \
  tests/test_optimizer_acceptance.py \
  tests/test_remote_optimizer_flow.py \
  -q
```

Expected: pass.

**Step 3: Run full package checks**

Run:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests
git diff --check -- . ':!vendor' ':!.serena'
```

Expected: all pass.

**Step 4: Confirm release package untouched**

Run:

```bash
find /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1 \
  -newer src/hermes_workflow/optimizer_continuation_flow.py \
  -type f | head -n 20
```

Expected: no output.

- [ ] Task 6 complete

## Task 7: Real Local Continuation Smoke

**Files:** no code edits.

**Step 1: Copy prior real project**

Use a previously completed development-package real local project, for example
the latest known 10-point, 3-corner validation project:

```bash
TS=$(date +%Y%m%d_%H%M%S)
DST=/tmp/ic_opt_continue_strategy_pass_${TS}
rsync -a /tmp/ic_opt_local10_3corner_b09_20260614_050335/ "$DST"/
sha256sum "$DST/opt_requirement.md"
```

**Step 2: Run continuation**

Run:

```bash
./.venv/bin/ic-opt "$DST" --real --continue 2
```

Expected: exit 0 and `continuation completed`.

**Step 3: Verify artifacts**

Check:

```bash
./.venv/bin/python - <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
report = json.loads((root / "reports/optimizer_run_report.json").read_text())
state = json.loads((root / "state/optimizer_state.json").read_text())
ledger = sum(1 for line in (root / "ledger/experiment_ledger.jsonl").read_text().splitlines() if line.strip())
evals = sum(1 for line in (root / report["evaluations"]).read_text().splitlines() if line.strip())
cont = report["openbox"]["continuation"]
print(report["status"], report["evaluation_count"], evals)
print(state["status"], state["current_evaluations"], state.get("recorded_observation_count"), ledger)
print(cont)
print(report["openbox"]["requested_strategy"])
print(report["openbox"]["resolved_strategy"])
PY
```

Expected:

- report status is `completed`;
- evaluation rows and state current increase by exactly `2`;
- state recorded count equals ledger rows;
- continuation fields show `cli_continuation_delta`;
- resolved strategy matches the copied project's requirement/config.

**Step 4: Verify requirement hash unchanged**

Run:

```bash
sha256sum "$DST/opt_requirement.md"
```

Expected: same hash as before continuation.

- [ ] Task 7 complete

## Task 8: Final Review Gate

**Step 1: Review diff**

Run:

```bash
git diff -- src/hermes_workflow/optimizer_continuation_flow.py \
  src/hermes_workflow/remote_optimizer_flow.py \
  tests/test_remote_optimizer_flow.py \
  tests/test_product_cli.py \
  tests/test_product_cli_remote.py \
  tests/test_openbox_backend.py \
  README.md docs/AGENT_OPTIMIZER_USAGE_MANUAL.md \
  docs/OPTIMIZER_PRODUCTION_QUICKSTART.md docs/USER_GUIDE_CN.md \
  docs/TROUBLESHOOTING_CN.md skills/ic-opt/SKILL.md \
  src/hermes_workflow/agent_skills/ic-opt/SKILL.md
```

Confirm:

- no product continuation strategy-detail constants remain;
- no product CLI workload/resource override flags were reintroduced;
- no automatic requirement rewrite was added;
- remote adapter routing is unchanged;
- tests assert requirement pass-through, not PRF/EIC hardcoding.

**Step 2: Prepare final report**

Report:

- files changed;
- RED/GREEN evidence;
- exact test commands and results;
- real local smoke result;
- whether remote real smoke was run;
- release package untouched status;
- any remaining risk.

- [ ] Task 8 complete
