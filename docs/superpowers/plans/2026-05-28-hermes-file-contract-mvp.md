# Hermes File Contract MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Hermes-side file-contract MVP that validates structured optimization configs, creates Claude execution packages, reads Claude preflight reports, and writes first-run supervisor instructions.

**Architecture:** Plan A treats `config/*.yaml` as the first structured input boundary. Hermes does not parse `USER_TASK.md` in this MVP; a later parser can convert user Markdown or dialogue into these YAML contracts after the file protocol is stable. All downstream agent coordination happens through explicit files rather than chat history.

**Tech Stack:** Python 3.11+, `pydantic>=2`, `PyYAML`, `typer`, `pytest`, `ruff`; no Cadence, Virtuoso, Spectre, TuRBO, or Claude CLI invocation in this plan.

---

## Confirmed Scope

Plan A starts after Hermes has produced or received these structured files:

```text
config/project_config.yaml
config/variables.yaml
config/metrics.yaml
config/spectre.yaml
config/optimizer.yaml
```

Plan A does not parse `USER_TASK.md`, natural language, or semi-structured Markdown into YAML. That conversion belongs to a later plan after the file contracts are stable.

## Included

- Python package scaffold for `hermes_workflow`.
- Pydantic schemas for YAML and JSON file contracts.
- Validation for project config, variables, metrics, constraints, objective, Spectre policy, and optimizer budget.
- Project template generation.
- Claude execution package generation with immutable config hashes.
- `EXECUTION_TASK.md` rendering with safety instructions and expected outputs.
- Claude preflight report readers for `netlist_preparation_report.json`, `dry_run_report.json`, and `health_check.json`.
- Hermes approval gate that writes `supervisor_instruction.json`.
- CLI commands for the above.
- Unit tests and file-contract fixtures.

## Excluded

- `USER_TASK.md` parser.
- Claude CLI or `Claude-cli-skill` invocation.
- Virtuoso bridge startup or Maestro netlist export.
- Spectre simulation.
- Optimizer/TuRBO execution.
- Project-local runner template implementation such as `render_netlist.py`, `dry_run.py`, `run_candidate.py`, or `optimization_loop.py`.
- Final optimization report generation.

## Proposed File Structure

```text
ic-auto-opt-workflow/
├── pyproject.toml
├── README.md
├── src/
│   └── hermes_workflow/
│       ├── __init__.py
│       ├── cli.py
│       ├── schemas.py
│       ├── validate.py
│       ├── package.py
│       ├── reports.py
│       ├── approvals.py
│       └── templates/
│           └── spectre_maestro_project/
│               ├── TASK.md
│               ├── METRICS.md
│               ├── CIRCUIT_KNOWLEDGE.md
│               ├── FAILURE_PLAYBOOK.md
│               ├── config/
│               │   ├── project_config.yaml
│               │   ├── variables.yaml
│               │   ├── metrics.yaml
│               │   ├── spectre.yaml
│               │   └── optimizer.yaml
│               ├── netlists/
│               │   ├── exported/.gitkeep
│               │   └── templates/.gitkeep
│               ├── src/.gitkeep
│               ├── execution_package/.gitkeep
│               ├── ledger/.gitkeep
│               ├── state/.gitkeep
│               └── reports/.gitkeep
└── tests/
    ├── fixtures/
    │   └── bridge_test_inv/
    │       ├── project_config.yaml
    │       ├── variables.yaml
    │       ├── metrics.yaml
    │       ├── spectre.yaml
    │       ├── optimizer.yaml
    │       ├── reports/
    │       │   ├── netlist_preparation_report.pass.json
    │       │   ├── dry_run_report.pass.json
    │       │   └── review_report.pass.md
    │       └── state/
    │           └── health_check.pass.json
    ├── test_cli.py
    ├── test_schemas.py
    ├── test_validate.py
    ├── test_package.py
    ├── test_reports.py
    └── test_approvals.py
```

## Module Boundaries

`schemas.py` owns typed file contracts. It contains Pydantic models and enums only.

`validate.py` owns config loading and cross-file consistency checks. It returns structured validation issues and raises only at the explicit `assert_valid_project` boundary.

`package.py` owns template copying, immutable hash calculation, execution package construction, and `EXECUTION_TASK.md` rendering.

`reports.py` owns loading Claude preflight outputs and validating whether those outputs satisfy the file contract.

`approvals.py` owns approval decisions and writing `supervisor_instruction.json`.

`cli.py` owns Typer command wiring and text output only; business logic stays in the modules above.

## Planning Status

The five structured YAML contracts are confirmed. The remainder of this plan decomposes Plan A into TDD implementation tasks.

## Confirmed Contract Decisions

### MVP backend stance

Responsibility: keep the first runnable system focused on the original Maestro-exported Spectre deck backend while acknowledging that complex Maestro formulas will need later per-analysis references.

Confirmed rules:

- Continue the MVP with the standalone Spectre flow:
  `Maestro export input.scs -> template approved variables -> run standalone Spectre -> compute metrics from Spectre results`.
- Do not pivot the first MVP to a Maestro-managed simulation loop yet.
- Complex formula fidelity is deferred to later reference work. As real `virtuoso-bridge` optimization tests cover `tran`, `dc`, `sp`, `pss`, `pnoise`, `stb`, and related flows, collect formula-specific implementation references for each analysis family.
- `maestro_formula` is retained in `metrics.yaml` for traceability, review, and future reference generation.
- The MVP does not assume an agent can correctly interpret every Maestro calculator expression from free text.
- Plan A validates only the file contract, references, and expression dependencies; later Claude-side plans own metric implementation and comparison against real simulation results.

### `project_config.yaml`

Responsibility: project identity, single-corner Maestro testbench locator, netlist path contract, and safety policy.

Confirmed rules:

- First version supports exactly one corner as `testbench.corner`.
- Multi-corner support is deferred until the Maestro integration plan.
- `netlist.exported_input_scs` and `netlist.template_scs` live in `project_config.yaml`.
- Netlist paths are generated by Hermes/template, not normally specified by the user.
- Netlist paths must be project-relative, must not contain `..`, and must stay under `netlists/exported/` and `netlists/templates/`.

Confirmed shape:

```yaml
schema_version: "1.0"

project:
  name: bridge_test_inv
  description: "Optimize inverter sizing from an existing Maestro testbench"
  backend: maestro_exported_spectre_deck

testbench:
  virtuoso_library: Virtuoso_Bridge_test
  cell: bridge_test_inv
  design_view: schematic
  maestro_view: maestro
  test_name: tran_dc_test
  corner: Nominal

netlist:
  source: existing_maestro_setup
  export_method: maeCreateNetlistForCorner
  exported_input_scs: netlists/exported/input.scs
  template_scs: netlists/templates/template.scs

safety:
  immutable_after_package: true
  require_hermes_approval_before_real_run: true
  allow_maestro_setup_modification: false
  allow_only_variable_templating: true
```

### `variables.yaml`

Responsibility: whitelist the exact variables Claude may template and define the quantized search space.

Confirmed rules:

- First version supports only `integer` and `continuous_step`.
- This matches EDA simulation practice: all candidates are quantized and reproducible.
- Users provide complete values with units where units exist, such as `"0.3 um"`.
- Do not require `description`, `device`, or a separate `unit` field.
- Claude only needs the complete variable name to find the variable in exported `input.scs`.
- `name` values must be unique and must match `[A-Za-z_][A-Za-z0-9_]*`.
- `integer` values must parse as integers.
- `continuous_step` lower, upper, and step must use compatible unit suffixes.

Confirmed shape:

```yaml
schema_version: "1.0"

variables:
  - name: FN
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WN
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"

  - name: FP
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WP
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"
```

### `metrics.yaml`

Responsibility: define simulation metrics, hard constraints, and the scalar objective in one file because constraints and objective reference metric names.

Confirmed rules:

