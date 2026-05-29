# Plan B: Mock Optimization Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a deterministic mock optimization loop that reads the same validated YAML configs Hermes already owns, generates quantized candidate parameter sets, computes mock metrics, evaluates constraints and objective, and writes standardized state files — without requiring Cadence, Virtuoso, Spectre, or TuRBO.

**Architecture:** The mock optimizer is a library module (`hermes_workflow.mock_optimizer`) callable from a new CLI command (`hermes-workflow mock-run`). It reuses the existing `ContractBundle` from `validate.py` for config loading and the AST-based expression evaluator for objective computation. Candidate generation uses numpy-based Sobol, Latin hypercube, and random samplers with deduplication. It never calls Spectre, never imports `virtuoso_bridge`, and never performs real simulation.

**Tech Stack:** Python 3.11+, `pydantic>=2`, `PyYAML`, `typer`, `numpy>=1.24`, `pytest`, `ruff`. New dependency: `numpy>=1.24` (required for quantized candidate generation).

**Prerequisite:** Plan A (Hermes File Contract MVP) Tasks 1-9 are complete and locked. Do not modify Plan A modules unless a Plan B task explicitly requires a minor extension.

---

## Confirmed Scope

### Included

- New Pydantic schemas for optimizer state artifacts: `OptimizerState`, `BestCandidate`, `LedgerRow`.
- Quantized candidate generation engine: Sobol, Latin hypercube, and random samplers producing integer and continuous_step parameter sets.
- Mock metric computation: deterministic pseudo-metrics derived from variable values, mapping back to declared metric names.
- Objective expression evaluation: reuse the validated AST from `validate.py` to compute scalar objectives from candidate metrics.
- Constraint evaluation: compare computed metric values against declared constraint thresholds.
- JSONL ledger writing: one row per candidate evaluation.
- Optimizer state persistence: `optimizer_state.json`, `best_candidate.json`, `health_check.json`.
- CLI command `hermes-workflow mock-run <project_dir>` with `--max-evaluations` override.
- Unit tests and integration tests for all of the above.

### Excluded

- Real Spectre execution or `virtuoso_bridge` integration.
- TuRBO algorithm implementation.
- Netlist templating (`input.scs` preparation).
- Claude CLI invocation.
- `USER_TASK.md` parsing.
- Final optimization report generation.
- Project-local runner template files (`render_netlist.py`, `dry_run.py`, `run_candidate.py`).

---

## Module Boundaries

`mock_optimizer.py` owns candidate generation, metric computation, constraint/objective evaluation, deduplication, state persistence, and the top-level `run_mock_optimization()` orchestration. It depends on `schemas.py` for config types and `validate.py` for `ContractBundle` loading and objective AST evaluation.

`cli.py` gains one new command: `mock-run`. Business logic stays in `mock_optimizer.py`.

`schemas.py` gains new state artifact models: `OptimizerState`, `BestCandidate`, `LedgerRow`.

---

## Proposed File Changes

```text
Modified:
  pyproject.toml                                         # add numpy>=1.24 dependency
  src/hermes_workflow/schemas.py                         # add OptimizerState, BestCandidate, LedgerRow models
  src/hermes_workflow/cli.py                             # add mock-run command
  src/hermes_workflow/validate.py                        # extract evaluate_objective_expression() as public helper

New:
  src/hermes_workflow/mock_optimizer.py                  # core mock optimizer logic
  tests/test_mock_optimizer.py                           # unit tests for mock optimizer
  tests/mock_optimization_helpers.py                     # shared test helpers for mock optimization
```

---

## New Pydantic Models

### `LedgerRow`

```python
class LedgerRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str          # e.g. "cand_001"
    parameters: dict[str, str] # e.g. {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"}
    metrics: dict[str, float]  # e.g. {"rise": 42.0, "fall": 43.0, "DC": 120.0}
    constraints_passed: bool
    objective: float
    batch_id: int
    simulation_status: str    # "mock_pass" | "mock_constraint_fail" | "mock_error"
    timestamp_utc: str        # ISO 8601
```

### `BestCandidate`

```python
class BestCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    parameters: dict[str, str]
    metrics: dict[str, float]
    constraints_passed: bool
    objective: float
    batch_id: int
    timestamp_utc: str
```

### `OptimizerState`

```python
class OptimizerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    project_name: str
    algorithm: str
    initialization: str
    current_evaluations: int
    max_evaluations: int
    batch_size: int
    random_seed: int
    best_candidate_id: str | None
    status: str  # "running" | "completed" | "stopped"
    started_at_utc: str
    updated_at_utc: str
```

---

## Mock Metric Design

The mock optimizer computes deterministic pseudo-metrics from parameter values. The formula for each metric is derived from the variable names and their numeric values:

