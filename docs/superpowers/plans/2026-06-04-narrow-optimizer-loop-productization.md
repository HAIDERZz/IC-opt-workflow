# Narrow Optimizer Loop Productization Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` when implementation begins. This plan intentionally keeps task count small and favors real evidence over speculative framework work.

**Goal:** Productize the proven C-14 path into a minimal fixed-budget optimizer loop driver.

**Active spec:** `docs/superpowers/specs/2026-06-04-narrow-optimizer-loop-productization-design.md`

**Evidence base:** C-14 real-tool acceptance, committed in `003e969 docs: record C14 real tool acceptance`.

## Scope Guard

Allowed:

- Add one narrow loop driver.
- Reuse existing Hermes library functions or CLI-equivalent behavior.
- Invoke the existing C-7 adapter as the execution step.
- Add fake-adapter tests for contract behavior.
- Run one real-tool acceptance pass after fake tests pass.

Forbidden:

- Do not create a broad optimizer framework.
- Do not add a daemon, queue, scheduler, service, or parallel batch runner.
- Do not implement a new optimizer algorithm.
- Do not parse PSF data.
- Do not rewrite OCEAN formulas.
- Do not flatten or replace native Maestro/ADE netlist layout.
- Do not commit raw Cadence artifacts, protected sidecars, PSF/raw data, full logs, `docs/OCEAN_DOC_*`, or `docs/toolchain_evidence/`.

## Task 1: Loop ID Allocation And Fake Adapter Library Smoke

**Risk:** Medium. This touches orchestration logic but not real tools.

**Goal:** Add a small library function that can execute one candidate cycle with an injectable adapter runner.

Expected behavior:

- Determine the next candidate id and real-run id from project files.
- Call the existing suggestion and candidate-package contracts.
- Call an injected adapter runner for the prepared run.
- Run existing `check-real-run`, `check-metric-results`, and `record-real-result`.
- Return a compact structured report.
- Stop and report a clear state if adapter/check/record fails.

- [x] Tests:

- one fake successful cycle records a new ledger row;
- existing candidate or run ids are not overwritten;
- fake adapter failure stops before checks/record;
- fake metric check failure is reported without formula edits.

- [x] Verification:

```bash
python3 -m pytest tests/test_optimizer_loop.py -q
python3 -m pytest tests/test_optimizer_suggestion.py tests/test_candidate_injection_real_run.py -q
python3 -m ruff check src tests tools
```

## Task 2: Tool Entry Point

**Risk:** Medium. This adds an execution-side command wrapper.

**Goal:** Add `tools/run_real_optimizer_loop.py` for a small fixed-budget loop.

Expected behavior:

- Accept `PROJECT_DIR`, `--max-new-evaluations`, and `--cadence-cshrc`.
- For each requested cycle, call the Task 1 library function.
- Invoke the C-7 adapter outside the sandbox by launching the approved Cadence `csh -fc` flow.
- Print compact per-cycle status.
- Write a sanitized summary report under `PROJECT_DIR/reports/`.
- Refuse `--max-new-evaluations` values below 1.

- [x] Tests:

- CLI argument validation;
- fake subprocess runner success path;
- fake subprocess failure path;
- report shape.

- [x] Verification:

```bash
python3 -m pytest tests/test_optimizer_loop.py -q
python3 -m ruff check src tests tools
python3 tools/check_development_cadence.py
git diff --check
```

## Task 3: One-Cycle Real-Tool Acceptance

**Risk:** High. This runs real Spectre/OCEAN.

**Goal:** Run exactly one additional candidate cycle on the existing C-14 local project.

Prerequisites:

- Task 1 and Task 2 pass locally.
- The local project `/tmp/ic_auto_opt_c14/bridge_test_inv` still contains the C-14 two-row ledger.
- Real Spectre/OCEAN is launched outside the Codex sandbox.

- [x] Run:

```bash
csh -fc "source /home/zzchen/cadence_ic231_env.csh; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; /home/zzchen/.venvs/openclaw/bin/python tools/run_real_optimizer_loop.py /tmp/ic_auto_opt_c14/bridge_test_inv --max-new-evaluations 1 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh"
```

- [x] Expected:

- one new candidate request is written;
- one new real-run package is prepared;
- C-7 adapter runs once;
- the result is checked and either recorded or stopped with a clear failure state;
- no formulas are changed;
- raw artifacts remain local-only.

If the real run fails, stop and compare against C-14 evidence before code changes.

Task 3 execution note:

- Real loop command recorded `candidate_000003` as `real_003`.
- OCEAN metrics: `rise=6.508914194299693e-11 s`, `fall=6.17648525412794e-11 s`, `DC=0.0003515194271758733 W`.
- Ledger now has 3 rows.
- `candidate_000003` is `real_pass` and is the current best candidate.

## Task 4: Final Review And Closeout

**Risk:** Low to medium.

- [x] Actions:

- Update `docs/CURRENT_TASK_STATE.json`.
- Append a concise entry to `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`.
- Update `docs/EXECUTION_PROGRESS_2026-05-29.md` and `docs/COMPACT_RESUME_CHECKPOINT.md` if C-15 reaches real-tool acceptance.
- Run focused tests, ruff, cadence checker, and `git diff --check`.
- Review gate by risk: code-quality/spec review is required because Task 1/2 add orchestration and file writes.

Acceptance:

- C-15 remains a small loop driver around proven contracts.
- No broad optimizer framework or speculative assets are introduced.

Task 4 execution note:

- Final verification passed with focused C-15 tests, adjacent contract regressions, ruff, cadence checker, and `git diff --check`.
- Initial local spec/code-quality review passed and identified no Critical findings. Important coverage/reporting improvements were still applied: direct `result_check_failed` and `record_failed` tests now cover the remaining fail-closed branches, adapter stdout/stderr issues are bounded in the loop report, and the CLI uses the `RECORDED` constant instead of a string literal.
- Local spec re-review and local code-quality re-review both passed with no remaining blockers.
- C-15 remains narrow: no broad optimizer framework, daemon, scheduler, PSF parser, formula rewrite, or native-layout replacement was added.
