# Claude Prompt: Phase 12b Remote Waveform Metric Name Fix

You are working in:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

This is a narrow Phase 12 scope extension. Phase 12 migrated
`tests/real_run_smoke_helpers.py` to generic projects and the helper consumer
group passed, but the full suite failed in `tests/test_remote_spectre_ocean_waveform.py`
because its fake remote runners still write `rise`/`fall`/`DC` rows to
`ocean_scalars.tsv`.

## Read First

Read:

```text
docs/superpowers/specs/2026-06-19-test-project-factory-template-coupling-phase12b-remote-waveform-metric-names-spec.md
docs/superpowers/plans/2026-06-19-test-project-factory-template-coupling-phase12b-remote-waveform-metric-names-plan.md
tests/test_remote_spectre_ocean_waveform.py
tests/test_remote_spectre_ocean.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

## Strict Scope

Allowed to modify only:

```text
tests/test_remote_spectre_ocean_waveform.py
docs/superpowers/reports/2026-06-18-test-project-factory-template-coupling-inventory.md
```

Do not modify:

```text
src/
tests/real_run_smoke_helpers.py
tests/test_remote_spectre_ocean.py
tests/test_template_coupling_guard.py
../ic-auto-opt-workflow-v0.1
graphify-out/
docs/superpowers/specs/
docs/superpowers/plans/
docs/superpowers/prompts/
```

Do not commit, tag, push, or publish.

## Required Fix

In `tests/test_remote_spectre_ocean_waveform.py`, extend the sibling import:

```python
from tests.test_remote_spectre_ocean import (
    FakeRunner,
    _ocean_scalars_tsv,
    _request_for_metrics_dir,
    create_approved_real_project,
)
```

Then replace both hardcoded `ocean_scalars.tsv` writes in:

- `WaveformFakeRunner.download_tree()`
- `WaveformCsvOnlyRunner.download_tree()`

with:

```python
(Path(local_path) / "ocean_scalars.tsv").write_text(
    _ocean_scalars_tsv(_request_for_metrics_dir(Path(local_path))),
    encoding="utf-8",
)
```

Keep waveform CSV, waveform manifest, `ocean.stdout`, `ocean.stderr`, and
`ocean.log` behavior unchanged.

Update the inventory with a short Phase 12b addendum and exact verification
results.

## Required Verification

Run:

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
git status --short
```

Expected:

- Waveform file: `7 passed, 13 warnings`
- Full suite: about `1194 passed, 13 warnings`
- Ruff passes.
- `git diff --check` clean.
- Release checkout clean.
- Old hardcoded TSV metric row grep prints no matches.
- No production files touched.
- `graphify-out/` untouched.

## Stop and Ask If

Stop and report if:

- Production code seems necessary.
- Any file beyond `tests/test_remote_spectre_ocean_waveform.py` and inventory
  must be edited.
- Full-suite failures remain outside this waveform sibling file.

## Final Report Format

Return:

1. Files modified.
2. Root cause.
3. Fix summary.
4. Exact verification commands and pass/fail counts.
5. Release checkout status.
6. Confirmation that no production files and no `graphify-out/` files were touched.
7. Whether Phase 12 is now committable.