For the `bridge_test_inv` fixture with variables `FN`, `WN`, `FP`, `WP` and metrics `rise`, `fall`, `DC`:

- `rise = 30.0 + 5.0 * FN + 2.0 * WN_numeric - 1.0 * FP - 0.5 * WP_numeric`
- `fall = 25.0 + 4.0 * FN + 1.5 * WN_numeric + 2.0 * FP - 0.3 * WP_numeric`
- `DC = 200.0 - 10.0 * FN - 15.0 * WN_numeric - 8.0 * FP - 20.0 * WP_numeric`

Where `WN_numeric` and `WP_numeric` are the numeric part of the continuous_step values (e.g., `"1.0 um"` → `1.0`).

For general projects, the mock metric formulas use a seeded pseudo-random function of the parameter values, so outputs are reproducible given the same seed. The implementation uses `hashlib.sha256(f"{metric_name}:{sorted_params}").hexdigest()` mapped to a float in a sensible range, then scaled by metric config hints if available.

**Important:** The mock optimizer does NOT interpret `maestro_formula`. It computes deterministic placeholder values. This is a deliberate MVP choice—real metric computation requires Spectre results and belongs in a later plan.

---

## Candidate Generation Design

### Integer Variables

For `kind: integer` with lower=L, upper=U, step=S:
- Legal values: `L, L+S, L+2S, ..., U`
- The validator already requires `(U - L) % S == 0`

### Continuous Step Variables

For `kind: continuous_step` with lower=L, upper=U, step=S (all with optional unit suffix):
- Legal values: `L, L+S, L+2S, ..., L+kS` where `L+kS <= U`
- Values preserve unit suffix in output

### Initialization Strategies

- **sobol**: Use `numpy`-based scrambled Sobol sequence (via `scipy.stats.qmc.Sobol`). Fallback to random if scipy is unavailable.
- **latin_hypercube**: Use `numpy`-based Latin hypercube (via `scipy.stats.qmc.LatinHypercube`). Fallback to stratified random if scipy is unavailable.
- **random**: Use seeded `numpy.random.default_rng(seed)` uniform sampling, then snap to grid.

All strategies produce candidates in the quantized grid, then deduplicate.

### Deduplication

As required by the MVP contract, `deduplicate_candidates: true` is enforced. After generating a batch, remove any candidate whose parameter dict matches a previously seen combination. Append new unique candidates until the batch reaches `batch_size` or `max_evaluations` is reached.

---

## Constraint and Objective Evaluation

### Constraint Evaluation

For each constraint `metric <op> value`:
1. Look up the computed mock metric value.
2. Parse the constraint value string to extract numeric and unit components.
3. Compare using the declared operator (`lt`, `le`, `gt`, `ge`).
4. A candidate passes if ALL constraints are satisfied.

### Objective Evaluation

1. Build a name→float mapping from computed metrics.
2. Parse the validated `objective.expression` via `ast.parse(mode="eval")`.
3. Evaluate the AST, allowing only `Name` nodes referencing declared metrics, `Constant` numeric nodes, and arithmetic operators (`+`, `-`, `*`, `/`, `**`, `%`, unary `+`/`-`).
4. For `direction: maximize`, negate the result (stored as negative in the ledger for minimization conventions).

This reuses the validated AST node types from `validate.py`.

---

## State File Formats

### `ledger/experiment_ledger.jsonl`

One JSON object per line, each a `LedgerRow`:

```jsonl
{"candidate_id":"cand_001","parameters":{"FN":"4","WN":"1.0 um","FP":"4","WP":"1.0 um"},"metrics":{"rise":52.0,"fall":42.5,"DC":120.0},"constraints_passed":true,"objective":11340.0,"batch_id":1,"simulation_status":"mock_pass","timestamp_utc":"2026-05-29T12:00:00Z"}
```

### `state/optimizer_state.json`

```json
{
  "schema_version": "1.0",
  "project_name": "bridge_test_inv",
  "algorithm": "turbo",
  "initialization": "sobol",
  "current_evaluations": 6,
  "max_evaluations": 100,
  "batch_size": 10,
  "random_seed": 20260528,
  "best_candidate_id": "cand_001",
  "status": "completed",
  "started_at_utc": "2026-05-29T12:00:00Z",
  "updated_at_utc": "2026-05-29T12:00:01Z"
}
```

### `state/best_candidate.json`

```json
{
  "candidate_id": "cand_001",
  "parameters": {"FN": "4", "WN": "1.0 um", "FP": "4", "WP": "1.0 um"},
  "metrics": {"rise": 52.0, "fall": 42.5, "DC": 120.0},
  "constraints_passed": true,
  "objective": 11340.0,
  "batch_id": 1,
  "timestamp_utc": "2026-05-29T12:00:00Z"
}
```

