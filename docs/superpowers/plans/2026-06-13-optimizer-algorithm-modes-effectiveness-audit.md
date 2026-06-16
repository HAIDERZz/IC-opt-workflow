# C-77 Optimizer Algorithm Modes + Effectiveness Audit Implementation Plan

## Post-C-76/C-77 Alignment Checkpoint 2026-06-13

Development must continue from `ic-auto-opt-workflow`. `ic-auto-opt-workflow-v0.1` is a release/package synchronization target after development-package verification.

After C-77 implementation, C-76 multi-corner execution/aggregation/reporting code from `ic-auto-opt-workflow-v0.1` was synchronized back into the development package. C-77 optimizer strategy presets and optimizer effectiveness audit were preserved. Fresh targeted verification in the development package passed for both the C-76 multi-corner suite and the C-77 optimizer strategy/audit suite; full pytest, `ruff check src tests`, development cadence check, and `git diff --check` also passed.

Remaining verification gap: no fresh live Cadence/Spectre/OCEAN multi-corner optimizer practice run has been executed after this alignment. Do not claim real multi-corner optimizer effectiveness until that development-package real route is run and inspected.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optimizer strategy presets and per-batch effectiveness audit to the existing OpenBox/TuRBO optimizer flow without rewriting candidate evaluation or real-tool adapters.

**Architecture:** Introduce a small strategy resolver that maps user-facing presets to existing OpenBox, native TuRBO, or random-baseline execution paths. Reuse current `openbox_backend.py` and `native_turbo.py` candidate evaluation loops, then record a stable batch-level audit in optimizer reports and insight markdown.

**Tech Stack:** Python 3.11, Pydantic v2 schemas, Typer CLI, existing OpenBox ask-and-tell path, existing native TuRBO runner, pytest, ruff.

---

## Source Design

Use this spec as authority:

```text
docs/superpowers/specs/2026-06-13-optimizer-algorithm-modes-effectiveness-audit-design.md
```

Use this algorithm background:

```text
docs/OPTIMIZER_ALGORITHM_MODES.md
```

## Hard Constraints

- Do not rewrite the optimizer framework.
- Do not delete or replace `src/hermes_workflow/native_turbo.py`.
- Do not change Spectre/OCEAN adapter semantics.
- Do not change OCEAN formulas or metric math.
- Do not parse PSF.
- Do not change multi-testbench or multi-corner `parallel_jobs` semantics.
- Do not create a Python virtualenv inside user project directories.
- Do not silently switch backend during continuation.
- Do not run real Virtuoso/Spectre/OCEAN for implementation tasks unless a
  later user explicitly approves a real acceptance drill.
- Keep `ic-auto-opt-workflow-v0.1` as a release sync target, not the
  implementation workspace for C-77.

## File Structure

Create:

- `src/hermes_workflow/optimizer_strategy.py`
  - Owns strategy enum, OpenBox/TuRBO advanced settings, preset resolution,
    compatibility validation, and resolved settings serialization.
- `src/hermes_workflow/optimizer_effectiveness.py`
  - Owns batch effectiveness audit data models and pure functions that compute
    audit rows from traces and strategy metadata.
- `tests/test_optimizer_strategy.py`
  - Unit tests for strategy parsing, default mapping, advanced overrides, and
    continuation compatibility.
- `tests/test_optimizer_effectiveness.py`
  - Unit tests for audit row computation from OpenBox and TuRBO traces.

Modify:

- `src/hermes_workflow/schemas.py`
- `src/hermes_workflow/requirement_intake.py`
- `src/hermes_workflow/openbox_backend.py`
- `src/hermes_workflow/native_turbo.py`
- `src/hermes_workflow/cli.py`
- `src/hermes_workflow/product_cli.py`
- `src/hermes_workflow/optimizer_flow.py`
- `src/hermes_workflow/remote_optimizer_flow.py`
- `src/hermes_workflow/optimizer_task_package.py`
- `src/hermes_workflow/optimizer_insights.py`
- `src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md`
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`

## Task 1: Strategy Schema And Resolver

**Files:**

- Create: `src/hermes_workflow/optimizer_strategy.py`
- Modify: `src/hermes_workflow/schemas.py`
- Test: `tests/test_optimizer_strategy.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write failing strategy resolver tests**

