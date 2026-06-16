# C-73 Doctor Requirement Semantic Checks Implementation Plan

> **For coding agents:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development`. The implementation agent must
> perform its own spec review and code-quality review, fix review findings, and
> return only after targeted tests, full tests, lint, and diff checks pass.

**Goal:** make `ic-opt PROJECT --doctor` catch deterministic
`opt_requirement.md` semantic mistakes before real Spectre/OCEAN/OpenBox work
starts.

**Design authority:**

```text
docs/superpowers/specs/2026-06-12-doctor-requirement-semantic-checks-design.md
```

**Implementation target:** `ic-auto-opt-workflow-v0.1`.

**Hard boundary:** no optimizer behavior changes, no Spectre/OCEAN command
changes, no OpenBox backend changes, no requirement grammar redesign, no TUI,
no formula rewriting, and no new real simulation runs.

## Current Diagnosis

The product already supports a stable one-command flow, local and remote
Spectre/OCEAN execution, multi-testbench aggregation, continuation runs, and
post-run reports. The weak point is earlier: users and agents can still start
from an `opt_requirement.md` that is structurally valid but semantically wrong.

Examples:

- objective formula references `P1DB` while the metric is named `P1dB`;
- objective formula references a metric that is not declared;
- constraint references a missing metric;
- unsafe or unsupported objective expression reaches optimizer setup;
- variable bounds parse as YAML but are not meaningful numeric ranges;
- remote `parallel_jobs` is set too high and later stresses SSH.

C-73 moves these deterministic checks into doctor. Agents should explain doctor
output, not replace doctor with prompt judgement.

## Task 1: Add Failing Semantic Requirement Tests

**Purpose:** lock the desired doctor behavior before implementation.

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/tests/test_requirement_intake.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_remote_doctor.py`
- Modify if needed: `ic-auto-opt-workflow-v0.1/tests/test_product_cli_remote.py`

**Cases to add:**

1. Objective references an unknown metric and fails intake:

   ```text
   objective expression references unknown metric NF_3G
   ```

2. Objective references an unknown metric with a close declared name and reports
   a suggestion:

   ```text
   objective expression references unknown metric P1DB; did you mean P1dB?
   ```

3. Constraint references an unknown metric and fails intake.
4. Representative normalized FoM expression passes:

   ```text
   -(0.5*min(max(0,min(1,10*(ln(BW/28e9)/ln(10))/0.6)),max(0,min(1,(MAX_GAIN-5.5)/2)))+0.5*(0.1*max(0,min(1,10*(ln(BW/28e9)/ln(10))/0.6))+0.9*max(0,min(1,(MAX_GAIN-5.5)/2))))
   ```

5. Unsafe expressions fail without executing code:

   ```text
   eval("1")
   __import__("os").system("echo bad")
   BW.__class__
   ```

6. Unsupported function names fail:

   ```text
   unknown_func(BW)
   ```

7. Dummy evaluation catches invalid finite math such as:

   ```text
   BW / 0
   ```

8. Variable semantic errors fail:
   - lower > upper;
   - step <= 0;
   - unparsable numeric-like range where range checks are required.
9. Valid single-testbench and multi-testbench fixtures still pass.
10. Remote doctor includes a clear message for remote `parallel_jobs > 8`.

**Verification after adding tests, before implementation:** targeted tests must
fail for new cases.

## Task 2: Implement Safe Objective Expression Analyzer

**Purpose:** validate objective expressions deterministically without Python
`eval`.

**Files:**

- Prefer adding: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/requirement_semantics.py`
- Or narrowly modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/requirement_intake.py`
- Modify tests from Task 1.

**Required behavior:**

1. Parse objective expression with Python `ast.parse(..., mode="eval")`.
2. Allow only a narrow AST whitelist:
   - `Expression`
   - `BinOp`
   - `UnaryOp`
   - `Call`
   - `Name`
   - `Constant`
   - operator nodes for `+`, `-`, `*`, `/`, `**`, unary `+/-`