- `metrics`, `constraints`, and `objective` live in the same YAML file.
- `metrics[].maestro_formula` stores the user-provided Maestro result formula.
- The MVP does not implement a generic Maestro calculator parser.
- `metrics[].maestro_formula` is not treated as executable by Plan A.
- `metrics[].required_signals` is an explicit contract field. It may be produced upstream from the user-provided Maestro formula, then written into `metrics.yaml`.
- Plan A validates that `required_signals` exists and is non-empty. Later Claude-side plans verify these signals against exported `input.scs` and Spectre results.
- Constraint operators support only `lt`, `le`, `gt`, and `ge`.
- `eq` is intentionally not supported because exact equality is fragile in simulation workflows.
- `objective.direction` supports both `minimize` and `maximize`.
- A later runner can transform `maximize` into minimization by negating the scalar objective.
- `objective.expression` may reference only metric names, numeric literals, arithmetic operators, and parentheses.
- Function calls, imports, attribute access, and unknown symbols are invalid.
- Every metric referenced by `constraints[].metric` or `objective.expression` must be declared under `metrics`.

Confirmed shape:

```yaml
schema_version: "1.0"

metrics:
  - name: rise
    unit: ps
    maestro_formula: "riseTime(VT('/VOUT') 0 nil 1.2 nil 10 90 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: fall
    unit: ps
    maestro_formula: "fallTime(VT('/VOUT') 0 nil 1.2 nil 90 10 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: DC
    unit: u
    maestro_formula: "average(abs(IT('/VDD')))"
    required_signals:
      - VDD

constraints:
  - metric: rise
    op: lt
    value: "80 ps"

  - metric: fall
    op: lt
    value: "80 ps"

  - metric: DC
    op: lt
    value: "400 u"

objective:
  direction: minimize
  expression: "(rise + fall) * DC"
```

### `spectre.yaml`

Responsibility: define standalone Spectre execution policy for the exported deck. It does not define analyses, models, save options, simulator options, or outputs; those remain owned by the Maestro-exported `input.scs`.

Confirmed rules:

- First version supports only Spectre X presets.
- Supported presets are `cx`, `ax`, `mx`, `lx`, and `vx`.
- Do not expose plain Spectre, APS, or Spectre FX in the first version.
- Do not expose ADE-style Spectre/APS accuracy settings such as `Do not override`, `Liberal`, `Moderate`, or `Conservative` in the first version.
- The runner maps `preset: ax` to the existing `virtuoso-bridge-lite` call `spectre_mode_args("ax")`, which emits CLI args `+preset=ax +mt`.
- The `+mt` argument enables Spectre multithreading for each simulation task. The first version does not expose thread count; when no count is given, thread allocation is left to Spectre, the Cadence environment, and host policy.
- `output_format` must be `psfascii` because the current parser path reads PSF ASCII into `SimulationResult.data`.
- `parallel_jobs` is candidate-level concurrency and must be at least `1`.
- `timeout_s` is per-candidate Spectre timeout, must be positive, and must be explicitly provided by the user/upstream Hermes config. Do not rely on a hidden default because pre-layout and post-layout simulation runtime can differ by orders of magnitude.
- Real-run code should check the Spectre license when `require_license_check` is true.

Confirmed shape:

```yaml
schema_version: "1.0"

spectre:
  engine: spectre_x
  preset: ax
  output_format: psfascii
  parallel_jobs: 10
  timeout_s: 3600
  require_license_check: true
  keep_failed_runs: true
  keep_successful_runs: true
```

### `optimizer.yaml`

Responsibility: define candidate search strategy, total candidate budget, per-batch candidate count, reproducibility, and failure penalty. It does not define variable bounds, constraints, objective expression, or Spectre execution policy.

Confirmed rules:

- First version supports `algorithm: turbo` and `algorithm: random`.
- `random` is allowed as a debug/fallback algorithm so the end-to-end system can run before TuRBO tuning is stable.
- `initialization` defines how the first candidate samples are generated before model-based search has enough data.
- Supported initialization methods are `sobol`, `latin_hypercube`, and `random`.
- `max_evaluations` means total candidate simulations, not optimizer rounds.
- One evaluation equals one candidate parameter set, one Spectre run, and one ledger row.
- `batch_size` means candidates generated per optimizer batch.
- `max_batches` is derived as `ceil(max_evaluations / batch_size)` and must not be stored as a separate YAML field.
- `batch_size` must be less than or equal to `spectre.parallel_jobs` because `spectre.parallel_jobs` is the server resource limit.
- `random_seed` is required for reproducibility.
- `failure_penalty` must be a positive finite number.
- `deduplicate_candidates` must be true in the MVP because integer and stepped variables can collide after quantization.
- If `algorithm` is `turbo`, `max_evaluations` must be at least `2 * number_of_variables`.

Confirmed shape:

```yaml
schema_version: "1.0"

optimizer:
  algorithm: turbo
  initialization: sobol
  max_evaluations: 100
  batch_size: 10
  random_seed: 20260528
  failure_penalty: 1000000.0
  deduplicate_candidates: true
```

## Plan A Task Breakdown

The tasks below intentionally stop at Hermes file contracts, project packaging, preflight report reading, and first-run approval. They do not implement real Virtuoso, Spectre, optimizer, Claude CLI, or `USER_TASK.md` parsing behavior.

### Task 1: Python Package Scaffold

**Files:**
- Create: `ic-auto-opt-workflow/pyproject.toml`
- Create: `ic-auto-opt-workflow/README.md`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/__init__.py`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/cli.py`
- Create: `ic-auto-opt-workflow/tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI version test**

Create `ic-auto-opt-workflow/tests/test_cli.py`:

```python
from typer.testing import CliRunner

from hermes_workflow.cli import app


runner = CliRunner()


def test_cli_version_prints_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_cli.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow'`.

- [ ] **Step 3: Add the minimal package metadata**

Create `ic-auto-opt-workflow/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "ic-auto-opt-workflow"
version = "0.1.0"
description = "Hermes file-contract workflow for IC auto optimization"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "PyYAML>=6.0",
    "typer>=0.12",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
]

[project.scripts]
hermes-workflow = "hermes_workflow.cli:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

Create `ic-auto-opt-workflow/README.md`:

```markdown
# IC Auto Opt Workflow

Hermes-side file contracts for IC auto optimization on top of `virtuoso-bridge-lite`.

The first MVP validates five structured YAML files, builds Claude execution packages, reads Claude preflight reports, and writes first-run supervisor instructions. It does not parse `USER_TASK.md`, invoke Claude CLI, run Virtuoso, run Spectre, or run an optimizer loop.
```

Create `ic-auto-opt-workflow/src/hermes_workflow/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `ic-auto-opt-workflow/src/hermes_workflow/cli.py`:

```python
from typing import Annotated

import typer

from hermes_workflow import __version__


app = typer.Typer(help="Hermes file-contract workflow tools.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the package version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    return None
```

- [ ] **Step 4: Run the CLI test to verify it passes**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add pyproject.toml README.md src/hermes_workflow/__init__.py src/hermes_workflow/cli.py tests/test_cli.py
git commit -m "chore: scaffold hermes workflow package"
```

### Task 2: YAML Schema Models

**Files:**
- Create: `ic-auto-opt-workflow/src/hermes_workflow/schemas.py`
- Create: `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/project_config.yaml`
- Create: `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/variables.yaml`
- Create: `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/metrics.yaml`
- Create: `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/spectre.yaml`
- Create: `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/optimizer.yaml`
- Create: `ic-auto-opt-workflow/tests/test_schemas.py`

- [ ] **Step 1: Add fixture YAML files for the confirmed contracts**

Create `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/project_config.yaml`:

```yaml
schema_version: "1.0"

project:
  name: bridge_test_inv
  description: "Optimize inverter sizing from an existing Maestro testbench"
  backend: maestro_exported_spectre_deck

testbench:
  virtuoso_library: Virtuoso_Bridge_test
  cell: bridge_test_inv
  design_view: schematic
  maestro_view: maestro
  test_name: tran_dc_test
  corner: Nominal

netlist:
  source: existing_maestro_setup
  export_method: maeCreateNetlistForCorner
  exported_input_scs: netlists/exported/input.scs
  template_scs: netlists/templates/template.scs

safety:
  immutable_after_package: true
  require_hermes_approval_before_real_run: true
  allow_maestro_setup_modification: false
  allow_only_variable_templating: true
```

Create `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/variables.yaml`:

```yaml
schema_version: "1.0"

variables:
  - name: FN
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WN
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"

  - name: FP
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WP
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"
```

Create `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/metrics.yaml`:

```yaml
schema_version: "1.0"