Add tests proving:

```python
def test_openbox_algorithm_defaults_to_openbox_auto() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=None,
            openbox=None,
            turbo=None,
            variable_count=4,
        )
    )
    assert resolved.requested_strategy.value == "openbox_auto"
    assert resolved.backend == "openbox"
    assert resolved.surrogate_type == "auto"
    assert resolved.acq_type == "auto"
    assert resolved.acq_optimizer_type == "auto"
    assert resolved.initial_trials == 8


def test_openbox_gp_eic_resolves_expected_openbox_settings() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=OptimizerStrategyName.OPENBOX_GP_EIC,
            openbox=None,
            turbo=None,
            variable_count=10,
        )
    )
    assert resolved.surrogate_type == "gp"
    assert resolved.acq_type == "eic"
    assert resolved.acq_optimizer_type == "random_scipy"
    assert resolved.initial_trials == 20


def test_openbox_prf_eic_resolves_expected_openbox_settings() -> None:
    resolved = resolve_optimizer_strategy(
        OptimizerStrategyRequest(
            algorithm=OptimizerAlgorithm.OPENBOX,
            strategy=OptimizerStrategyName.OPENBOX_PRF_EIC,
            openbox=None,
            turbo=None,
            variable_count=11,
        )
    )
    assert resolved.surrogate_type == "prf"
    assert resolved.acq_type == "eic"
    assert resolved.acq_optimizer_type == "local_random"
    assert resolved.initial_trials == 22


def test_openbox_eic_is_rejected_as_strategy_name() -> None:
    with pytest.raises(ValueError, match="eic is an acquisition function"):
        OptimizerStrategyName.from_user_value("openbox_eic")
```

- [ ] **Step 2: Run resolver tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_strategy.py -q
```

Expected: FAIL because `hermes_workflow.optimizer_strategy` does not exist.

- [ ] **Step 3: Implement strategy resolver**

Create `optimizer_strategy.py` with:

```python
class OptimizerStrategyName(StrEnum):
    OPENBOX_AUTO = "openbox_auto"
    OPENBOX_GP_EIC = "openbox_gp_eic"
    OPENBOX_PRF_EIC = "openbox_prf_eic"
    TURBO_TRUST_REGION = "turbo_trust_region"
    RANDOM_BASELINE = "random_baseline"
```

Implement dataclasses:

```python
@dataclass(frozen=True)
class OpenBoxAdvancedSettings:
    surrogate_type: str | None = None
    acq_type: str | None = None
    acq_optimizer_type: str | None = None
    initial_trials: int | Literal["auto"] | None = None

@dataclass(frozen=True)
class TurboAdvancedSettings:
    snap_to_step: bool = True
    duplicate_handling: str = "resample"

@dataclass(frozen=True)
class OptimizerStrategyRequest:
    algorithm: OptimizerAlgorithm
    strategy: OptimizerStrategyName | None
    openbox: OpenBoxAdvancedSettings | None
    turbo: TurboAdvancedSettings | None
    variable_count: int

@dataclass(frozen=True)
class ResolvedOptimizerStrategy:
    requested_strategy: OptimizerStrategyName
    backend: Literal["openbox", "native_turbo", "random_baseline"]
    surrogate_type: str | None = None
    acq_type: str | None = None
    acq_optimizer_type: str | None = None
    initial_trials: int | None = None
    snap_to_step: bool | None = None
    duplicate_handling: str | None = None
    model_based: bool = True
```

Implement `resolve_optimizer_strategy(request)` with the preset table from the
C-77 spec. `initial_trials` uses `max(2 * variable_count, 1)` when `auto`.

- [ ] **Step 4: Extend Pydantic schema**

Modify `schemas.py`:

```python
class OptimizerStrategy(StrEnum):
    OPENBOX_AUTO = "openbox_auto"
    OPENBOX_GP_EIC = "openbox_gp_eic"
    OPENBOX_PRF_EIC = "openbox_prf_eic"
    TURBO_TRUST_REGION = "turbo_trust_region"
    RANDOM_BASELINE = "random_baseline"