3. Reject:
   - `Attribute`
   - `Subscript`
   - `Lambda`
   - comprehensions
   - imports
   - assignment expressions
   - comparisons unless explicitly needed and tested
4. Allow only these function names initially:

   ```text
   min, max, abs, ln, log, log10, exp, sqrt, pow
   ```

5. Extract metric references from `Name` nodes after subtracting allowed
   function names.
6. Compare metric references against declared metric names.
7. If unknown metric has a close declared match, include the suggestion in the
   issue message.
8. Evaluate the expression with a custom safe evaluator over the AST, not with
   Python `eval`.
9. Dummy metric values must be finite positive numbers. Avoid zero values so
   normal division formulas do not fail accidentally.
10. Reject non-finite results and exceptions with actionable issue messages.

**Implementation note:** keep messages stable enough for tests, but do not
overfit to one exact paragraph. The user-facing message must name the failing
field and the unknown/unsafe symbol.

## Task 3: Implement Constraint And Variable Semantic Checks

**Purpose:** catch deterministic config mistakes that currently pass early
Markdown parsing.

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/requirement_intake.py`
- Modify or add helper module from Task 2.
- Modify tests from Task 1.

**Constraint checks:**

1. Every `Constraints[].metric` must exist in declared Metrics.
2. If a close metric match exists, include suggestion text.
3. Do not silently correct metric names.

**Variable checks:**

1. Variable names must be unique.
2. Variable names should not collide with metric names. This may be warning
   level if the current report model can carry warnings safely; otherwise make
   it an issue only if the collision would make objective parsing ambiguous.
3. Numeric-like `lower`, `upper`, and `step` values should support common SPICE
   suffixes:

   ```text
   f, p, n, u, m, k, meg, g
   ```

4. Validate:
   - lower <= upper;
   - step > 0 when present;
   - stepped range contains at least one value.
5. If a value cannot be parsed for range checks, report a clear issue. Do not
   invent conversion rules.

## Task 4: Wire Semantic Checks Into Requirement Intake And Product Doctor

**Purpose:** ensure the same semantic validation runs for local and remote
doctor paths.

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/requirement_intake.py`
- Modify if needed: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/remote_doctor.py`
- Modify tests from Task 1.

**Steps:**

1. Run semantic checks inside `parse_requirement_text()` after Markdown/YAML
   extraction and before returning `pass`.
2. Preserve existing `RequirementIntakeReport.status`, `issues`, and `sections`
   behavior.
3. If warnings are added, keep them backward-compatible. Do not break existing
   JSON consumers.
4. Ensure `prepare_from_requirement` and product-level doctor both benefit
   automatically because they already call the same parser.
5. Ensure remote doctor uses the same parser and reports the same semantic
   issues from remote requirement text.

## Task 5: Add Remote High-Parallel Doctor Warning

**Purpose:** surface a known SSH remote risk before long runs fail.

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/remote_doctor.py`
- Modify: `ic-auto-opt-workflow-v0.1/tests/test_remote_doctor.py`
- Modify if needed: `ic-auto-opt-workflow-v0.1/tests/test_product_cli_remote.py`

**Required behavior:**

For remote doctor only, when rendered Spectre settings contain
`parallel_jobs > 8`, include a clear non-fatal message:

```text
remote parallel_jobs=24 is high; normal remote multi-testbench runs should start around 4-8 to avoid SSH server limits
```

This should be warning-level if the report supports warnings. If the current
report cannot represent warnings without broad changes, add a non-fatal check
entry whose status does not fail doctor.

Do not add this warning to local doctor by default.

## Task 6: Update Agent Skill And User-Facing Docs

**Purpose:** make agents and human users use doctor correctly.

**Files:**

- Modify: `ic-auto-opt-workflow-v0.1/skills/ic-opt/SKILL.md`
- Sync same content to:
  `ic-auto-opt-workflow-v0.1/src/hermes_workflow/agent_skills/ic-opt/SKILL.md`