metrics:
  - name: rise
    unit: ps
    maestro_formula: "riseTime(VT('/VOUT') 0 nil 1.2 nil 10 90 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: fall
    unit: ps
    maestro_formula: "fallTime(VT('/VOUT') 0 nil 1.2 nil 90 10 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: DC
    unit: u
    maestro_formula: "average(abs(IT('/VDD')))"
    required_signals:
      - VDD

constraints:
  - metric: rise
    op: lt
    value: "80 ps"

  - metric: fall
    op: lt
    value: "80 ps"

  - metric: DC
    op: lt
    value: "400 u"

objective:
  direction: minimize
  expression: "(rise + fall) * DC"
```

Create `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/spectre.yaml`:

```yaml
schema_version: "1.0"

spectre:
  engine: spectre_x
  preset: ax
  output_format: psfascii
  parallel_jobs: 10
  timeout_s: 3600
  require_license_check: true
  keep_failed_runs: true
  keep_successful_runs: true
```

Create `ic-auto-opt-workflow/tests/fixtures/bridge_test_inv/config/optimizer.yaml`:

```yaml
schema_version: "1.0"

optimizer:
  algorithm: turbo
  initialization: sobol
  max_evaluations: 100
  batch_size: 10
  random_seed: 20260528
  failure_penalty: 1000000.0
  deduplicate_candidates: true
```

- [ ] **Step 2: Write failing schema parsing tests**

Create `ic-auto-opt-workflow/tests/test_schemas.py`:

```python
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hermes_workflow.schemas import (
    MetricsConfig,
    OptimizerConfig,
    ProjectConfig,
    SpectreConfig,
    VariablesConfig,
)


FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "bridge_test_inv" / "config"


def load_yaml(file_name: str) -> dict:
    return yaml.safe_load((FIXTURE_CONFIG / file_name).read_text(encoding="utf-8"))


def test_schema_models_parse_confirmed_contracts() -> None:
    project = ProjectConfig.model_validate(load_yaml("project_config.yaml"))
    variables = VariablesConfig.model_validate(load_yaml("variables.yaml"))
    metrics = MetricsConfig.model_validate(load_yaml("metrics.yaml"))
    spectre = SpectreConfig.model_validate(load_yaml("spectre.yaml"))
    optimizer = OptimizerConfig.model_validate(load_yaml("optimizer.yaml"))

    assert project.project.name == "bridge_test_inv"
    assert [variable.name for variable in variables.variables] == ["FN", "WN", "FP", "WP"]
    assert [metric.name for metric in metrics.metrics] == ["rise", "fall", "DC"]
    assert spectre.spectre.engine == "spectre_x"
    assert spectre.spectre.preset == "ax"
    assert optimizer.optimizer.algorithm == "turbo"


def test_variables_reject_duplicate_names() -> None:
    payload = load_yaml("variables.yaml")
    payload["variables"][1]["name"] = "FN"

    with pytest.raises(ValidationError, match="variable names must be unique"):
        VariablesConfig.model_validate(payload)


def test_metrics_reject_empty_required_signals() -> None:
    payload = load_yaml("metrics.yaml")
    payload["metrics"][0]["required_signals"] = []

    with pytest.raises(ValidationError, match="required_signals must not be empty"):
        MetricsConfig.model_validate(payload)


def test_spectre_rejects_non_spectre_x_engine() -> None:
    payload = load_yaml("spectre.yaml")
    payload["spectre"]["engine"] = "aps"

    with pytest.raises(ValidationError):
        SpectreConfig.model_validate(payload)
```

- [ ] **Step 3: Run schema tests to verify they fail**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_schemas.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.schemas'`.

- [ ] **Step 4: Implement schema models**

Create `ic-auto-opt-workflow/src/hermes_workflow/schemas.py`:

```python
from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_name(value: str, label: str) -> str:
    if not NAME_RE.match(value):
        raise ValueError(f"{label} must match [A-Za-z_][A-Za-z0-9_]*")
    return value


class VariableKind(StrEnum):
    INTEGER = "integer"
    CONTINUOUS_STEP = "continuous_step"


class ConstraintOp(StrEnum):
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"


class ObjectiveDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class SpectrePreset(StrEnum):
    CX = "cx"
    AX = "ax"
    MX = "mx"
    LX = "lx"
    VX = "vx"


class OptimizerAlgorithm(StrEnum):
    TURBO = "turbo"
    RANDOM = "random"


class InitializationMethod(StrEnum):
    SOBOL = "sobol"
    LATIN_HYPERCUBE = "latin_hypercube"
    RANDOM = "random"


class ProjectInfo(StrictModel):
    name: str
    description: str = ""
    backend: Literal["maestro_exported_spectre_deck"]

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "project.name")


class TestbenchConfig(StrictModel):
    virtuoso_library: str
    cell: str
    design_view: str
    maestro_view: str
    test_name: str
    corner: str


class NetlistConfig(StrictModel):
    source: Literal["existing_maestro_setup"]
    export_method: Literal["maeCreateNetlistForCorner"]
    exported_input_scs: str
    template_scs: str


class SafetyConfig(StrictModel):
    immutable_after_package: Literal[True]
    require_hermes_approval_before_real_run: Literal[True]
    allow_maestro_setup_modification: Literal[False]
    allow_only_variable_templating: Literal[True]


class ProjectConfig(StrictModel):
    schema_version: Literal["1.0"]
    project: ProjectInfo
    testbench: TestbenchConfig
    netlist: NetlistConfig
    safety: SafetyConfig


class VariableSpec(StrictModel):
    name: str
    kind: VariableKind
    lower: str
    upper: str
    step: str

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "variable name")


class VariablesConfig(StrictModel):
    schema_version: Literal["1.0"]
    variables: list[VariableSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _variable_names_are_unique(self) -> "VariablesConfig":
        names = [variable.name for variable in self.variables]
        if len(names) != len(set(names)):
            raise ValueError("variable names must be unique")
        return self


class MetricSpec(StrictModel):
    name: str
    unit: str
    maestro_formula: str
    required_signals: list[str]

    @field_validator("name")
    @classmethod
    def _name_is_identifier(cls, value: str) -> str:
        return validate_name(value, "metric name")

    @field_validator("required_signals")
    @classmethod
    def _required_signals_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("required_signals must not be empty")
        return value


class ConstraintSpec(StrictModel):
    metric: str
    op: ConstraintOp
    value: str

    @field_validator("metric")
    @classmethod
    def _metric_is_identifier(cls, value: str) -> str:
        return validate_name(value, "constraint metric")


class ObjectiveSpec(StrictModel):
    direction: ObjectiveDirection
    expression: str


class MetricsConfig(StrictModel):
    schema_version: Literal["1.0"]
    metrics: list[MetricSpec] = Field(min_length=1)
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    objective: ObjectiveSpec

    @model_validator(mode="after")
    def _metric_names_are_unique(self) -> "MetricsConfig":
        names = [metric.name for metric in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("metric names must be unique")
        return self


class SpectreSettings(StrictModel):
    engine: Literal["spectre_x"]
    preset: SpectrePreset
    output_format: Literal["psfascii"]
    parallel_jobs: int = Field(ge=1)
    timeout_s: int = Field(gt=0)
    require_license_check: bool
    keep_failed_runs: bool
    keep_successful_runs: bool


class SpectreConfig(StrictModel):
    schema_version: Literal["1.0"]
    spectre: SpectreSettings


class OptimizerSettings(StrictModel):
    algorithm: OptimizerAlgorithm
    initialization: InitializationMethod
    max_evaluations: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    random_seed: int
    failure_penalty: float = Field(gt=0)
    deduplicate_candidates: Literal[True]


class OptimizerConfig(StrictModel):
    schema_version: Literal["1.0"]
    optimizer: OptimizerSettings
```

- [ ] **Step 5: Run schema tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_schemas.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/schemas.py tests/fixtures/bridge_test_inv/config tests/test_schemas.py
git commit -m "feat: define hermes yaml schemas"
```

### Task 3: Cross-File Contract Validation

**Files:**
- Create: `ic-auto-opt-workflow/src/hermes_workflow/validate.py`
- Create: `ic-auto-opt-workflow/tests/test_validate.py`

- [ ] **Step 1: Write failing validation tests**

Create `ic-auto-opt-workflow/tests/test_validate.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from hermes_workflow.validate import assert_valid_project, validate_project_files


FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "bridge_test_inv"


