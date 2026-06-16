# C-74 Structured Errors And Readable Diagnostics Implementation Plan

> **For coding agents:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development`. The implementation agent must run
> its own spec review and code-quality review, fix findings, and return only
> after targeted tests, full tests, lint, and diff checks pass.

**Goal:** make product-facing errors structured and readable before adding any
new report-viewing command.

**Design authority:**

```text
docs/superpowers/specs/2026-06-12-structured-errors-readable-diagnostics-design.md
```

**Implementation target:** `ic-auto-opt-workflow-v0.1`.

**Hard boundary:** no optimizer search changes, no Spectre/OCEAN command
changes, no OpenBox changes, no report-view command, no TUI, no real
simulation, and no removal of legacy `issues: list[str]`.

## Current Diagnosis

C-73 made doctor much smarter, but the product still emits mostly opaque string
issues. This is workable for developers, but weak for:

- normal IC users trying to fix `opt_requirement.md`;
- agents deciding whether to stop, retry, ask the user, or continue;
- future report readers that should not need brittle string parsing.

C-74 adds a structured diagnostic layer while keeping all old strings.

## Task 1: Add Reusable Diagnostic Model And Helpers

**Purpose:** provide one small model that reports can reuse.

**Files:**

- Add: `ic-auto-opt-workflow-v0.1/src/hermes_workflow/diagnostics.py`
- Add tests if useful: `ic-auto-opt-workflow-v0.1/tests/test_diagnostics.py`

**Implementation:**

Add:

```python
class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"

class Diagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity
    stage: str
    component: str
    message: str
    detail: str | None = None
    likely_cause: str | None = None
    recommended_action: str | None = None
    evidence: list[str] = Field(default_factory=list)
```

Add helper functions:

- `diagnostic_to_issue(diagnostic) -> str`
- `format_diagnostics_for_cli(diagnostics, fallback_issues=None) -> list[str]`
- narrow factory helpers for high-frequency errors if it keeps callsites clean.

Do not over-engineer a large error framework.

## Task 2: Extend Requirement Intake Report Additively

**Purpose:** make C-73 doctor errors actionable without breaking old reports.

**Files:**

- Modify: `src/hermes_workflow/requirement_intake.py`
- Modify: `src/hermes_workflow/requirement_semantics.py`
- Modify: `tests/test_requirement_intake.py`

**Implementation options:**

Option A, preferred if clean:

- `validate_requirement_semantics()` returns structured diagnostics.
- `parse_requirement_text()` derives legacy `issues` from diagnostics plus
  existing non-semantic strings.

Option B, acceptable for narrow scope:

- Keep current string issues.
- Add a classifier that converts known C-73 strings into structured diagnostics.

Either option must produce:

```json
"issues": ["objective expression references unknown metric P1DB; did you mean P1dB?"],
"structured_issues": [
  {
    "code": "OBJECTIVE_UNKNOWN_METRIC",
    "severity": "error",
    "stage": "requirement",
    "component": "requirement_intake",
    "message": "...",
    "recommended_action": "..."
  }
]
```

**Required diagnostics:**

- `OBJECTIVE_UNKNOWN_METRIC`
- `OBJECTIVE_UNSAFE_EXPRESSION`
- `OBJECTIVE_UNSUPPORTED_FUNCTION`
- `CONSTRAINT_UNKNOWN_METRIC`
- `VARIABLE_RANGE_INVALID`
- `MAESTRO_INPUT_SCS_MISSING`

Keep `RequirementIntakeReport.status`, `issues`, and `sections` intact.

## Task 3: Extend Remote Doctor Report Additively

**Purpose:** make remote setup failures and warnings readable.

**Files:**

- Modify: `src/hermes_workflow/remote_doctor.py`
- Modify: `tests/test_remote_doctor.py`

**Implementation:**

Add `structured_issues` or `diagnostics` to remote doctor JSON. Prefer the name
`structured_issues` for consistency with requirement intake.

Include diagnostics for:

- `SSH_LOGIN_FAILED`
- `REMOTE_PROJECT_MISSING`
- `REMOTE_PROJECT_NOT_WRITABLE`
- `REMOTE_PARALLELISM_HIGH`
- `CADENCE_CSHRC_MISSING`
- `CADENCE_TOOL_MISSING`

`REMOTE_PARALLELISM_HIGH` must be severity `warn` and must not make doctor
status fail.

Do not change remote command execution behavior.

## Task 4: Improve Product CLI Failure Formatting

**Purpose:** show users concise structured errors instead of only raw strings.

**Files:**

- Modify: `src/hermes_workflow/product_cli.py`
- Modify or add tests:
  - `tests/test_product_cli.py`
  - `tests/test_product_cli_remote.py`

**Implementation:**

1. For local failures, if report object has structured diagnostics, print those
   with a compact block:

   ```text
   [ERROR] OBJECTIVE_UNKNOWN_METRIC
   Stage: requirement
   Message: Objective expression references unknown metric P1DB.
   Action: Change P1DB to P1dB, or rename the metric consistently.
   Evidence: opt_requirement.md:Objective.expression
   ```

2. For remote doctor, print warning diagnostics if status passes and warnings
   exist.
3. For exceptions caught by `_exit_with_error()`, wrap known product-level
   errors where feasible:
   - missing Cadence cshrc;
   - remote mode requires action;
   - remote doctor failed.
4. Preserve exit codes.

Do not add a report-view command.

## Task 5: Add Metric/Real-Run Check Structured Diagnostics Narrowly

**Purpose:** improve the most common post-run failure explanations without
rewriting all checker logic.

**Files:**

- Modify: `src/hermes_workflow/reports.py`
- Modify: `src/hermes_workflow/metric_results.py`
- Modify if low-risk: real-run check module that writes
  `reports/real_run_check_report.json`
- Modify related tests.

**Implementation:**

Add `structured_issues` to report models where they already expose `issues`.

Minimum mapping:

- `metric result manifest is invalid` -> `METRIC_MANIFEST_INVALID`
- `metric <name> did not succeed` -> `METRIC_NON_SCALAR` or
  `METRIC_CHECK_FAILED`, depending on available evidence;
- `metric <name> value is not finite` -> `METRIC_NON_FINITE`
- `metric artifact is missing: <path>` -> `SPECTRE_ARTIFACT_MISSING` or
  `OCEAN_SCALAR_MISSING`, depending on path.

If exact classification is ambiguous, use a broad but honest code:

```text
METRIC_CHECK_FAILED
```

Do not invent root cause beyond evidence.

## Task 6: Update Agent Skill And User Docs

**Purpose:** make agents consume the new structure correctly.

**Files:**

- Modify: `skills/ic-opt/SKILL.md`
- Sync: `src/hermes_workflow/agent_skills/ic-opt/SKILL.md`
- Modify: `docs/USER_GUIDE_CN.md`
- Modify if present: `docs/TROUBLESHOOTING_CN.md`

**Required text:**

- Agents should read `structured_issues` first.
- If absent, fall back to legacy `issues`.
- For each error, report code, stage, likely cause, action, evidence.
- Do not run `--real` when doctor emits error-severity diagnostics.
- Warning diagnostics do not necessarily block the run.
- Do not silently rewrite formulas or variables without user approval.

## Task 7: Subagent Review And Verification

The implementation subagent must perform:

1. **Spec compliance review**
   - every C-74 acceptance criterion PASS/FAIL;
   - all FAIL findings fixed before handoff.
2. **Code quality review**
   - additive report fields only;
   - backward compatibility preserved;
   - no optimizer/Spectre/OCEAN behavior drift;
   - no large error framework beyond current need;
   - tests cover CLI and JSON.

**Targeted verification:**

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest \
  tests/test_requirement_intake.py \
  tests/test_remote_doctor.py \
  tests/test_product_cli.py \
  tests/test_product_cli_remote.py \
  tests/test_agent_skill.py \
  -q
```

