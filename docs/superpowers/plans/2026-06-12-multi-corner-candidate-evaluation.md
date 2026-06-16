# C-76 Multi-Corner Candidate Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. The implementation and review subagents must use model
> `5.3-codex-spark`. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Goal:** Add process-corner evaluation as an optional axis inside the
> existing candidate evaluation model without adding a new CLI mode.
>
> **Architecture:** Keep `ic-opt PROJECT --real` as the only real-run command.
> Requirement intake detects optional corner configuration, generates
> corner-aware contracts, and candidate evaluation serially runs
> testbench-by-corner child simulations inside each candidate. OpenBox
> concurrency remains candidate-level only.
>
> **Tech Stack:** Python 3.10+, Typer CLI, OpenBox backend, existing
> Spectre/OCEAN local and remote adapters, pytest, ruff.

## Source Design

Use this spec as authority:

```text
docs/superpowers/specs/2026-06-12-multi-corner-candidate-evaluation-design.md
```

## Hard Constraints

- Do not add `--multi-corner`.
- Do not change the meaning of `parallel_jobs`.
- Do not add inner testbench/corner parallelism.
- Do not require live Virtuoso/Maestro during optimizer execution.
- Do not rewrite OCEAN formulas.
- Do not introduce Monte Carlo support in this task.
- Preserve existing single-corner and multi-testbench behavior.
- Keep remote Spectre/OCEAN behavior local-parity only.

## Task 1: Requirement Parsing And Schema

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/requirement_intake.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/schemas.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_requirement_intake.py`

**Step 1: Write failing tests for missing corner section compatibility**

Add a test that parses an existing single-corner fixture without
`Process Corners` and asserts generated config semantics include exactly one
implicit corner:

```python
assert corner_config.corners[0].id == "nominal"
assert corner_config.objective_policy == "nominal"
assert corner_config.constraint_policy == "nominal"
```

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_requirement_intake.py -q
```

Expected: FAIL until schema/parser exists.

**Step 2: Write failing tests for explicit corners**

Add a fixture-style requirement with:

```yaml
Process Corners:
  objective_policy: worst_case
  constraint_policy: all_corners
  corners:
    - id: tt
      model_section: Post_simu_top_tt
      variables:
        temperature: "27"
    - id: ss
      model_section: Post_simu_top_ss
      variables:
        temperature: "125"
```

Assert parsed fields preserve IDs, policies, section names, and variables.

**Step 3: Implement minimal schema and parser**

Add dataclasses/Pydantic models consistent with existing schema style:

```text
ProcessCorner
ProcessCornerConfig
```

Validation:

- `id` required.
- `id` must be path-safe.
- `objective_policy` in `{nominal, worst_case}`.
- `constraint_policy` in `{nominal, all_corners}`.
- empty corner list is invalid.
- missing `Process Corners` creates implicit nominal config.

**Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_requirement_intake.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/src/hermes_workflow/requirement_intake.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/schemas.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md ic-auto-opt-workflow-v0.1/tests/test_requirement_intake.py
rtk git commit -m "feat: parse process corner requirements"
```

## Task 2: Corner-Aware Netlist Templates

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/netlists.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_netlists.py`
- Add if needed: `ic-auto-opt-workflow-v0.1/tests/fixtures/requirement_intake/multi_corner_project/`

**Step 1: Write failing test for corner template generation**

Create a minimal Spectre input containing:

```spectre
include "/path/to/toplevel.scs" section=Post_simu_top_tt
parameters temperature=27 F=20 W=1.8u
```

Assert two corner templates are generated:

```text
netlists/testbenches/<tb_id>/corners/tt/template.scs
netlists/testbenches/<tb_id>/corners/ss/template.scs
```

The `ss` template must contain:

```spectre
section=Post_simu_top_ss
```

and preserve unrelated lines.

**Step 2: Write failing test for safe replacement**

Assert replacement only affects the model include section, not comments or
OCEAN expressions.

**Step 3: Implement minimal netlist transformation**

Use a focused parser/rewrite helper:

```text
render_corner_netlist_template(source_text, corner_config, base_corner)
```

Rules:

- replace only Spectre `include ... section=...` model line;
- support optional `model_file`;
- update variables by reusing existing parameter rendering where possible;
- raise structured issue if `model_section` is requested but no model include
  section can be found.

**Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_netlists.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/src/hermes_workflow/netlists.py ic-auto-opt-workflow-v0.1/tests/test_netlists.py ic-auto-opt-workflow-v0.1/tests/fixtures/requirement_intake/multi_corner_project
rtk git commit -m "feat: generate corner-aware netlist templates"
```

## Task 3: Candidate Run Context Matrix

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/real_run.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_spectre_ocean_adapter.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_remote_spectre_ocean.py`

**Step 1: Write failing local adapter test**

Assert `run_spectre_ocean_adapter(..., testbench_id="cg_nf", corner_id="ss")`
loads the corner-specific template and writes artifacts under a corner-aware
child path.

Expected path shape:

```text
runs/real/<run_id>/testbenches/<testbench_id>/corners/<corner_id>/
```

**Step 2: Write failing remote adapter test**

