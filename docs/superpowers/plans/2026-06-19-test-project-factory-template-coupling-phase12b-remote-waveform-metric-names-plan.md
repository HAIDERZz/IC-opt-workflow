# Test Project Factory Template Coupling Phase 12b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Phase 12 full-suite regression by making remote waveform
fake runners write metric TSV rows that match generic-project metric requests.

**Architecture:** Keep the fix inside `tests/test_remote_spectre_ocean_waveform.py`
by reusing the request-derived TSV helpers from `tests/test_remote_spectre_ocean.py`.
No production code changes are expected. The inventory gets a short Phase 12b
addendum because this is a scope extension to make Phase 12 committable.

**Tech Stack:** Python, pytest, JSON fixtures, remote Spectre/OCEAN adapter tests.

---

## File Structure

- Modify `tests/test_remote_spectre_ocean_waveform.py`
  - Import `_request_for_metrics_dir` and `_ocean_scalars_tsv` from
    `tests.test_remote_spectre_ocean`.
  - Replace hardcoded `rise`/`fall`/`DC` TSV rows in waveform fake runners.

- Modify `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`
  - Add a Phase 12b addendum and exact verification.

## Task 0: Confirm the Regression

**Files:**
- Read: `tests/test_remote_spectre_ocean_waveform.py`
- Read: `tests/test_remote_spectre_ocean.py`

- [ ] **Step 1: Run the failing waveform file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean_waveform.py -q
```

Expected before fix:

```text
6 failed, 1 passed, 13 warnings
```

The failure issues should include:

```text
metric metric_gain missing from ocean scalar output
metric metric_power missing from ocean scalar output
unrequested metric in ocean scalar output: rise
unrequested metric in ocean scalar output: fall
unrequested metric in ocean scalar output: DC
```

## Task 1: Reuse Request-Derived TSV Helpers

**Files:**
- Modify: `tests/test_remote_spectre_ocean_waveform.py`

- [ ] **Step 1: Extend the import from `tests.test_remote_spectre_ocean`**

Change:

```python
from tests.test_remote_spectre_ocean import (
    FakeRunner,
    create_approved_real_project,
)
```

to:

```python
from tests.test_remote_spectre_ocean import (
    FakeRunner,
    _ocean_scalars_tsv,
    _request_for_metrics_dir,
    create_approved_real_project,
)
```

- [ ] **Step 2: Update `WaveformFakeRunner.download_tree()`**

Replace the hardcoded `ocean_scalars.tsv` body under `elif remote.endswith("/metrics")`
with:

```python
(Path(local_path) / "ocean_scalars.tsv").write_text(
    _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
    encoding="utf-8",
)
```

Keep `ocean.stdout`, `ocean.stderr`, and `ocean.log` writes unchanged.

- [ ] **Step 3: Update `WaveformCsvOnlyRunner.download_tree()`**

Replace the hardcoded `ocean_scalars.tsv` body under `elif remote.endswith("/metrics")`
with the same request-derived write:

```python
(Path(local_path) / "ocean_scalars.tsv").write_text(
    _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
    encoding="utf-8",
)
```

Keep waveform CSV and log writes unchanged.

- [ ] **Step 4: Run waveform file**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean_waveform.py -q
```

Expected:

```text
7 passed, 13 warnings
```

## Task 2: Verify Remote Sibling Compatibility

**Files:**
- Verify: `tests/test_remote_spectre_ocean.py`
- Verify: `tests/test_remote_spectre_ocean_waveform.py`

- [ ] **Step 1: Run remote sibling tests together**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected: both files pass. Record the exact count and warning count.

- [ ] **Step 2: Run Phase 12 consumer group including waveform sibling**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_local_real_run_smoke.py tests/test_optimizer_acceptance.py tests/test_optimizer_completion.py tests/test_optimizer_finalize.py tests/test_optimizer_status.py tests/test_native_turbo.py tests/test_openbox_backend.py tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q
```

Expected: the Phase 12 consumer group plus waveform sibling passes. Record exact
count and warning count.

## Task 3: Update Inventory

**Files:**
- Modify: `docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md`

- [ ] **Step 1: Add a Phase 12b addendum after Phase 12 status**

Add:

```markdown
### Phase 12b addendum

Phase 12 exposed one sibling test-file drift outside the original allowed scope:
`tests/test_remote_spectre_ocean_waveform.py` still wrote fake remote
`ocean_scalars.tsv` rows with legacy `rise`/`fall`/`DC` metrics while
`create_approved_real_project()` now creates generic metric requests. Phase 12b
updated the waveform fake runners to reuse the request-derived TSV helpers from
`tests/test_remote_spectre_ocean.py`, restoring full-suite compatibility without
production changes.
```

- [ ] **Step 2: Add verification results**

Add the exact Phase 12b verification commands and results:

```markdown
- `pytest tests/test_remote_spectre_ocean_waveform.py -q` -> ...
- `pytest tests/test_remote_spectre_ocean.py tests/test_remote_spectre_ocean_waveform.py -q` -> ...
- `pytest [Phase 12 consumer group + waveform sibling] -q` -> ...
- `pytest tests/test_template_coupling_guard.py -q` -> ...
- `pytest -q` -> ...
- `ruff check src tests` -> ...
- `git diff --check` -> clean
- `git -C ../ic-auto-opt-workflow-v0.1 status --short` -> clean
- grep hardcoded old TSV metric rows over `tests/test_remote_spectre_ocean_waveform.py` -> no matches
```

## Task 4: Full Verification and Final Report

**Files:**
- Verify: waveform file, remote sibling, Phase 12 consumer group, guard, full suite

- [ ] **Step 1: Run coupling guard**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_template_coupling_guard.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 2: Run full suite**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected:

```text
1194 passed, 13 warnings
```

If the count differs because Phase 12 changed collection counts, record the
actual count.

- [ ] **Step 3: Run ruff**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: clean.

- [ ] **Step 5: Confirm release checkout stayed untouched**

Run:

```bash
git -C ../ic-auto-opt-workflow-v0.1 status --short
```

Expected: no output.

- [ ] **Step 6: Check hardcoded old TSV rows are gone**

Run:

```bash
grep -n '"rise\\t\\|fall\\t\\|DC\\t"' tests/test_remote_spectre_ocean_waveform.py || true
```

Expected: no output.

- [ ] **Step 7: Final report**

Report:

- Files modified.
- Root cause.
- Exact fix.
- Verification commands and results.
- Release checkout status.
- Confirmation that no production files and no `graphify-out/` files were touched.
- Whether Phase 12 is now committable.

Do not commit, tag, push, or publish.

## Stop Conditions

Stop and report if:

- Production code under `src/` appears necessary.
- Any file beyond `tests/test_remote_spectre_ocean_waveform.py` and inventory
  must be edited.
- Full-suite failures remain outside this waveform sibling file.