def copy_fixture_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "bridge_test_inv"
    shutil.copytree(FIXTURE_PROJECT, project_dir)
    return project_dir


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_valid_project_files_pass(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)

    report = validate_project_files(project_dir)

    assert report.ok is True
    assert report.issues == []
    assert_valid_project(project_dir)


def test_batch_size_must_not_exceed_spectre_parallel_jobs(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    optimizer_path = project_dir / "config" / "optimizer.yaml"
    payload = read_yaml(optimizer_path)
    payload["optimizer"]["batch_size"] = 11
    write_yaml(optimizer_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any(
        issue.message == "optimizer.batch_size must be <= spectre.parallel_jobs"
        for issue in report.issues
    )


def test_objective_expression_rejects_function_calls(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "max(rise, fall)"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any("unsupported objective expression node Call" in issue.message for issue in report.issues)


def test_objective_expression_rejects_unknown_metric_names(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    metrics_path = project_dir / "config" / "metrics.yaml"
    payload = read_yaml(metrics_path)
    payload["objective"]["expression"] = "(rise + slew) * DC"
    write_yaml(metrics_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any("objective references unknown metric slew" in issue.message for issue in report.issues)


def test_netlist_paths_must_stay_under_expected_directories(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    project_config_path = project_dir / "config" / "project_config.yaml"
    payload = read_yaml(project_config_path)
    payload["netlist"]["exported_input_scs"] = "../input.scs"
    write_yaml(project_config_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any("netlist.exported_input_scs must stay under netlists/exported/" in issue.message for issue in report.issues)


def test_continuous_step_units_must_match(tmp_path: Path) -> None:
    project_dir = copy_fixture_project(tmp_path)
    variables_path = project_dir / "config" / "variables.yaml"
    payload = read_yaml(variables_path)
    payload["variables"][1]["step"] = "200 nm"
    write_yaml(variables_path, payload)

    report = validate_project_files(project_dir)

    assert report.ok is False
    assert any("WN lower, upper, and step unit suffixes must match" in issue.message for issue in report.issues)
```

- [ ] **Step 2: Run validation tests to verify they fail**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_validate.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.validate'`.

- [ ] **Step 3: Implement project validation**

Create `ic-auto-opt-workflow/src/hermes_workflow/validate.py`:

```python
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from hermes_workflow.schemas import (
    MetricsConfig,
    OptimizerConfig,
    ProjectConfig,
    VariableKind,
    VariablesConfig,
    SpectreConfig,
)


CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "project_config.yaml": ProjectConfig,
    "variables.yaml": VariablesConfig,
    "metrics.yaml": MetricsConfig,
    "spectre.yaml": SpectreConfig,
    "optimizer.yaml": OptimizerConfig,
}

QUANTITY_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z0-9_/%]*)\s*$")


@dataclass(frozen=True)
class ValidationIssue:
    file: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def format(self) -> str:
        if self.ok:
            return "validation passed"
        return "\n".join(f"{issue.file}:{issue.path}: {issue.message}" for issue in self.issues)


@dataclass(frozen=True)
class ContractBundle:
    project_dir: Path
    project_config: ProjectConfig
    variables: VariablesConfig
    metrics: MetricsConfig
    spectre: SpectreConfig
    optimizer: OptimizerConfig


def validate_project_files(project_dir: Path) -> ValidationReport:
    config_dir = Path(project_dir) / "config"
    issues: list[ValidationIssue] = []
    loaded: dict[str, BaseModel] = {}

    for file_name, model_type in CONFIG_MODELS.items():
        path = config_dir / file_name
        if not path.exists():
            issues.append(ValidationIssue(file_name, "$", "required config file is missing"))
            continue
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            issues.append(ValidationIssue(file_name, "$", f"invalid YAML: {exc}"))
            continue
        if payload is None:
            payload = {}
        try:
            loaded[file_name] = model_type.model_validate(payload)
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"])
                issues.append(ValidationIssue(file_name, location, str(error["msg"])))

    if issues:
        return ValidationReport(issues)

    bundle = ContractBundle(
        project_dir=Path(project_dir),
        project_config=loaded["project_config.yaml"],
        variables=loaded["variables.yaml"],
        metrics=loaded["metrics.yaml"],
        spectre=loaded["spectre.yaml"],
        optimizer=loaded["optimizer.yaml"],
    )
    issues.extend(_validate_bundle(bundle))
    return ValidationReport(issues)


def assert_valid_project(project_dir: Path) -> ContractBundle:
    report = validate_project_files(project_dir)
    if not report.ok:
        raise ValueError(report.format())
    return load_contract_bundle(project_dir)


def load_contract_bundle(project_dir: Path) -> ContractBundle:
    config_dir = Path(project_dir) / "config"
    payloads: dict[str, Any] = {}
    for file_name in CONFIG_MODELS:
        payloads[file_name] = yaml.safe_load((config_dir / file_name).read_text(encoding="utf-8"))
    return ContractBundle(
        project_dir=Path(project_dir),
        project_config=ProjectConfig.model_validate(payloads["project_config.yaml"]),
        variables=VariablesConfig.model_validate(payloads["variables.yaml"]),
        metrics=MetricsConfig.model_validate(payloads["metrics.yaml"]),
        spectre=SpectreConfig.model_validate(payloads["spectre.yaml"]),
        optimizer=OptimizerConfig.model_validate(payloads["optimizer.yaml"]),
    )


def _validate_bundle(bundle: ContractBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_netlist_paths(bundle.project_config))
    issues.extend(_validate_variables(bundle.variables))
    issues.extend(_validate_metric_references(bundle.metrics))
    issues.extend(_validate_objective_expression(bundle.metrics))
    issues.extend(_validate_optimizer_against_spectre(bundle))
    return issues


def _validate_netlist_paths(config: ProjectConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    checks = [
        ("exported_input_scs", config.netlist.exported_input_scs, PurePosixPath("netlists/exported")),
        ("template_scs", config.netlist.template_scs, PurePosixPath("netlists/templates")),
    ]
    for field_name, value, required_parent in checks:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.parts[: len(required_parent.parts)] == required_parent.parts:
            issues.append(
                ValidationIssue(
                    "project_config.yaml",
                    f"netlist.{field_name}",
                    f"netlist.{field_name} must stay under {required_parent.as_posix()}/",
                )
            )
    return issues


def _validate_variables(config: VariablesConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for variable in config.variables:
        if variable.kind == VariableKind.INTEGER:
            issues.extend(_validate_integer_variable(variable.name, variable.lower, variable.upper, variable.step))
        else:
            issues.extend(_validate_continuous_step_variable(variable.name, variable.lower, variable.upper, variable.step))
    return issues


def _validate_integer_variable(name: str, lower_text: str, upper_text: str, step_text: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    parsed: list[int] = []
    for label, text in [("lower", lower_text), ("upper", upper_text), ("step", step_text)]:
        try:
            if text.strip() != str(int(text.strip())):
                raise ValueError
            parsed.append(int(text.strip()))
        except ValueError:
            issues.append(ValidationIssue("variables.yaml", name, f"{name} {label} must be an integer without units"))
    if issues:
        return issues
    lower, upper, step = parsed
    if step <= 0:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} step must be positive"))
    if lower > upper:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} lower must be <= upper"))
    if step > 0 and (upper - lower) % step != 0:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} range must be divisible by step"))
    return issues


def _validate_continuous_step_variable(name: str, lower_text: str, upper_text: str, step_text: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    quantities = []
    for label, text in [("lower", lower_text), ("upper", upper_text), ("step", step_text)]:
        try:
            quantities.append(_parse_quantity(text))
        except ValueError:
            issues.append(ValidationIssue("variables.yaml", name, f"{name} {label} must be a numeric value with optional unit suffix"))
    if issues:
        return issues
    lower, upper, step = quantities
    units = {lower[1], upper[1], step[1]}
    if len(units) != 1:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} lower, upper, and step unit suffixes must match"))
    if step[0] <= 0:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} step must be positive"))
    if lower[0] > upper[0]:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} lower must be <= upper"))
    if step[0] > 0 and (upper[0] - lower[0]) % step[0] != 0:
        issues.append(ValidationIssue("variables.yaml", name, f"{name} range must be divisible by step"))
    return issues


def _parse_quantity(text: str) -> tuple[Decimal, str]:
    match = QUANTITY_RE.match(text)
    if not match:
        raise ValueError(text)
    number_text, unit = match.groups()
    try:
        return Decimal(number_text), unit
    except InvalidOperation as exc:
        raise ValueError(text) from exc


def _validate_metric_references(config: MetricsConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    metric_names = {metric.name for metric in config.metrics}
    for constraint in config.constraints:
        if constraint.metric not in metric_names:
            issues.append(
                ValidationIssue(
                    "metrics.yaml",
                    f"constraints.{constraint.metric}",
                    f"constraint references unknown metric {constraint.metric}",
                )
            )
    return issues


def _validate_objective_expression(config: MetricsConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    metric_names = {metric.name for metric in config.metrics}
    try:
        expression = ast.parse(config.objective.expression, mode="eval")
    except SyntaxError as exc:
        return [ValidationIssue("metrics.yaml", "objective.expression", f"invalid objective expression syntax: {exc.msg}")]

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
    )
    for node in ast.walk(expression):
        if not isinstance(node, allowed_nodes):
            issues.append(
                ValidationIssue(
                    "metrics.yaml",
                    "objective.expression",
                    f"unsupported objective expression node {type(node).__name__}",
                )
            )
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float):
            issues.append(
                ValidationIssue(
                    "metrics.yaml",
                    "objective.expression",
                    "objective constants must be numeric",
                )
            )
        if isinstance(node, ast.Name) and node.id not in metric_names:
            issues.append(
                ValidationIssue(
                    "metrics.yaml",
                    "objective.expression",
                    f"objective references unknown metric {node.id}",
                )
            )
    return issues


def _validate_optimizer_against_spectre(bundle: ContractBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    optimizer = bundle.optimizer.optimizer
    spectre = bundle.spectre.spectre
    if optimizer.batch_size > spectre.parallel_jobs:
        issues.append(
            ValidationIssue(
                "optimizer.yaml",
                "optimizer.batch_size",
                "optimizer.batch_size must be <= spectre.parallel_jobs",
            )
        )
    if optimizer.algorithm == "turbo" and optimizer.max_evaluations < 2 * len(bundle.variables.variables):
        issues.append(
            ValidationIssue(
                "optimizer.yaml",
                "optimizer.max_evaluations",
                "turbo max_evaluations must be at least 2 * number_of_variables",
            )
        )
    return issues
```

- [ ] **Step 4: Run validation tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_validate.py -v
```

Expected: PASS.

- [ ] **Step 5: Run schema and validation tests together**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_schemas.py tests/test_validate.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/validate.py tests/test_validate.py
git commit -m "feat: validate hermes config contracts"
```

### Task 4: Project Template Generation

**Files:**
- Create: `ic-auto-opt-workflow/src/hermes_workflow/package.py`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/TASK.md`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/METRICS.md`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/CIRCUIT_KNOWLEDGE.md`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/FAILURE_PLAYBOOK.md`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/project_config.yaml`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/variables.yaml`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/metrics.yaml`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/spectre.yaml`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/optimizer.yaml`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/netlists/exported/.gitkeep`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/netlists/templates/.gitkeep`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/src/.gitkeep`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/execution_package/.gitkeep`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/ledger/.gitkeep`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/state/.gitkeep`
- Create: `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/reports/.gitkeep`
- Create: `ic-auto-opt-workflow/tests/test_package.py`

- [ ] **Step 1: Write failing project template tests**

Create `ic-auto-opt-workflow/tests/test_package.py`:

```python
from pathlib import Path

import pytest

from hermes_workflow.package import TemplateError, create_project_from_template
from hermes_workflow.validate import validate_project_files


def test_create_project_from_template_writes_expected_tree(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"

    create_project_from_template(project_dir)

    assert (project_dir / "TASK.md").exists()
    assert (project_dir / "METRICS.md").exists()
    assert (project_dir / "config" / "project_config.yaml").exists()
    assert (project_dir / "netlists" / "exported").is_dir()
    assert (project_dir / "netlists" / "templates").is_dir()
    assert (project_dir / "execution_package").is_dir()
    assert (project_dir / "reports").is_dir()
    assert validate_project_files(project_dir).ok is True


def test_create_project_from_template_refuses_non_empty_destination(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    project_dir.mkdir()
    (project_dir / "existing.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(TemplateError, match="destination already exists and is not empty"):
        create_project_from_template(project_dir)
```

- [ ] **Step 2: Run project template tests to verify they fail**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_package.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.package'`.

- [ ] **Step 3: Add template files**

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/TASK.md`:

```markdown
# Optimization Task

This project is driven by the structured files under `config/`.

Hermes owns the config files and approval gate. Claude Code owns netlist export, variable templating, project-local metric code, dry run, and real optimization only after Hermes approval.
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/METRICS.md`:

```markdown
# Metric Contract Notes

Metric definitions live in `config/metrics.yaml`.

`maestro_formula` is preserved for traceability and review. The first MVP does not implement a generic Maestro calculator parser.
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/CIRCUIT_KNOWLEDGE.md`:

```markdown
# Circuit Knowledge

Record circuit-specific interpretation notes here during execution. Do not change `config/*.yaml` when adding notes.
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/FAILURE_PLAYBOOK.md`:

```markdown
# Failure Playbook

Use this file for project-specific recovery notes after Claude writes an escalation report.
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/project_config.yaml`:

```yaml
schema_version: "1.0"

project:
  name: bridge_test_inv
  description: "Optimize inverter sizing from an existing Maestro testbench"
  backend: maestro_exported_spectre_deck

testbench:
  virtuoso_library: Virtuoso_Bridge_test
  cell: bridge_test_inv
  design_view: schematic
  maestro_view: maestro
  test_name: tran_dc_test
  corner: Nominal

netlist:
  source: existing_maestro_setup
  export_method: maeCreateNetlistForCorner
  exported_input_scs: netlists/exported/input.scs
  template_scs: netlists/templates/template.scs

safety:
  immutable_after_package: true
  require_hermes_approval_before_real_run: true
  allow_maestro_setup_modification: false
  allow_only_variable_templating: true
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/variables.yaml`:

```yaml
schema_version: "1.0"

variables:
  - name: FN
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WN
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"

  - name: FP
    kind: integer
    lower: "2"
    upper: "12"
    step: "1"

  - name: WP
    kind: continuous_step
    lower: "0.3 um"
    upper: "3 um"
    step: "0.2 um"
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/metrics.yaml`:

```yaml
schema_version: "1.0"

metrics:
  - name: rise
    unit: ps
    maestro_formula: "riseTime(VT('/VOUT') 0 nil 1.2 nil 10 90 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: fall
    unit: ps
    maestro_formula: "fallTime(VT('/VOUT') 0 nil 1.2 nil 90 10 nil 'time')"
    required_signals:
      - time
      - VOUT

  - name: DC
    unit: u
    maestro_formula: "average(abs(IT('/VDD')))"
    required_signals:
      - VDD

constraints:
  - metric: rise
    op: lt
    value: "80 ps"

  - metric: fall
    op: lt
    value: "80 ps"

  - metric: DC
    op: lt
    value: "400 u"

objective:
  direction: minimize
  expression: "(rise + fall) * DC"
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/spectre.yaml`:

```yaml
schema_version: "1.0"

spectre:
  engine: spectre_x
  preset: ax
  output_format: psfascii
  parallel_jobs: 10
  timeout_s: 3600
  require_license_check: true
  keep_failed_runs: true
  keep_successful_runs: true
```

Create `ic-auto-opt-workflow/src/hermes_workflow/templates/spectre_maestro_project/config/optimizer.yaml`:

```yaml
schema_version: "1.0"

optimizer:
  algorithm: turbo
  initialization: sobol
  max_evaluations: 100
  batch_size: 10
  random_seed: 20260528
  failure_penalty: 1000000.0
  deduplicate_candidates: true
```

Create empty `.gitkeep` files at:

```text
src/hermes_workflow/templates/spectre_maestro_project/netlists/exported/.gitkeep
src/hermes_workflow/templates/spectre_maestro_project/netlists/templates/.gitkeep
src/hermes_workflow/templates/spectre_maestro_project/src/.gitkeep
src/hermes_workflow/templates/spectre_maestro_project/execution_package/.gitkeep
src/hermes_workflow/templates/spectre_maestro_project/ledger/.gitkeep
src/hermes_workflow/templates/spectre_maestro_project/state/.gitkeep
src/hermes_workflow/templates/spectre_maestro_project/reports/.gitkeep
```

- [ ] **Step 4: Implement template copy logic**

Create `ic-auto-opt-workflow/src/hermes_workflow/package.py`:

```python
from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path


TEMPLATE_PACKAGE = "hermes_workflow"
TEMPLATE_PATH = ("templates", "spectre_maestro_project")


class TemplateError(RuntimeError):
    pass


def _copy_template_tree(destination: Path) -> None:
    template = resources.files(TEMPLATE_PACKAGE).joinpath(*TEMPLATE_PATH)
    if not template.is_dir():
        raise TemplateError("project template is not packaged")

    for item in template.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_directory(item, target)
        else:
            target.write_bytes(item.read_bytes())


def _copy_resource_directory(source: resources.abc.Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_resource_directory(item, target)
        else:
            target.write_bytes(item.read_bytes())


def create_project_from_template(destination: Path, *, force: bool = False) -> Path:
    destination = Path(destination)
    if destination.exists() and not destination.is_dir():
        raise TemplateError("destination exists and is not a directory")
    if destination.exists() and force:
        shutil.rmtree(destination)
    elif destination.exists() and any(destination.iterdir()):
        raise TemplateError("destination already exists and is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    _copy_template_tree(destination)
    return destination
```

- [ ] **Step 5: Run project template tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_package.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/package.py src/hermes_workflow/templates/spectre_maestro_project tests/test_package.py
git commit -m "feat: add hermes project template"
```

### Task 5: Execution Package Manifest Builder

**Files:**
- Modify: `ic-auto-opt-workflow/src/hermes_workflow/package.py`
- Modify: `ic-auto-opt-workflow/tests/test_package.py`

- [ ] **Step 1: Add failing manifest builder test**

Append to `ic-auto-opt-workflow/tests/test_package.py`:

```python
import json
from hashlib import sha256

from hermes_workflow.package import build_execution_package


def test_build_execution_package_copies_config_and_records_hashes(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    manifest = build_execution_package(
        project_dir,
        created_at_utc="2026-05-28T00:00:00Z",
    )

    manifest_path = project_dir / "execution_package" / "execution_manifest.json"
    copied_config = project_dir / "execution_package" / "config" / "variables.yaml"
    source_config = project_dir / "config" / "variables.yaml"
    expected_hash = sha256(source_config.read_bytes()).hexdigest()
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest.path == manifest_path
    assert copied_config.read_text(encoding="utf-8") == source_config.read_text(encoding="utf-8")
    assert manifest_payload["schema_version"] == "1.0"
    assert manifest_payload["project_name"] == "bridge_test_inv"
    assert manifest_payload["created_at_utc"] == "2026-05-28T00:00:00Z"
    assert manifest_payload["immutable_config_files"]["config/variables.yaml"] == expected_hash
```

- [ ] **Step 2: Run the manifest test to verify it fails**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_package.py::test_build_execution_package_copies_config_and_records_hashes -v
```

Expected: FAIL with `ImportError` for `build_execution_package`.

- [ ] **Step 3: Implement execution package manifest builder**

Preserve the Task 4 template-copy implementation in `ic-auto-opt-workflow/src/hermes_workflow/package.py` exactly as written, including `importlib.resources`, packaged template discovery, file-destination `TemplateError`, and clean `force=True` regeneration.

Add these imports near the existing imports:

```python
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from hermes_workflow.validate import assert_valid_project
```

Then append these Task 5 constants and functions below the existing `create_project_from_template()` implementation:

```python

CONFIG_FILE_NAMES = [
    "project_config.yaml",
    "variables.yaml",
    "metrics.yaml",
    "spectre.yaml",
    "optimizer.yaml",
]


@dataclass(frozen=True)
class ExecutionManifest:
    path: Path
    payload: dict


def sha256_file(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def build_execution_package(project_dir: Path, *, created_at_utc: str | None = None) -> ExecutionManifest:
    project_dir = Path(project_dir)
    bundle = assert_valid_project(project_dir)
    execution_dir = project_dir / "execution_package"
    config_destination = execution_dir / "config"
    execution_dir.mkdir(parents=True, exist_ok=True)
    config_destination.mkdir(parents=True, exist_ok=True)

    immutable_hashes: dict[str, str] = {}
    for file_name in CONFIG_FILE_NAMES:
        source = project_dir / "config" / file_name
        destination = config_destination / file_name
        shutil.copy2(source, destination)
        immutable_hashes[f"config/{file_name}"] = sha256_file(source)

    created_at = created_at_utc or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": "1.0",
        "project_name": bundle.project_config.project.name,
        "created_at_utc": created_at,
        "source_project_dir": str(project_dir.resolve()),
        "immutable_config_files": immutable_hashes,
        "required_preflight_reports": [
            "reports/netlist_preparation_report.json",
            "reports/dry_run_report.json",
            "state/health_check.json",
        ],
    }
    manifest_path = execution_dir / "execution_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ExecutionManifest(path=manifest_path, payload=payload)
```

- [ ] **Step 4: Run package tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_package.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/package.py tests/test_package.py
git commit -m "feat: build execution package manifest"
```

### Task 6: `EXECUTION_TASK.md` Renderer

**Files:**
- Modify: `ic-auto-opt-workflow/src/hermes_workflow/package.py`
- Modify: `ic-auto-opt-workflow/tests/test_package.py`

- [ ] **Step 1: Add failing execution task rendering test**

Append to `ic-auto-opt-workflow/tests/test_package.py`:

```python
def test_build_execution_package_writes_execution_task(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)

    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")

    task_text = (project_dir / "execution_package" / "EXECUTION_TASK.md").read_text(encoding="utf-8")
    assert "# Claude Code Execution Task" in task_text
    assert "Project: `bridge_test_inv`" in task_text
    assert "Backend: `maestro_exported_spectre_deck`" in task_text
    assert "Spectre X preset: `ax`" in task_text
    assert "`FN`, `WN`, `FP`, `WP`" in task_text
    assert "Do not modify Maestro setup" in task_text
    assert "Wait for `supervisor_instruction.json` before the first real Spectre run" in task_text
```

- [ ] **Step 2: Run the execution task test to verify it fails**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_package.py::test_build_execution_package_writes_execution_task -v
```

Expected: FAIL because `EXECUTION_TASK.md` does not exist.

- [ ] **Step 3: Implement Markdown rendering**

Add this function to `ic-auto-opt-workflow/src/hermes_workflow/package.py`:

```python
def render_execution_task(project_dir: Path, manifest_payload: dict) -> str:
    bundle = assert_valid_project(project_dir)
    variable_names = ", ".join(f"`{variable.name}`" for variable in bundle.variables.variables)
    metric_lines = "\n".join(
        f"- `{metric.name}` [{metric.unit}]: `{metric.maestro_formula}`"
        for metric in bundle.metrics.metrics
    )
    constraint_lines = "\n".join(
        f"- `{constraint.metric}` {constraint.op.value} `{constraint.value}`"
        for constraint in bundle.metrics.constraints
    )
    hash_lines = "\n".join(
        f"- `{path}`: `{digest}`"
        for path, digest in sorted(manifest_payload["immutable_config_files"].items())
    )
    return f"""# Claude Code Execution Task

Project: `{bundle.project_config.project.name}`
Backend: `{bundle.project_config.project.backend}`
Created at UTC: `{manifest_payload["created_at_utc"]}`

## Scope

Use `virtuoso-bridge-lite` skills to prepare the project-local execution files. Do not run a real Spectre optimization before Hermes approval.

## Testbench

- Virtuoso library: `{bundle.project_config.testbench.virtuoso_library}`
- Cell: `{bundle.project_config.testbench.cell}`
- Design view: `{bundle.project_config.testbench.design_view}`
- Maestro view: `{bundle.project_config.testbench.maestro_view}`
- Test name: `{bundle.project_config.testbench.test_name}`
- Corner: `{bundle.project_config.testbench.corner}`

## Allowed Variables

Only template these variables in the exported Spectre deck: {variable_names}

## Metrics

{metric_lines}

## Constraints

{constraint_lines}

## Objective

- Direction: `{bundle.metrics.objective.direction.value}`
- Expression: `{bundle.metrics.objective.expression}`

## Spectre Policy

- Engine: `spectre_x`
- Spectre X preset: `{bundle.spectre.spectre.preset.value}`
- Output format: `{bundle.spectre.spectre.output_format}`
- Candidate-level parallel jobs: `{bundle.spectre.spectre.parallel_jobs}`
- Per-candidate timeout seconds: `{bundle.spectre.spectre.timeout_s}`

## Safety Rules

- Do not modify Maestro setup.
- Do not change analysis statements, model includes, simulator options, save options, constraints, objective, variable bounds, or variable step sizes.
- Template only approved variables.
- Write `reports/netlist_preparation_report.json`, `reports/dry_run_report.json`, `reports/review_report.md`, and `state/health_check.json`.
- Wait for `supervisor_instruction.json` before the first real Spectre run.

## Immutable Config Hashes

{hash_lines}
"""
```

Modify `build_execution_package` so it writes the rendered task before returning:

```python
    task_text = render_execution_task(project_dir, payload)
    (execution_dir / "EXECUTION_TASK.md").write_text(task_text, encoding="utf-8")
    return ExecutionManifest(path=manifest_path, payload=payload)
```

- [ ] **Step 4: Run package tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_package.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/package.py tests/test_package.py
git commit -m "feat: render claude execution task"
```

### Task 7: Claude Preflight Report Readers

**Files:**
- Create: `ic-auto-opt-workflow/src/hermes_workflow/reports.py`
- Create: `ic-auto-opt-workflow/tests/report_helpers.py`
- Create: `ic-auto-opt-workflow/tests/test_reports.py`

- [ ] **Step 1: Write failing report reader tests**

Create `ic-auto-opt-workflow/tests/report_helpers.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_pass_reports(project_dir: Path) -> None:
    write_json(
        project_dir / "reports" / "netlist_preparation_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "exported_input_scs": "netlists/exported/input.scs",
            "template_scs": "netlists/templates/template.scs",
            "approved_variables_template_status": {"FN": True, "WN": True, "FP": True, "WP": True},
            "analysis_statements": ["tran", "dc"],
            "forbidden_setup_changes_detected": False,
            "issues": [],
        },
    )
    write_json(
        project_dir / "reports" / "dry_run_report.json",
        {
            "schema_version": "1.0",
            "status": "pass",
            "rendered_candidate_scs": "runs/dry_run/input.scs",
            "placeholder_check": {
                "unresolved_placeholders": [],
                "unexpected_template_variables": [],
            },
            "metrics_import_ok": True,
            "mock_metrics_ok": True,
            "objective_ok": True,
            "constraints_ok": True,
            "ledger_write_ok": True,
            "state_write_ok": True,
            "issues": [],
        },
    )
    write_json(
        project_dir / "state" / "health_check.json",
        {
            "schema_version": "1.0",
            "status": "healthy",
            "real_run_started": False,
            "current_evaluations": 0,
            "best_candidate_path": None,
            "last_batch_id": None,
            "issues": [],
        },
    )
```

Create `ic-auto-opt-workflow/tests/test_reports.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.reports import load_preflight_reports
from tests.report_helpers import write_json, write_pass_reports


def test_load_preflight_reports_accepts_pass_reports(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    write_pass_reports(project_dir)

    reports = load_preflight_reports(project_dir)

    assert reports.ready is True
    assert reports.messages == []


def test_load_preflight_reports_rejects_failed_dry_run(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    write_pass_reports(project_dir)
    dry_run_path = project_dir / "reports" / "dry_run_report.json"
    payload = json.loads(dry_run_path.read_text(encoding="utf-8"))
    payload["status"] = "fail"
    payload["issues"] = ["objective evaluation failed"]
    write_json(dry_run_path, payload)

    reports = load_preflight_reports(project_dir)

    assert reports.ready is False
    assert "dry run status is fail" in reports.messages
    assert "objective evaluation failed" in reports.messages
```

- [ ] **Step 2: Run report tests to verify they fail**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_reports.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.reports'`.

- [ ] **Step 3: Implement report readers**

Create `ic-auto-opt-workflow/src/hermes_workflow/reports.py`:

```python
from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class StrictReport(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PassFail(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


class NetlistPreparationReport(StrictReport):
    schema_version: str
    status: PassFail
    exported_input_scs: str
    template_scs: str
    approved_variables_template_status: dict[str, bool]
    analysis_statements: list[str]
    forbidden_setup_changes_detected: bool
    issues: list[str] = Field(default_factory=list)


class PlaceholderCheck(StrictReport):
    unresolved_placeholders: list[str] = Field(default_factory=list)
    unexpected_template_variables: list[str] = Field(default_factory=list)


class DryRunReport(StrictReport):
    schema_version: str
    status: PassFail
    rendered_candidate_scs: str
    placeholder_check: PlaceholderCheck
    metrics_import_ok: bool
    mock_metrics_ok: bool
    objective_ok: bool
    constraints_ok: bool
    ledger_write_ok: bool
    state_write_ok: bool
    issues: list[str] = Field(default_factory=list)


class HealthCheck(StrictReport):
    schema_version: str
    status: HealthStatus
    real_run_started: bool
    current_evaluations: int = Field(ge=0)
    best_candidate_path: str | None
    last_batch_id: int | None
    issues: list[str] = Field(default_factory=list)


class PreflightReports(BaseModel):
    netlist_preparation: NetlistPreparationReport
    dry_run: DryRunReport
    health_check: HealthCheck
    messages: list[str] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.messages


def load_preflight_reports(project_dir: Path) -> PreflightReports:
    project_dir = Path(project_dir)
    netlist = _load_json_model(
        project_dir / "reports" / "netlist_preparation_report.json",
        NetlistPreparationReport,
    )
    dry_run = _load_json_model(project_dir / "reports" / "dry_run_report.json", DryRunReport)
    health = _load_json_model(project_dir / "state" / "health_check.json", HealthCheck)

    messages: list[str] = []
    if netlist.status != PassFail.PASS:
        messages.append(f"netlist preparation status is {netlist.status.value}")
    if netlist.forbidden_setup_changes_detected:
        messages.append("netlist preparation detected forbidden setup changes")
    for variable, templated in sorted(netlist.approved_variables_template_status.items()):
        if not templated:
            messages.append(f"approved variable {variable} was not templated")
    messages.extend(netlist.issues)

    if dry_run.status != PassFail.PASS:
        messages.append(f"dry run status is {dry_run.status.value}")
    if dry_run.placeholder_check.unresolved_placeholders:
        messages.append("dry run has unresolved placeholders")
    if dry_run.placeholder_check.unexpected_template_variables:
        messages.append("dry run has unexpected template variables")
    for field_name in [
        "metrics_import_ok",
        "mock_metrics_ok",
        "objective_ok",
        "constraints_ok",
        "ledger_write_ok",
        "state_write_ok",
    ]:
        if not getattr(dry_run, field_name):
            messages.append(f"dry run check failed: {field_name}")
    messages.extend(dry_run.issues)

    if health.status != HealthStatus.HEALTHY:
        messages.append(f"health status is {health.status.value}")
    if health.real_run_started:
        messages.append("real run already started before approval")
    messages.extend(health.issues)

    return PreflightReports(
        netlist_preparation=netlist,
        dry_run=dry_run,
        health_check=health,
        messages=messages,
    )


def _load_json_model(path: Path, model_type: type[StrictReport]) -> StrictReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return model_type.model_validate(payload)
```

- [ ] **Step 4: Run report tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_reports.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/reports.py tests/report_helpers.py tests/test_reports.py
git commit -m "feat: read claude preflight reports"
```

### Task 8: Hermes First-Run Approval Gate

**Files:**
- Create: `ic-auto-opt-workflow/src/hermes_workflow/approvals.py`
- Create: `ic-auto-opt-workflow/tests/test_approvals.py`

- [ ] **Step 1: Write failing approval tests**

Create `ic-auto-opt-workflow/tests/test_approvals.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from tests.report_helpers import write_pass_reports, write_json


def test_approval_gate_writes_approve_instruction(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")
    write_pass_reports(project_dir)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    instruction_path = project_dir / "supervisor_instruction.json"
    payload = json.loads(instruction_path.read_text(encoding="utf-8"))
    assert instruction["decision"] == "approve_first_real_run"
    assert payload["decision"] == "approve_first_real_run"
    assert "run_standalone_spectre_optimizer" in payload["allowed_actions"]
    assert payload["approved_config_hashes"]["config/project_config.yaml"]


def test_approval_gate_writes_reject_instruction_when_preflight_fails(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    create_project_from_template(project_dir)
    build_execution_package(project_dir, created_at_utc="2026-05-28T00:00:00Z")
    write_pass_reports(project_dir)
    dry_run_path = project_dir / "reports" / "dry_run_report.json"
    dry_run_payload = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run_payload["status"] = "fail"
    dry_run_payload["issues"] = ["mock metric failed"]
    write_json(dry_run_path, dry_run_payload)

    instruction = decide_first_real_run(
        project_dir,
        created_at_utc="2026-05-28T00:10:00Z",
    )

    assert instruction["decision"] == "reject_first_real_run"
    assert "dry run status is fail" in instruction["reason"]
    assert "mock metric failed" in instruction["reason"]
```

- [ ] **Step 2: Run approval tests to verify they fail**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_approvals.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_workflow.approvals'`.

- [ ] **Step 3: Implement approval gate**

Create `ic-auto-opt-workflow/src/hermes_workflow/approvals.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from hermes_workflow.reports import load_preflight_reports
from hermes_workflow.validate import validate_project_files


def decide_first_real_run(project_dir: Path, *, created_at_utc: str | None = None) -> dict:
    project_dir = Path(project_dir)
    created_at = created_at_utc or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    validation_report = validate_project_files(project_dir)
    manifest_path = project_dir / "execution_package" / "execution_manifest.json"

    if not manifest_path.exists():
        instruction = _reject(created_at, "execution manifest is missing", {})
        return _write_instruction(project_dir, instruction)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    approved_hashes = manifest["immutable_config_files"]

    if not validation_report.ok:
        instruction = _reject(created_at, validation_report.format(), approved_hashes)
        return _write_instruction(project_dir, instruction)

    preflight = load_preflight_reports(project_dir)
    if not preflight.ready:
        instruction = _reject(created_at, "; ".join(preflight.messages), approved_hashes)
        return _write_instruction(project_dir, instruction)

    instruction = {
        "schema_version": "1.0",
        "created_at_utc": created_at,
        "decision": "approve_first_real_run",
        "reason": "config validation and Claude preflight reports passed",
        "allowed_actions": ["run_standalone_spectre_optimizer"],
        "forbidden_actions": [
            "modify_maestro_setup",
            "modify_immutable_config_files",
            "change_variable_bounds",
            "change_objective_or_constraints",
        ],
        "approved_config_hashes": approved_hashes,
    }
    return _write_instruction(project_dir, instruction)


def _reject(created_at_utc: str, reason: str, approved_hashes: dict[str, str]) -> dict:
    return {
        "schema_version": "1.0",
        "created_at_utc": created_at_utc,
        "decision": "reject_first_real_run",
        "reason": reason,
        "allowed_actions": ["write_escalation_report", "revise_execution_package_after_hermes_instruction"],
        "forbidden_actions": ["run_standalone_spectre_optimizer"],
        "approved_config_hashes": approved_hashes,
    }


def _write_instruction(project_dir: Path, instruction: dict) -> dict:
    path = Path(project_dir) / "supervisor_instruction.json"
    path.write_text(json.dumps(instruction, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return instruction
```

- [ ] **Step 4: Run approval tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_approvals.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/approvals.py tests/test_approvals.py
git commit -m "feat: add hermes first-run approval gate"
```

### Task 9: CLI Contract Smoke Tests

**Files:**
- Modify: `ic-auto-opt-workflow/src/hermes_workflow/cli.py`
- Modify: `ic-auto-opt-workflow/tests/test_cli.py`
- Modify: `ic-auto-opt-workflow/README.md`

- [ ] **Step 1: Add failing CLI command tests**

Append to `ic-auto-opt-workflow/tests/test_cli.py`:

```python
import json
from pathlib import Path

from tests.report_helpers import write_pass_reports


def test_cli_init_and_validate(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"

    init_result = runner.invoke(app, ["init", str(project_dir)])
    validate_result = runner.invoke(app, ["validate", str(project_dir)])

    assert init_result.exit_code == 0
    assert validate_result.exit_code == 0
    assert "validation passed" in validate_result.stdout


def test_cli_package_and_approve(tmp_path: Path) -> None:
    project_dir = tmp_path / "bridge_test_inv"
    runner.invoke(app, ["init", str(project_dir)])
    package_result = runner.invoke(app, ["package", str(project_dir)])
    write_pass_reports(project_dir)
    approve_result = runner.invoke(app, ["approve", str(project_dir)])

    instruction = json.loads((project_dir / "supervisor_instruction.json").read_text(encoding="utf-8"))
    assert package_result.exit_code == 0
    assert "execution_package/execution_manifest.json" in package_result.stdout
    assert approve_result.exit_code == 0
    assert instruction["decision"] == "approve_first_real_run"
```

- [ ] **Step 2: Run CLI command tests to verify they fail**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_cli.py -v
```

Expected: FAIL because the `init`, `validate`, `package`, and `approve` commands are not registered.

- [ ] **Step 3: Implement CLI command wiring**

Replace `ic-auto-opt-workflow/src/hermes_workflow/cli.py` with:

```python
from pathlib import Path
from typing import Annotated

import typer

from hermes_workflow import __version__
from hermes_workflow.approvals import decide_first_real_run
from hermes_workflow.package import build_execution_package, create_project_from_template
from hermes_workflow.validate import validate_project_files


app = typer.Typer(help="Hermes file-contract workflow tools.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the package version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    return None


@app.command("init")
def init_command(
    destination: Annotated[Path, typer.Argument(help="Project directory to create.")],
    force: Annotated[bool, typer.Option("--force", help="Overwrite files inside an existing project directory.")] = False,
) -> None:
    project_dir = create_project_from_template(destination, force=force)
    typer.echo(str(project_dir))


@app.command("validate")
def validate_command(project_dir: Annotated[Path, typer.Argument(help="Project directory containing config/*.yaml.")]) -> None:
    report = validate_project_files(project_dir)
    typer.echo(report.format())
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("package")
def package_command(project_dir: Annotated[Path, typer.Argument(help="Project directory to package for Claude Code.")]) -> None:
    manifest = build_execution_package(project_dir)
    typer.echo(str(manifest.path.relative_to(project_dir)))


@app.command("approve")
def approve_command(project_dir: Annotated[Path, typer.Argument(help="Project directory with Claude preflight reports.")]) -> None:
    instruction = decide_first_real_run(project_dir)
    typer.echo(instruction["decision"])
    if instruction["decision"] != "approve_first_real_run":
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Update README with CLI usage**

Append to `ic-auto-opt-workflow/README.md`:

````markdown

## MVP CLI

```bash
hermes-workflow init projects/bridge_test_inv
hermes-workflow validate projects/bridge_test_inv
hermes-workflow package projects/bridge_test_inv
hermes-workflow approve projects/bridge_test_inv
```

The `approve` command only approves the first real run when config validation, netlist preparation report, dry-run report, and health check all pass.
````

- [ ] **Step 5: Run CLI tests to verify they pass**

Run:

```bash
cd ic-auto-opt-workflow
pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Run all tests**

Run:

```bash
cd ic-auto-opt-workflow
pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Run lint**

Run:

```bash
cd ic-auto-opt-workflow
ruff check .
```

Expected: exit code 0.

- [ ] **Step 8: Commit**

Run:

```bash
cd ic-auto-opt-workflow
git add src/hermes_workflow/cli.py tests/test_cli.py README.md
git commit -m "feat: add hermes workflow cli commands"
```

## Final Verification

After Task 9, run:

```bash
cd ic-auto-opt-workflow
pytest -q
ruff check .
```

Expected: all tests pass and Ruff reports no issues.

## Self-Review

- Spec coverage: Plan A covers structured YAML schema validation, cross-file rules, template generation, execution package manifest, `EXECUTION_TASK.md`, preflight report readers, approval gate, and CLI smoke coverage. It excludes `USER_TASK.md` parsing, Claude CLI, Virtuoso, Spectre, and optimizer execution as confirmed.
- Placeholder scan: The plan contains concrete file paths, concrete YAML shapes, concrete test code, concrete implementation code, exact commands, and expected outcomes.
- Type consistency: The APIs used across tasks are consistent: `create_project_from_template`, `build_execution_package`, `render_execution_task`, `validate_project_files`, `assert_valid_project`, `load_preflight_reports`, and `decide_first_real_run`.