- Modify: `ic-auto-opt-workflow-v0.1/docs/USER_GUIDE_CN.md`
- Modify if present/relevant:
  `ic-auto-opt-workflow-v0.1/docs/TROUBLESHOOTING_CN.md`
- Modify if relevant:
  `ic-auto-opt-workflow-v0.1/src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md`

**Required doc/skill behavior:**

1. Fresh real run flow starts with doctor.
2. If doctor fails, do not run `--real`.
3. Agent should report exact doctor issue messages.
4. Agent should not rewrite formulas or OCEAN expressions unless the user asks.
5. If remote doctor warns about high `parallel_jobs`, recommend 4-8 for SSH
   remote runs.
6. Explain that doctor catches deterministic mistakes; engineering judgement
   still belongs to the user/agent after reports are generated.

## Task 7: Subagent Review, Fix Loop, And Final Verification

**Purpose:** keep implementation quality high without Codex doing coding work.

The coding subagent must run two explicit reviews before returning:

1. **Spec compliance review**
   - Check every C-73 acceptance criterion.
   - List PASS/FAIL for each criterion.
   - Fix any FAIL before handoff.
2. **Code quality review**
   - Check safe AST evaluation, no Python `eval`, no arbitrary code execution.
   - Check scope did not expand into optimizer/Spectre/OCEAN behavior.
   - Check report backward compatibility.
   - Check tests cover both local and remote doctor paths.
   - Fix any issue before handoff.

**Required verification commands:**

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest \
  tests/test_requirement_intake.py \
  tests/test_remote_doctor.py \
  tests/test_product_cli_remote.py \
  tests/test_agent_skill.py \
  -q
```

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q
```

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
```

```bash
rtk git -C ic-auto-opt-workflow-v0.1 diff --check
```

If the subagent uses a different Python path, it must state the exact path and
why.

## Final Acceptance By Codex

Codex final acceptance will check:

- only spec/doctor/skill/docs/tests changed;
- no optimizer search behavior changed;
- no Spectre/OCEAN argv or manifest behavior changed;
- semantic checks are deterministic and shared by local and remote doctor;
- unsafe objective expressions fail safely;
- valid normalized FoM expressions pass;
- remote high parallelism produces a clear warning/check;
- full test and lint evidence is present.

## Subagent Handoff Prompt

Use this prompt when assigning C-73 coding to Claude or another implementation
agent:

```text
You are implementing C-73 for ic-auto-opt-workflow.

REQUIRED: use superpowers:subagent-driven-development for the coding workflow.
You must perform your own spec review and code-quality review before returning.
Fix all review findings yourself.

Design authority:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/docs/superpowers/specs/2026-06-12-doctor-requirement-semantic-checks-design.md

Implementation plan:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/docs/superpowers/plans/2026-06-12-doctor-requirement-semantic-checks.md

Implementation target:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1

Hard boundaries:
- Do not change optimizer behavior.
- Do not change Spectre/OCEAN command behavior.
- Do not change OpenBox backend behavior.
- Do not redesign requirement grammar.
- Do not rewrite user formulas.
- Do not run real simulations.

Implement deterministic semantic checks in doctor:
- unknown objective metric references fail;
- close metric names produce suggestions, e.g. P1DB -> P1dB;
- unsafe objective expressions fail using safe AST evaluation, not eval;
- valid normalized FoM expressions pass dummy evaluation;
- unknown constraint metric references fail;
- variable range semantic errors fail;
- remote doctor warns/checks when parallel_jobs > 8.

Update agent/user docs so fresh real runs start with doctor and agents do not
run --real if doctor fails.

Required verification:
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_requirement_intake.py tests/test_remote_doctor.py tests/test_product_cli_remote.py tests/test_agent_skill.py -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
rtk git -C ic-auto-opt-workflow-v0.1 diff --check

Return:
- changed files;
- key design choices;
- test/lint results;
- spec compliance review summary;
- code quality review summary;
- commit hash if you commit.
```