**Full verification:**

```bash
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
rtk git -C ic-auto-opt-workflow-v0.1 diff --check
```

## Final Acceptance By Codex

Codex will reject C-74 if:

- legacy `issues` is removed or renamed;
- existing report status semantics change;
- CLI exit codes change;
- optimizer/Spectre/OCEAN behavior changes;
- structured diagnostics are only strings hidden in another list;
- likely cause/action/evidence are missing for key doctor errors;
- tests only check implementation helpers and do not verify real report JSON.

## Subagent Handoff Prompt

Use this prompt when assigning C-74 coding to Claude or another implementation
agent:

```text
You are implementing C-74 for ic-auto-opt-workflow.

REQUIRED: use superpowers:subagent-driven-development. Perform implementation,
spec review, code-quality review, and fix all findings before returning.

Design authority:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/docs/superpowers/specs/2026-06-12-structured-errors-readable-diagnostics-design.md

Implementation plan:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow/docs/superpowers/plans/2026-06-12-structured-errors-readable-diagnostics.md

Implementation target:
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1

Hard boundaries:
- Do not add a report-view command.
- Do not add a TUI.
- Do not change optimizer behavior.
- Do not change Spectre/OCEAN command behavior.
- Do not change OpenBox behavior.
- Do not remove legacy issues.
- Do not run real simulations.

Goal:
Add additive structured diagnostics to product-facing reports and CLI output so
errors are easier for humans and agents to read. Keep backward compatibility.

Required verification:
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest tests/test_requirement_intake.py tests/test_remote_doctor.py tests/test_product_cli.py tests/test_product_cli_remote.py tests/test_agent_skill.py -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m pytest -q
rtk proxy ../ic-auto-opt-workflow/.venv/bin/python -m ruff check src tests tools --exclude tests/fixtures
rtk git -C ic-auto-opt-workflow-v0.1 diff --check

Return changed files, key design choices, exact verification output,
spec-compliance review, code-quality review, and commit hash if committed.
```
