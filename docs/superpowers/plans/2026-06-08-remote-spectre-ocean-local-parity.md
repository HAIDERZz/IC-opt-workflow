# C-70 Remote Spectre/OCEAN Local-Parity Implementation Plan

> **For coding agents:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development`. The implementation agent must
> perform its own spec review and code-quality review before asking Codex for
> final acceptance.

**Goal:** make remote Spectre/OCEAN execution semantically identical to the
proven local Spectre/OCEAN adapter. C-70 keeps the C-69 SSH/product plumbing but
replaces the duplicated remote command/manifest behavior.

**Status 2026-06-09:** implemented and reviewed for local/unit parity in
commits `4fb3d29` and `84afe18`. Targeted C-70 tests passed with `98 passed`;
full pytest passed with `733 passed, 1 warning`; ruff, cadence, and
`git diff --check` passed. Real remote SSH/Spectre/OCEAN parity acceptance is
still pending user authorization.

**Design authority:**

```text
docs/superpowers/specs/2026-06-08-remote-spectre-ocean-local-parity-design.md
```

**Hard boundary:** no optimizer behavior changes, no requirement grammar
changes, no metric formula changes, no remote Python product install, no PSF
parsing, and no new broad remote framework.

## Current Diagnosis

C-69 remote SSH mode proved useful SSH orchestration and product routing, but
deep artifact inspection found the Spectre/OCEAN adapter was not equivalent to
the local proven adapter:

- remote Spectre command was hand-built and omitted local adapter flags;
- remote Spectre command hardcoded `+preset=aps`;
- remote OCEAN used `-restore` instead of local `-replay ... -log ...`;
- remote mode did not download required PSF artifacts before writing success
  manifests;
- remote success manifest could reference missing `psf/spectre.out`;
- remote metric result manifest could show child success while metric rows
  failed.

The requirement markdown is not the cause. The local RC project used the same
requirement and produced valid multi-testbench results.

## Task 1: Downgrade C-69 Acceptance Claim And Add Regression Tests

**Purpose:** lock the discovered failure into tests before any implementation
changes.

**Files:**

- Modify: `docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md`
- Modify: `tests/test_remote_spectre_ocean.py`
- Modify if needed: `tests/test_remote_optimizer_flow.py`

**Steps:**

1. Update the C-69 evidence doc to say:
   - SSH orchestration/product routing passed;
   - remote Spectre/OCEAN parity was not accepted;
   - C-70 is required before production remote Spectre/OCEAN acceptance.
2. Add a failing command parity test proving remote Spectre uses the canonical
   local argv. The test must fail on the current C-69 implementation because it
   hardcodes `+preset=aps` and omits local flags.
3. Add a failing OCEAN command parity test proving remote OCEAN uses
   `-replay` and `-log`, not `-restore`.
4. Add a failing missing-artifact test:
   - fake remote Spectre returns success;
   - fake remote download does not create `psf/` or `psf/spectre.out`;
   - adapter must return failed and must not write a success result manifest.
5. Add a failing metric failure propagation test:
   - `ocean_scalars.tsv` exists with one requested metric row marked `fail`;
   - metric result manifest top-level status must be `failed`;
   - adapter result status must be `failed`.

**Verification:**

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected before implementation: the new tests fail for the C-69 behavior.

**Commit after green later:** no commit until Tasks 2-4 make the tests pass.

## Task 2: Use Local Canonical Spectre/OCEAN Argv In Remote Adapter

**Purpose:** remove command semantic drift without redesigning remote SSH.

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify: `tests/test_remote_spectre_ocean.py`

**Steps:**

1. Expose narrow public wrappers from the local adapter:

   ```python
   def build_spectre_argv(context: SpectreOceanContext) -> list[str]: ...
   def build_ocean_argv(context: SpectreOceanContext) -> list[str]: ...
   ```

   Preserve existing private wrappers if other code or tests rely on them:

   ```python
   def _spectre_argv(context): return build_spectre_argv(context)
   def _ocean_argv(context): return build_ocean_argv(context)
   ```

2. In `remote_spectre_ocean.py`, replace the hand-built command body with
   shell-quoted canonical argv from those wrappers.
3. Keep the remote Cadence environment wrapper only:

   ```text
   csh -fc 'source <remote_cadence_cshrc>; cd <canonical remote cwd>; <canonical argv>'
   ```

4. Map cwd exactly:
   - Spectre remote cwd: remote equivalent of `context.input_scs.parent`;
   - OCEAN remote cwd: remote equivalent of `context.project_dir`.
5. Do not alter local adapter behavior.

**Verification:**

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_spectre_ocean_adapter.py -q
```

Expected: command parity tests pass; local adapter tests still pass.

## Task 3: Download Required Remote Artifacts Before Manifest Writing

**Purpose:** make success impossible when remote PSF/log/scalar artifacts are
missing.

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify: `tests/test_remote_spectre_ocean.py`

**Steps:**

1. After remote Spectre returns success, download at least:
   - child/candidate `psf/`;
   - `psf/spectre.out`;
   - `spectre.stdout`;
   - `spectre.stderr`.
2. Verify the local mirror contains:
   - `context.psf_dir`;
   - `context.psf_dir / "spectre.out"`.
3. If required Spectre artifacts are absent, return failed and write a failure
   result manifest through the local manifest helper path.