Assert remote adapter receives and mirrors the same `testbench_id` and
`corner_id` path shape.

**Step 3: Implement `corner_id` context support**

Extend the existing adapter context loader to accept optional `corner_id`.

Rules:

- when no corner is configured, existing paths remain backward-compatible;
- when corner is configured, use corner-aware child paths;
- result manifests must include `testbench_id` and `corner_id`.

**Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_spectre_ocean_adapter.py ic-auto-opt-workflow-v0.1/tests/test_remote_spectre_ocean.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/src/hermes_workflow/real_run.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/execution_adapters/spectre_ocean.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/execution_adapters/remote_spectre_ocean.py ic-auto-opt-workflow-v0.1/tests/test_spectre_ocean_adapter.py ic-auto-opt-workflow-v0.1/tests/test_remote_spectre_ocean.py
rtk git commit -m "feat: add corner-aware run contexts"
```

## Task 4: Serial Testbench-By-Corner Execution

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/native_turbo.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_native_turbo.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_remote_optimizer_flow.py`

**Step 1: Write failing serial-order test**

For a project with two testbenches and three corners, use a fake adapter that
records calls.

Assert exact order:

```text
tb1/tt
tb1/ff
tb1/ss
tb2/tt
tb2/ff
tb2/ss
```

Assert no inner executor is created.

**Step 2: Write failing parallel invariant test**

For `batch_size=4`, `parallel_jobs=2`, two testbenches, three corners:

- at most two candidates may be active concurrently;
- within one candidate, child calls are serial.

**Step 3: Implement serial corner loop**

Extend existing multi-testbench loops:

```python
for testbench in testbenches:
    for corner in corners:
        run_adapter(testbench_id=testbench.id, corner_id=corner.id)
```

Do not add new `ThreadPoolExecutor` or `asyncio` logic.

**Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_native_turbo.py ic-auto-opt-workflow-v0.1/tests/test_remote_optimizer_flow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/src/hermes_workflow/native_turbo.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/execution_adapters/remote_spectre_ocean.py ic-auto-opt-workflow-v0.1/tests/test_native_turbo.py ic-auto-opt-workflow-v0.1/tests/test_remote_optimizer_flow.py
rtk git commit -m "feat: evaluate corners serially within candidates"
```

## Task 5: Corner Aggregation And Status Semantics

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/multi_testbench_aggregation.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/native_turbo.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_multi_testbench_aggregation.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_openbox_backend.py`

**Step 1: Write failing aggregation tests**

Cases:

1. all child runs pass -> aggregate `feasible`;
2. one corner has tool failure -> aggregate `real_check_failed`;
3. one corner has missing scalar -> aggregate `metric_check_failed`;
4. one corner violates constraint under `all_corners` -> aggregate
   `constraint_failed`;
5. nominal passes and non-nominal fails under `nominal` policy -> aggregate
   follows nominal only.

**Step 2: Write failing worst-case objective test**

For minimized internal objective values:

```text
tt = 1.0
ff = 2.5
ss = 1.5
```

Assert `worst_case` aggregate objective is `2.5`.

**Step 3: Implement aggregation policy**

Add explicit fields to aggregate report:

```text
constraint_policy
objective_policy
worst_corner
corner_objectives
corner_status_counts
```

Do not change ledger row status names.

**Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_multi_testbench_aggregation.py ic-auto-opt-workflow-v0.1/tests/test_openbox_backend.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/src/hermes_workflow/multi_testbench_aggregation.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/native_turbo.py ic-auto-opt-workflow-v0.1/tests/test_multi_testbench_aggregation.py ic-auto-opt-workflow-v0.1/tests/test_openbox_backend.py
rtk git commit -m "feat: aggregate multi-corner candidate results"
```

## Task 6: Reports And Visuals

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/optimizer_insights.py`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/optimizer_decision.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_optimizer_insights.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_optimizer_decision.py`

**Step 1: Write failing report tests**

Create synthetic traces with two corners.

Assert `optimizer_insight_report.md` contains:

- corner policy summary;
- best candidate per-corner metric table;
- worst corner label;
- failure distribution by corner.

**Step 2: Write failing decision report test**

Assert recommended candidate basis states:

```text
best observed feasible candidate under worst_case corner objective
```

**Step 3: Implement report sections**

Add concise sections:

```text
Process Corner Summary
Best Candidate Corner Metrics
Corner Failure Distribution
Worst-Case Objective Basis
```

Do not remove existing plots.

**Step 4: Run targeted tests**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest ic-auto-opt-workflow-v0.1/tests/test_optimizer_insights.py ic-auto-opt-workflow-v0.1/tests/test_optimizer_decision.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/src/hermes_workflow/optimizer_insights.py ic-auto-opt-workflow-v0.1/src/hermes_workflow/optimizer_decision.py ic-auto-opt-workflow-v0.1/tests/test_optimizer_insights.py ic-auto-opt-workflow-v0.1/tests/test_optimizer_decision.py
rtk git commit -m "feat: report multi-corner optimization results"
```