class OpenBoxOptimizerSettings(StrictModel):
    surrogate_type: Literal["auto", "gp", "prf", "gp_rbf", "sk_prf", "lightgbm"] | None = None
    acq_type: Literal["auto", "ei", "eic", "pi", "lcb"] | None = None
    acq_optimizer_type: Literal["auto", "random_scipy", "local_random"] | None = None
    initial_trials: StrictInt | Literal["auto"] | None = None


class TurboOptimizerSettings(StrictModel):
    snap_to_step: Literal[True] = True
    duplicate_handling: Literal["resample"] = "resample"
```

Add to `OptimizerSettings`:

```python
strategy: OptimizerStrategy | None = None
openbox: OpenBoxOptimizerSettings | None = None
turbo: TurboOptimizerSettings | None = None
```

Add model validation so OpenBox strategies require `algorithm=openbox`,
`turbo_trust_region` requires `algorithm=turbo`, and `random_baseline` requires
`algorithm=random`.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_strategy.py tests/test_schemas.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add src/hermes_workflow/optimizer_strategy.py src/hermes_workflow/schemas.py tests/test_optimizer_strategy.py tests/test_schemas.py
rtk git commit -m "feat: add optimizer strategy resolver"
```

## Task 2: Requirement Intake And Template Defaults

**Files:**

- Modify: `src/hermes_workflow/requirement_intake.py`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- Test: `tests/test_requirement_intake.py`

- [ ] **Step 1: Write failing requirement-intake test**

Add a test that writes `strategy: openbox_prf_eic` under optimizer settings in
`opt_requirement.md`, runs `prepare_from_requirement(project_dir)`, and asserts:

```python
optimizer = yaml.safe_load((project_dir / "config" / "optimizer.yaml").read_text())
assert optimizer["optimizer"]["algorithm"] == "openbox"
assert optimizer["optimizer"]["strategy"] == "openbox_prf_eic"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_requirement_intake.py::test_requirement_intake_preserves_optimizer_strategy -q
```

Expected: FAIL because strategy is not parsed or rendered.

- [ ] **Step 3: Parse strategy and advanced settings**

Extend optimizer key extraction in `requirement_intake.py` to include:

```python
"strategy"
"openbox"
"turbo"
```

Nested maps must be preserved as YAML mappings. Do not invent strategy in the
parser when the requirement omits it.

- [ ] **Step 4: Update templates**

In `opt_requirement.md`, make the default explicit:

```yaml
algorithm: openbox
strategy: openbox_auto
initialization: sobol
max_evaluations: 100
batch_size: 10
random_seed: 20260528
optimizer_cpu_threads: 4
failure_penalty: 1000000.0
deduplicate_candidates: true
```

In `OPT_REQUIREMENT_README.md`, list the five strategies and link to
`docs/OPTIMIZER_ALGORITHM_MODES.md`.