4. After remote OCEAN returns, download at least:
   - `metrics/metric_probe.ocn`;
   - `metrics/ocean.log`;
   - `metrics/ocean.stdout`;
   - `metrics/ocean.stderr`;
   - `metrics/ocean_scalars.tsv`.
5. Verify `ocean_scalars.tsv` exists before metric manifest writing.
6. Do not parse remote files in place; all parsing and manifest writing must
   happen against the local mirror.

**Verification:**

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py -q
```

Expected: missing artifact test passes.

## Task 4: Delegate Manifest Semantics To Local Adapter Helpers

**Purpose:** eliminate hand-written remote success/failure manifest drift.

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/spectre_ocean.py`
- Modify: `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify: `tests/test_remote_spectre_ocean.py`

**Steps:**

1. Expose only the minimum manifest helper surface needed by the remote adapter.
   Prefer wrappers over copying payload construction:

   ```python
   def write_spectre_result_manifest(...): ...
   def write_metric_result_manifest(...): ...
   ```

   The wrappers may call existing private helpers.
2. Remove or fully neutralize `_write_remote_success_manifests`.
3. Remove or fully neutralize remote hand-written success manifest payloads.
4. Ensure failed metric scalar rows extend the same top-level issue list as
   local mode.
5. Upload the final local `result_manifest.json` and
   `metric_result_manifest.json` back to the remote project only after local
   manifest writing succeeds.

**Verification:**

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q
```

Expected: metric failure propagation test passes.

## Task 5: Preserve Multi-Testbench Aggregation And Remote Flow Routing

**Purpose:** keep remote multi-testbench behavior identical to local
multi-testbench aggregation.

**Files:**

- Modify: `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`
- Modify if needed: `src/hermes_workflow/remote_optimizer_flow.py`
- Modify: `tests/test_remote_optimizer_flow.py`

**Steps:**

1. Keep one remote native Maestro/ADE bundle per child testbench.
2. Call the fixed remote single-testbench adapter for each child.
3. Do not multiply `spectre.parallel_jobs` by testbench count.
4. Do not merge child netlists into one synthetic deck.
5. Aggregate child manifests with the existing
   `aggregate_multi_testbench_run()` path.
6. Ensure child adapter failures propagate to aggregate and optimizer
   classification.

**Verification:**

```bash
rtk proxy ./.venv/bin/python -m pytest tests/test_remote_optimizer_flow.py tests/test_remote_spectre_ocean.py tests/test_multi_testbench_aggregation.py -q
```

Expected: remote multi-testbench tests pass without changing local
aggregation.

## Task 6: Real Remote Parity Acceptance

**Purpose:** prove remote mode now follows the same Spectre/OCEAN path as the
already accepted local RC project.

**Files:**

- Add or update: `docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md`
- Update: `docs/CURRENT_TASK_STATE.json`
- Update: `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`
- Update milestone docs only if the evidence changes the project route.

**Steps:**

1. Use the user-provided remote project path and passwordless SSH profile only.
2. Run remote doctor:

   ```bash
   rtk proxy ./.venv/bin/ic-opt --ssh-profile PROFILE /remote/project --doctor
   ```

3. Run the smallest meaningful real parity check. Prefer a deterministic first
   candidate run:

   ```bash
   rtk proxy ./.venv/bin/ic-opt --ssh-profile PROFILE /remote/project --real --max-evals 1 --batch-size 1 --parallel-jobs 1
   ```

4. If the first candidate matches the known local first candidate
   `F=14, L=40n, VB_LO=150m, W=0.4u`, compare child scalar behavior against
   the local RC pattern:
   - `cg_nf`: `MAX_GAIN` and `NF_3G` pass;
   - `iip3`: `IIP3` passes;
   - known weak-candidate non-scalar metrics may remain non-scalar.
5. If the first candidate differs, do not change formulas. Record the actual
   candidate and run the smallest deterministic continuation needed to compare
   an identical candidate if available.
6. Verify local mirror and remote project both contain required child artifacts:
   - `psf/`;
   - `psf/spectre.out`;
   - `spectre.stdout`;
   - `spectre.stderr`;
   - `metrics/ocean.log`;
   - `metrics/ocean.stdout`;
   - `metrics/ocean.stderr`;
   - `metrics/ocean_scalars.tsv`.
7. Run targeted and full regression appropriate for real-tool adapter work:

   ```bash
   rtk proxy ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_optimizer_flow.py tests/test_product_cli_remote.py tests/test_spectre_ocean_adapter.py -q
   rtk proxy ./.venv/bin/python -m pytest -q
   rtk proxy ./.venv/bin/python -m ruff check src tests
   rtk proxy ./.venv/bin/python tools/check_development_cadence.py
   rtk git diff --check
   ```

**Acceptance:** C-70 is not complete until unit parity and real remote parity
evidence both pass.

## Final Review Requirements

Claude implementation agent must provide:

- spec-compliance review against every invariant in the C-70 design;
- code-quality review focusing on duplication removal, shell quoting, artifact
  validation, manifest delegation, and local-mode regression risk;
- actual command outputs or concise summaries for all verification commands;
- a commit hash for the implementation.

Codex final acceptance will check:

- no optimizer, FoM, requirement grammar, or metric formula changes were made;
- remote adapter no longer contains the C-69 hardcoded command semantics;
- missing artifacts cannot produce success manifests;
- local adapter behavior remains unchanged;
- real remote evidence is based on actual Spectre/OCEAN artifacts, not only
  optimizer closeout success.