## Task 7: Documentation And Agent Skill

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/README.md`
- Modify: `ic-auto-opt-workflow-v0.1/docs/USER_GUIDE_CN.md`
- Modify: `ic-auto-opt-workflow-v0.1/docs/TROUBLESHOOTING_CN.md`
- Modify: `ic-auto-opt-workflow-v0.1/skills/ic-opt/SKILL.md`
- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md`
- Add: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_corner.md`
- Add: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_tb_corner.md`

**Step 1: Update user docs**

Document:

- no new CLI mode;
- `Process Corners` is optional;
- users must provide full PDK section names;
- `parallel_jobs` remains candidate-level;
- multi-corner increases total simulation count, not simultaneous Spectre
  count;
- Monte Carlo remains post-optimization/future work.

**Step 2: Update agent skill**

Instruct agents:

- run `ic-opt PROJECT --doctor` first;
- inspect `structured_issues`;
- do not invent corner names;
- ask user for exact model section names if missing;
- do not add `--multi-corner`;
- explain worst-case vs nominal objective policy.

**Step 3: Add templates**

Add one multi-corner example and one multi-testbench + multi-corner example.

**Step 4: Validate docs have no local private paths**

Run:

```bash
rtk proxy rg -n "/home/zzchen|10\\.113\\.216|remote_opt|IC-OPT-test" ic-auto-opt-workflow-v0.1/README.md ic-auto-opt-workflow-v0.1/docs ic-auto-opt-workflow-v0.1/skills ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates
```

Expected: no private path hits.

- [ ] **Step 5: Commit**

```bash
rtk git add ic-auto-opt-workflow-v0.1/README.md ic-auto-opt-workflow-v0.1/docs/USER_GUIDE_CN.md ic-auto-opt-workflow-v0.1/docs/TROUBLESHOOTING_CN.md ic-auto-opt-workflow-v0.1/skills/ic-opt/SKILL.md ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project
rtk git commit -m "docs: explain multi-corner optimization"
```

## Task 8: Full Validation And Review

**Files:**

- Review all changed files from Tasks 1-7.

**Step 1: Run targeted multi-corner suite**

Run:

```bash
rtk proxy ./.venv/bin/python -m pytest \
  ic-auto-opt-workflow-v0.1/tests/test_requirement_intake.py \
  ic-auto-opt-workflow-v0.1/tests/test_netlists.py \
  ic-auto-opt-workflow-v0.1/tests/test_spectre_ocean_adapter.py \
  ic-auto-opt-workflow-v0.1/tests/test_remote_spectre_ocean.py \
  ic-auto-opt-workflow-v0.1/tests/test_multi_testbench_aggregation.py \
  ic-auto-opt-workflow-v0.1/tests/test_optimizer_insights.py \
  -q
```

Expected: PASS.

**Step 2: Run full test suite**

Run:

```bash
cd ic-auto-opt-workflow-v0.1
rtk proxy ./.venv/bin/python -m pytest -q
```

Expected: PASS.

**Step 3: Run ruff**

Run:

```bash
cd ic-auto-opt-workflow-v0.1
rtk proxy ./.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
```

Expected: PASS.

**Step 4: Run whitespace check**

Run:

```bash
cd ic-auto-opt-workflow-v0.1
rtk git diff --check
```

Expected: clean.

**Step 5: Subagent review**

Dispatch code-quality review subagent using model `5.3-codex-spark`.

Required review findings:

- confirm no new CLI mode;
- confirm no inner testbench/corner parallelism;
- confirm remote local-parity;
- confirm no OCEAN formula rewrite;
- confirm backward compatibility for no-corner projects;
- confirm report/decision behavior for no feasible candidates.

Fix all review findings before handing back.

- [ ] **Step 6: Final commit**

If review caused fixes:

```bash
rtk git add ic-auto-opt-workflow-v0.1
rtk git commit -m "fix: address multi-corner review findings"
```

## Claude Dispatch Prompt

Use this prompt when handing implementation to Claude:

```text
You are implementing C-76 Multi-Corner Candidate Evaluation.

Repository root:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT

Implementation target:
ic-auto-opt-workflow-v0.1

Spec:
ic-auto-opt-workflow/docs/superpowers/specs/2026-06-12-multi-corner-candidate-evaluation-design.md

Plan:
ic-auto-opt-workflow/docs/superpowers/plans/2026-06-12-multi-corner-candidate-evaluation.md

Required process:
- Use superpowers:subagent-driven-development.
- Use 5.3-codex-spark for coding and review subagents.
- Implement task by task.
- Each task must start with failing tests, then minimal implementation, then targeted tests.
- Run strict code-quality review before final handoff.
- Do not use 5.5 as coding/review subagent.

Hard constraints:
- Do not add --multi-corner.
- Do not change parallel_jobs semantics.
- Do not add inner testbench/corner parallelism.
- Do not require live Virtuoso/Maestro.
- Do not rewrite OCEAN formulas.
- Do not implement Monte Carlo.
- Preserve single-corner and existing multi-testbench behavior.
- Remote Spectre/OCEAN must remain local-parity.

Final handoff must include:
- commits made;
- files changed;
- tests run and results;
- review findings and fixes;
- explicit statement that all hard constraints pass.
```