### `state/health_check.json`

Updated after each evaluation:

```json
{
  "schema_version": "1.0",
  "status": "healthy",
  "real_run_started": false,
  "current_evaluations": 6,
  "best_candidate_path": "state/best_candidate.json",
  "last_batch_id": 1,
  "issues": []
}
```

---

## Plan B Task Breakdown

### Task B1: Add numpy Dependency and Ledger/State Schemas

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/hermes_workflow/schemas.py`
- Create: `tests/test_mock_optimizer.py` (initial empty / import test)

**Steps:**

- [ ] **Step 1:** Add `numpy>=1.24` to `pyproject.toml` dependencies.

- [ ] **Step 2:** Add `LedgerRow`, `BestCandidate`, and `OptimizerState` Pydantic models to `schemas.py`. These models use `extra="forbid"`, strict types, and match the JSON schema contracts defined above.

- [ ] **Step 3:** Write failing schema tests for `LedgerRow`, `BestCandidate`, `OptimizerState`. Test that valid payloads parse and that extra fields are rejected.

- [ ] **Step 4:** Run schema tests to verify they pass.

- [ ] **Step 5:** Commit.

### Task B2: Extract Public Objective Evaluator from validate.py

**Files:**
- Modify: `src/hermes_workflow/validate.py`

**Steps:**

- [ ] **Step 1:** Extract a public function `evaluate_objective(expression: str, metrics: dict[str, float]) -> float` from the private AST validation in `validate.py`. The function parses the expression AST, substitutes metric name→float values, evaluates arithmetic, and returns the scalar result. It raises `ValueError` for unknown names, non-numeric constants, or unsupported nodes — reusing the same whitelist as `_is_allowed_objective_node`.

- [ ] **Step 2:** Write a failing test: `evaluate_objective("(rise + fall) * DC", {"rise": 52.0, "fall": 43.0, "DC": 120.0})` should return `(52.0 + 43.0) * 120.0 = 11400.0`.

- [ ] **Step 3:** Write additional tests for: unknown metric name raises ValueError, function calls raise ValueError, `direction: maximize` negation is handled at the call site (not in `evaluate_objective` itself).

- [ ] **Step 4:** Implement `evaluate_objective`.

- [ ] **Step 5:** Run tests to verify they pass.

- [ ] **Step 6:** Commit.

### Task B3: Quantized Candidate Generator

**Files:**
- Create: `src/hermes_workflow/mock_optimizer.py`
- Create: `tests/test_mock_optimizer.py` (expand with candidate generation tests)

**Steps:**

- [ ] **Step 1:** Write failing tests for:
  - `generate_integer_grid(lower=2, upper=12, step=1)` returns `[2, 3, 4, ..., 12]`.
  - `generate_continuous_grid(lower="0.3 um", upper="3 um", step="0.2 um")` returns `["0.3 um", "0.5 um", ..., "2.9 um"]`.
  - `generate_candidates(bundle, n_candidates=6, seed=20260528)` returns a list of `dict[str, str]` parameter sets using Sobol initialization.
  - `generate_candidates` with `initialization=random` returns different candidates from the same seed each call (in the epoch sense — within one call they are deterministic for that seed). Actually: same seed always produces same candidates for a given initialization method.
  - Deduplication: generating more candidates than the grid allows produces only unique combinations.

- [ ] **Step 2:** Implement `generate_integer_grid`, `generate_continuous_grid`, `generate_candidates`, and deduplication in `mock_optimizer.py`.

- [ ] **Step 3:** Run tests to verify they pass.

- [ ] **Step 4:** Commit.

### Task B4: Mock Metric Computation

**Files:**
- Modify: `src/hermes_workflow/mock_optimizer.py`
- Modify: `tests/test_mock_optimizer.py`

**Steps:**

- [ ] **Step 1:** Write failing tests for:
  - `compute_mock_metrics(variables_config, metrics_config, parameters)` returns a `dict[str, float]` mapping metric names to deterministic mock values.
  - For the `bridge_test_inv` fixture, given `FN=4, WN=1.0um, FP=4, WP=1.0um`, the metric values are deterministic and reproducible.
  - Different parameter sets produce different metric values.
  - The function works for any valid `MetricsConfig` with declared metrics, not just `bridge_test_inv`.

- [ ] **Step 2:** Implement `compute_mock_metrics` using a seeded deterministic formula: for each metric, compute `hashlib.sha256(f"{metric_name}:{sorted_param_str}".encode()).hexdigest()`, convert to float in [0,1), then scale into a reasonable range based on the metric unit and variable count.

- [ ] **Step 3:** Implement constraint evaluation: `evaluate_constraints(metrics_config, computed_metrics) -> bool`.

- [ ] **Step 4:** Run tests to verify they pass.

- [ ] **Step 5:** Commit.

### Task B5: Ledger and State Persistence

**Files:**
- Modify: `src/hermes_workflow/mock_optimizer.py`
- Modify: `tests/test_mock_optimizer.py`

**Steps:**

- [ ] **Step 1:** Write failing tests for:
  - `write_ledger_row(project_dir, row)` appends a JSONL line to `ledger/experiment_ledger.jsonl`.
  - `write_optimizer_state(project_dir, state)` writes `state/optimizer_state.json`.
  - `write_best_candidate(project_dir, candidate)` writes `state/best_candidate.json`.
  - `write_health_check(project_dir, current_evaluations, max_evaluations, best_candidate_id, status)` writes `state/health_check.json`.

- [ ] **Step 2:** Implement the four write functions in `mock_optimizer.py`, using the `LedgerRow`, `OptimizerState`, `BestCandidate` schemas from `schemas.py`.

- [ ] **Step 3:** Run tests to verify they pass.

- [ ] **Step 4:** Commit.

### Task B6: Top-Level Orchestration and CLI Command

**Files:**
- Modify: `src/hermes_workflow/mock_optimizer.py`
- Modify: `src/hermes_workflow/cli.py`
- Modify: `tests/test_mock_optimizer.py`
- Modify: `tests/test_cli.py`

**Steps:**

- [ ] **Step 1:** Write failing integration test:
  ```
  Given a project dir from `create_project_from_template`,
  `run_mock_optimization(project_dir, max_evaluations=6)`
  produces:
  - ledger/experiment_ledger.jsonl with 6 rows
  - state/optimizer_state.json with status "completed"
  - state/best_candidate.json with the lowest objective
  - state/health_check.json with status "healthy"
  ```

- [ ] **Step 2:** Implement `run_mock_optimization(project_dir, *, max_evaluations=None, seed_override=None)` in `mock_optimizer.py`:
  1. Load and validate the project: `assert_valid_project(project_dir)`.
  2. Read `optimizer.yaml` for algorithm, initialization, batch_size, random_seed, max_evaluations.
  3. Generate candidates using the initialization strategy from Step B3.
  4. For each candidate:
     a. Compute mock metrics (Step B4).
     b. Evaluate constraints.
     c. Evaluate objective.
     d. Write ledger row.
     e. Update best candidate if objective is better.
  5. Write final `optimizer_state.json`, `best_candidate.json`, `health_check.json`.

- [ ] **Step 3:** Add the CLI command:
  ```python
  @app.command("mock-run")
  def mock_run_command(
      project_dir: Annotated[Path, typer.Argument(help="Project directory.")],
      max_evaluations: Annotated[int | None, typer.Option("--max-evaluations", help="Override max_evaluations from optimizer.yaml.")] = None,
  ) -> None:
  ```

- [ ] **Step 4:** Write CLI smoke test: invoke `hermes-workflow mock-run <project_dir>` and verify exit code 0 and expected output files.

- [ ] **Step 5:** Run all tests:
  ```bash
  pytest -q
  ruff check .
  ```

- [ ] **Step 6:** Commit.

### Task B7: Review Gate

**Steps:**

- [ ] **Step 1:** Run spec review via `claude-review.spec_review` against Plan B task text and implementation.

- [ ] **Step 2:** Run code quality review via `claude-review.code_quality_review` against the Plan B diff.

- [ ] **Step 3:** Address any Critical or Important findings from both reviews.

- [ ] **Step 4:** Final verification:
  ```bash
  pytest -q
  ruff check .
  ```

---

## Verification Commands

After each task:

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
pytest tests/test_mock_optimizer.py -v
```

After all tasks:

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
pytest -q
ruff check .
```

## Self-Review

- **Spec coverage:** Plan B covers candidate generation, mock metrics, constraint/objective evaluation, ledger/state persistence, orchestration, CLI, and tests. It excludes real execution, netlist templating, and Claude CLI.
- **Boundary check:** The mock optimizer depends only on `schemas.py` and `validate.py`. It never imports `virtuoso_bridge`, never calls Spectre, and never writes netlist files.
- **Safety check:** The mock optimizer writes only to `ledger/` and `state/` directories inside the project. It does not modify `config/` or `execution_package/`.
- **Open interface check:** The `LedgerRow`, `BestCandidate`, and `OptimizerState` schemas match the contracts expected by Plan A's preflight report readers and approval gate, ensuring the mock loop output is compatible with the existing Hermes workflow.