- [ ] **Step 5: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_requirement_intake.py tests/test_schemas.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk git add src/hermes_workflow/requirement_intake.py src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md tests/test_requirement_intake.py
rtk git commit -m "feat: parse optimizer strategy requirements"
```

## Task 3: OpenBox Strategy Wiring

**Files:**

- Modify: `src/hermes_workflow/openbox_backend.py`
- Modify: `src/hermes_workflow/cli.py`
- Test: `tests/test_openbox_backend.py`

- [ ] **Step 1: Write failing OpenBox preset test**

Add a test that calls:

```python
run_openbox_real_optimization(
    project_dir,
    max_evals=2,
    batch_size=2,
    parallel_jobs=1,
    advisor_factory=advisor_factory,
    strategy="openbox_gp_eic",
    adapter=fake_adapter,
)
```

Assert `optimizer_run_report.json` includes:

```python
assert report["openbox"]["requested_strategy"] == "openbox_gp_eic"
assert report["openbox"]["resolved_strategy"]["surrogate_type"] == "gp"
assert report["openbox"]["resolved_strategy"]["acq_type"] == "eic"
assert report["openbox"]["resolved_strategy"]["acq_optimizer_type"] == "random_scipy"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_openbox_backend.py::test_run_openbox_real_optimization_applies_strategy_preset -q
```

Expected: FAIL because `strategy` is not accepted.

- [ ] **Step 3: Add strategy parameters to OpenBox settings**

Add fields to `OpenBoxBatchRunSettings`:

```python
requested_strategy: str
resolved_strategy: dict[str, object]
```

Update `run_openbox_fake_optimization`, `run_openbox_real_optimization`, and
`_run_openbox_batches` to accept:

```python
strategy: str | None = None
initial_trials: int | None = None
```

Resolve strategy once after loading the contract and before `_create_advisor`.

- [ ] **Step 4: Pass resolved values into OpenBox Advisor**

Modify the existing `_create_advisor` helper to accept `initial_trials` and
pass:

```python
initial_trials=resolved_strategy.initial_trials
surrogate_type=resolved_strategy.surrogate_type
acq_type=resolved_strategy.acq_type
acq_optimizer_type=resolved_strategy.acq_optimizer_type
```

Capture runtime resolved settings with explicit fallbacks:

```python
runtime_surrogate_type = getattr(advisor, "surrogate_type", resolved_strategy.surrogate_type)
runtime_acq_type = getattr(advisor, "acq_type", resolved_strategy.acq_type)
runtime_acq_optimizer_type = getattr(
    advisor,
    "acq_optimizer_type",
    resolved_strategy.acq_optimizer_type,
)
```

Use `"unknown"` only when both the advisor and the resolved strategy lack a
field.

- [ ] **Step 5: Add CLI passthrough**

Add `--strategy` and `--initial-trials` to `run-openbox-real` and
`continue-openbox-real`. Existing `--surrogate-type`, `--acq-type`, and
`--acq-optimizer-type` remain advanced overrides.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_openbox_backend.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add src/hermes_workflow/openbox_backend.py src/hermes_workflow/cli.py tests/test_openbox_backend.py
rtk git commit -m "feat: wire OpenBox optimizer strategies"
```

## Task 4: Effectiveness Audit Core

**Files:**

- Create: `src/hermes_workflow/optimizer_effectiveness.py`
- Modify: `src/hermes_workflow/openbox_backend.py`
- Test: `tests/test_optimizer_effectiveness.py`
- Test: `tests/test_openbox_backend.py`

- [ ] **Step 1: Write failing audit tests**

Create `tests/test_optimizer_effectiveness.py` with a synthetic batch containing
one `feasible`, one `constraint_failed`, and one `metric_check_failed` trace.
Assert:

```python
assert audit.history_size_before == 0
assert audit.history_size_after == 3
assert audit.successful_observation_count == 2
assert audit.penalty_observation_count == 1
assert audit.feasible_count == 1
assert audit.best_objective_so_far == 1.0
assert audit.best_feasible_so_far == 2.0
```

- [ ] **Step 2: Run audit tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_effectiveness.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement audit models**

Create `optimizer_effectiveness.py` with:

