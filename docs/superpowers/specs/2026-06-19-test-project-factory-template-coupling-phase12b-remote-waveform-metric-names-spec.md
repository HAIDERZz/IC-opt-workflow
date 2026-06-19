# Test Project Factory Template Coupling Phase 12b Spec

Date: 2026-06-19

## Objective

Fix the Phase 12 full-suite regression in
`tests/test_remote_spectre_ocean_waveform.py`.

Phase 12 migrated `tests/real_run_smoke_helpers.py` to generic projects. The
helper's remote consumers now expect metric names from each run's
`metric_extraction_request.json`. `tests/test_remote_spectre_ocean.py` was updated
accordingly, but sibling waveform tests still write fake remote
`ocean_scalars.tsv` rows for the old `rise`/`fall`/`DC` metrics. The adapter then
fails because the generic run requests `metric_gain`/`metric_power`.

## Scope

Allowed files to modify:

- `tests/test_remote_spectre_ocean_waveform.py`
- `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

Allowed files to read for orientation:

- `tests/test_remote_spectre_ocean.py`
- `tests/real_run_smoke_helpers.py`
- `src/hermes_workflow/execution_adapters/remote_spectre_ocean.py`

Do not modify production code, the release checkout, Phase 12 prompt/spec/plan,
or unrelated tests.

## Requirements

### 1. Fix Fake Remote Scalar TSV Generation

`WaveformFakeRunner.download_tree()` and `WaveformCsvOnlyRunner.download_tree()`
must stop writing hardcoded `rise`/`fall`/`DC` rows for generic-project runs.

Required behavior:

- Reuse the request-derived helper logic already present in
  `tests/test_remote_spectre_ocean.py`:
  - `_request_for_metrics_dir(Path(local_path))`
  - `_ocean_scalars_tsv(request)`
- When a request is available, fake remote `ocean_scalars.tsv` must contain the
  exact metric names and expression hashes requested by the run.
- The fallback legacy rows in `tests/test_remote_spectre_ocean.py` may remain
  unchanged for old direct-template tests. This Phase 12b should not remove
  legacy fallback behavior from sibling tests.

### 2. Preserve Waveform Contract Coverage

All existing waveform assertions must remain meaningful:

- Remote waveform CSV files are downloaded.
- Remote waveform export manifest is downloaded when present.
- Missing waveform artifacts do not fail the adapter.
- Local manifest generation works when the remote CSV exists but the remote
  manifest is absent.
- Generated manifest schema matches the local helper.
- Sanitized command trace does not leak cshrc/source/csh wrapper.
- Generated manifest is uploaded back to remote.

Do not weaken these tests to only check adapter success.

### 3. Inventory

Update the inventory report with a short Phase 12b addendum:

- State that `tests/test_remote_spectre_ocean_waveform.py` was updated as a
  Phase 12 scope-extension because the generic helper migration exposed stale
  fake remote TSV metric names.
- Record exact verification results.
- Do not change the guard allowlist count unless the implementation also changes
  `tests/test_template_coupling_guard.py`, which is not expected in this phase.

## Non-Goals

Do not modify:

- Production code under `src/`
- `tests/real_run_smoke_helpers.py`
- `tests/test_remote_spectre_ocean.py`
- `tests/test_template_coupling_guard.py`
- Release checkout `../ic-auto-opt-workflow-v0.1`
- `graphify-out/`

Do not commit, tag, push, or publish. The user will commit only after full suite
is green.

## Required Verification

Run from `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean_waveform.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
git diff --check
git -C ../ic-auto-opt-workflow-v0.1 status --short
grep -n '"rise\\t\\|fall\\t\\|DC\\t"' tests/test_remote_spectre_ocean_waveform.py || true
```

Expected:

- `tests/test_remote_spectre_ocean_waveform.py`: `7 passed, 13 warnings`
- Full suite: `1194 passed, 13 warnings` or the actual current full-suite count
  if Phase 12 changed collection counts.
- Ruff passes.
- `git diff --check` is clean.
- Release checkout remains clean.
- The grep for hardcoded old TSV metric rows prints no matches.

## Stop Conditions

Stop and report if:

- Production code appears necessary.
- `tests/real_run_smoke_helpers.py` or the Phase 12 consumer files must be
  changed again.
- Fixing the waveform test requires migrating a broader remote adapter test
  cluster.
- Full-suite failures remain outside this waveform sibling file.