```python
SUCCESSFUL_STATUSES = {"feasible", "constraint_failed"}

@dataclass(frozen=True)
class OptimizerBatchAuditInput:
    batch_id: str
    phase: str
    history_size_before: int
    traces: Sequence[Mapping[str, Any]]
    all_traces_so_far: Sequence[Mapping[str, Any]]
    replay_history_count: int = 0
    duplicate_replacements: int = 0
    resolved_surrogate_type: str | None = None
    resolved_acq_type: str | None = None
    resolved_acq_optimizer_type: str | None = None

@dataclass(frozen=True)
class OptimizerBatchAudit:
    batch_id: str
    phase: str
    history_size_before: int
    history_size_after: int
    suggestion_count: int
    evaluation_count: int
    successful_observation_count: int
    penalty_observation_count: int
    feasible_count: int
    best_objective_so_far: float | None
    best_feasible_so_far: float | None
    duplicate_replacements: int
    replay_history_count: int
    resolved_surrogate_type: str | None
    resolved_acq_type: str | None
    resolved_acq_optimizer_type: str | None

def build_batch_effectiveness_audit(
    payload: OptimizerBatchAuditInput,
) -> OptimizerBatchAudit:
    successful = [
        trace for trace in payload.traces
        if trace.get("status") in SUCCESSFUL_STATUSES
    ]
    feasible = [
        trace for trace in payload.all_traces_so_far
        if trace.get("status") == "feasible"
    ]
    finite = [
        trace for trace in payload.all_traces_so_far
        if isinstance(trace.get("objective"), int | float)
    ]
    return OptimizerBatchAudit(
        batch_id=payload.batch_id,
        phase=payload.phase,
        history_size_before=payload.history_size_before,
        history_size_after=payload.history_size_before + len(payload.traces),
        suggestion_count=len(payload.traces),
        evaluation_count=len(payload.traces),
        successful_observation_count=len(successful),
        penalty_observation_count=len(payload.traces) - len(successful),
        feasible_count=len(feasible),
        best_objective_so_far=min((float(trace["objective"]) for trace in finite), default=None),
        best_feasible_so_far=min((float(trace["objective"]) for trace in feasible if isinstance(trace.get("objective"), int | float)), default=None),
        duplicate_replacements=payload.duplicate_replacements,
        replay_history_count=payload.replay_history_count,
        resolved_surrogate_type=payload.resolved_surrogate_type,
        resolved_acq_type=payload.resolved_acq_type,
        resolved_acq_optimizer_type=payload.resolved_acq_optimizer_type,
    )
```

The function must compute successful observations, penalty observations,
feasible count, best objective so far, and best feasible objective so far.

- [ ] **Step 4: Capture OpenBox batch audit rows**

In `_run_openbox_batches`, create an `audit_rows` list. After each evaluated
batch, append a row with phase:

```python
"initialization" if history_size_before < initial_trials else "bo"
```

Continuation batches include `replay_history_count=len(model_replay_traces)`.

- [ ] **Step 5: Write audit artifact**

Write:

```text
reports/optimizer_effectiveness_audit.json
```

and reference it from `optimizer_run_report.json` as:

```json
"effectiveness_audit": "reports/optimizer_effectiveness_audit.json"
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_effectiveness.py tests/test_openbox_backend.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add src/hermes_workflow/optimizer_effectiveness.py src/hermes_workflow/openbox_backend.py tests/test_optimizer_effectiveness.py tests/test_openbox_backend.py
rtk git commit -m "feat: audit optimizer effectiveness by batch"
```

## Task 5: TuRBO And Random Baseline Modes

**Files:**

- Modify: `src/hermes_workflow/native_turbo.py`
- Modify: `src/hermes_workflow/optimizer_flow.py`
- Modify: `src/hermes_workflow/cli.py`
- Modify: `src/hermes_workflow/openbox_backend.py`
- Test: `tests/test_native_turbo.py`
- Test: `tests/test_optimizer_flow.py`
- Test: `tests/test_openbox_backend.py`

- [ ] **Step 1: Write failing TuRBO strategy flow test**

Add a test proving `strategy="turbo_trust_region"` in `optimize_project` routes
to `run_batch_native_turbo_optimization` and does not call OpenBox.

- [ ] **Step 2: Write failing random baseline test**

Add a test proving `strategy="random_baseline"` writes:

```python
assert report["openbox"]["requested_strategy"] == "random_baseline"
assert report["openbox"]["resolved_strategy"]["model_based"] is False
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_flow.py tests/test_openbox_backend.py -q
```

Expected: FAIL on the new tests.

- [ ] **Step 4: Route TuRBO through existing native runner**

In `optimizer_flow.py`, resolve strategy before optimizer execution. If backend
is `native_turbo`, call the existing batch native TuRBO runner. Do not modify
TuRBO candidate generation beyond strategy metadata and audit artifact writes.

- [ ] **Step 5: Implement random baseline through existing evaluator boundary**

Keep this minimal. Add a simple random-grid advisor for `random_baseline` that
uses existing quantization and duplicate handling, then reuses the same real
candidate evaluator and report writers. Mark audit phase as `random_baseline`.

- [ ] **Step 6: Attach TuRBO audit rows**

In `write_native_turbo_reports`, group traces by batch or selection phase and
write `reports/optimizer_effectiveness_audit.json`. Map phases:

```text
initialization -> initialization
turbo_trust_region -> turbo_trust_region
```

- [ ] **Step 7: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_native_turbo.py tests/test_optimizer_flow.py tests/test_openbox_backend.py tests/test_optimizer_effectiveness.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
rtk git add src/hermes_workflow/native_turbo.py src/hermes_workflow/optimizer_flow.py src/hermes_workflow/cli.py src/hermes_workflow/openbox_backend.py tests/test_native_turbo.py tests/test_optimizer_flow.py tests/test_openbox_backend.py
rtk git commit -m "feat: add turbo and random optimizer modes"
```

## Task 6: Product, Remote, And Task-Package Interfaces

**Files:**

- Modify: `src/hermes_workflow/product_cli.py`
- Modify: `src/hermes_workflow/remote_optimizer_flow.py`
- Modify: `src/hermes_workflow/optimizer_task_package.py`
- Test: `tests/test_product_cli.py`
- Test: `tests/test_remote_optimizer_flow.py`
- Test: `tests/test_optimizer_task_package.py`

- [ ] **Step 1: Write failing product CLI passthrough test**

Add a test invoking:

```bash
ic-opt PROJECT --real --strategy openbox_gp_eic
```

Assert `optimize_project(project_dir, real=True, strategy="openbox_gp_eic")`
is called.

- [ ] **Step 2: Write failing task-package test**

Add a test proving generated OpenBox task packages include:

```text
--strategy openbox_prf_eic
Requested optimizer strategy: openbox_prf_eic
Do not silently switch optimizer backend.
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_optimizer_task_package.py -q
```

Expected: FAIL on new tests.

- [ ] **Step 4: Add product CLI option**

Add:

```python
strategy: Annotated[str | None, typer.Option("--strategy", help="Optimizer strategy preset.")] = None
```

Pass it into `optimize_project(project_dir, real=real, strategy=strategy)`.

- [ ] **Step 5: Add remote flow strategy support**

Pass strategy into remote first-run and continuation OpenBox calls. Continuation
must fail closed if prior backend conflicts with the requested strategy.

- [ ] **Step 6: Add task-package strategy support**

Append `--strategy <strategy>` to generated commands when a strategy is set.
Task text must request `reports/optimizer_effectiveness_audit.json` as a
returned artifact.

- [ ] **Step 7: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_remote_optimizer_flow.py tests/test_optimizer_task_package.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
rtk git add src/hermes_workflow/product_cli.py src/hermes_workflow/remote_optimizer_flow.py src/hermes_workflow/optimizer_task_package.py tests/test_product_cli.py tests/test_remote_optimizer_flow.py tests/test_optimizer_task_package.py
rtk git commit -m "feat: expose optimizer strategy in product flow"
```

## Task 7: Reports, Insights, And Documentation

**Files:**

- Modify: `src/hermes_workflow/optimizer_insights.py`
- Modify: `src/hermes_workflow/optimizer_status.py`
- Modify: `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`
- Modify: `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`
- Modify: `src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- Test: `tests/test_optimizer_insights.py`
- Test: `tests/test_optimizer_status.py`

- [ ] **Step 1: Write failing insight report test**

Create a synthetic `reports/optimizer_effectiveness_audit.json` and assert
`generate_optimizer_insight_report(project_dir)` includes:

```text
Optimizer effectiveness audit
openbox_prf_eic
model replay: `40`
```

- [ ] **Step 2: Run report test and verify failure**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_insights.py::test_optimizer_insight_report_includes_effectiveness_audit -q
```

Expected: FAIL because insight report does not load the audit artifact.

- [ ] **Step 3: Load audit artifact in insights**

Add loader:

```python
EFFECTIVENESS_AUDIT_RELATIVE = Path("reports/optimizer_effectiveness_audit.json")

def _load_optimizer_effectiveness(project_dir: Path) -> dict[str, Any]:
    audit_path = project_dir / EFFECTIVENESS_AUDIT_RELATIVE
    if not audit_path.exists():
        return {"status": "not_available", "reason": "audit artifact missing"}
    try:
        payload = json.loads(audit_path.read_text())
    except json.JSONDecodeError as exc:
        return {"status": "not_available", "reason": f"invalid audit JSON: {exc}"}
    if not isinstance(payload, dict):
        return {"status": "not_available", "reason": "audit artifact is not an object"}
    return payload
```

Return a `not_available` object with a concrete reason when missing or
unreadable, for example
`{"status": "not_available", "reason": "audit artifact missing"}`.

- [ ] **Step 4: Add markdown section**

Render:

```text
## Optimizer effectiveness audit

- Requested strategy: `<strategy>`
- Resolved OpenBox: surrogate `<surrogate>`, acquisition `<acq>`, acquisition optimizer `<acq_optimizer>`
- Continuation model replay: `<count>`
- Latest phase: `<phase>`
- Latest history size: `<history_size_after>`
- Latest successful observations: `<successful_observation_count>`
- Latest feasible count: `<feasible_count>`
```

- [ ] **Step 5: Update user docs**

Update docs to explain:

- `openbox_auto` default;
- when to choose GP + EIC;
- when to choose PRF + EIC;
- when TuRBO is reasonable despite stepped variables;
- what the audit means;
- CPU limits affect runtime, not algorithm correctness.

- [ ] **Step 6: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_optimizer_insights.py tests/test_optimizer_status.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
rtk git add src/hermes_workflow/optimizer_insights.py src/hermes_workflow/optimizer_status.py docs/AGENT_OPTIMIZER_USAGE_MANUAL.md docs/OPTIMIZER_PRODUCTION_QUICKSTART.md src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md tests/test_optimizer_insights.py tests/test_optimizer_status.py
rtk git commit -m "docs: explain optimizer strategy audit"
```

## Task 8: Final Verification And State Sync

**Files:**

- Modify: `docs/CURRENT_TASK_STATE.json`
- Modify: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Modify if due: `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`

- [ ] **Step 1: Run targeted optimizer suite**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest \
  tests/test_optimizer_strategy.py \
  tests/test_optimizer_effectiveness.py \
  tests/test_openbox_backend.py \
  tests/test_native_turbo.py \
  tests/test_optimizer_flow.py \
  tests/test_remote_optimizer_flow.py \
  tests/test_optimizer_task_package.py \
  tests/test_optimizer_insights.py \
  tests/test_product_cli.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run schema and requirement tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_schemas.py tests/test_requirement_intake.py -q
```

Expected: PASS.

- [ ] **Step 3: Run ruff**

Run:

```bash
rtk proxy ./.venv/bin/python -m ruff check src tests
```

Expected: PASS.

- [ ] **Step 4: Run cadence and whitespace checks**

Run:

```bash
rtk proxy ./.venv/bin/python tools/check_development_cadence.py
rtk git diff --check
```

Expected: PASS.

- [ ] **Step 5: Update project state**

Update `docs/CURRENT_TASK_STATE.json` and
`docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` to record C-77 implementation
status, verification evidence, and next action.

- [ ] **Step 6: Final review gate**

Required review questions:

- Does C-77 reuse existing OpenBox and TuRBO flows instead of rewriting them?
- Are real-tool adapter semantics unchanged?
- Is continuation backend switching blocked?
- Does the audit distinguish initialization, BO, TuRBO trust region, and random
  baseline?
- Do reports show both requested strategy and resolved settings?

- [ ] **Step 7: Final commit**

```bash
rtk git add docs/CURRENT_TASK_STATE.json docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md
rtk git commit -m "docs: record c77 optimizer strategy completion"
```

## Self-Review

- Spec coverage: The plan covers strategy schema, presets, advanced overrides,
  OpenBox wiring, TuRBO routing, random baseline, product/remote/task-package
  interfaces, audit artifacts, insight reports, and docs.
- Placeholder scan: No implementation step depends on undefined future work.
- Type consistency: Strategy names, report keys, and artifact paths match the
  C-77 design spec.

## Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-06-13-optimizer-algorithm-modes-effectiveness-audit.md`.

Two execution options:

1. Subagent-Driven (recommended): dispatch a fresh subagent per task and review
   between tasks.
2. Inline Execution: execute tasks in this session using executing-plans with
   checkpoints.

Choose one before implementation starts.
