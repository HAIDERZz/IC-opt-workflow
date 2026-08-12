# Product Release Checklist

Use this checklist before publishing the release package. It is a guard against
documentation/template drift, not a development progress log.

## Required Requirement Mirrors

The user-facing examples and packaged templates must match byte-for-byte:

```text
examples/spectre_maestro_project/OPT_REQUIREMENT_README.md
src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md

examples/spectre_maestro_project/METRICS.md
src/hermes_workflow/templates/spectre_maestro_project/METRICS.md

examples/spectre_maestro_project/constraints.md
src/hermes_workflow/templates/spectre_maestro_project/constraints.md

examples/spectre_maestro_project/opt_requirement.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md

examples/spectre_maestro_project/opt_requirement.multi_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_corner.md

examples/spectre_maestro_project/opt_requirement.multi_testbench.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_testbench.md

examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_tb_corner.md

examples/spectre_maestro_project/opt_requirement.history_warm_start.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.history_warm_start.md

examples/spectre_maestro_project/opt_requirement.fix_run.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md

examples/spectre_maestro_project/opt_requirement.openbox_gp_eic.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.openbox_gp_eic.md

examples/spectre_maestro_project/opt_requirement.turbo.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.turbo.md

examples/spectre_maestro_project/opt_requirement.history_warm_start.multi_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.history_warm_start.multi_corner.md

examples/spectre_maestro_project/opt_requirement.fix_run.metrics_only.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.metrics_only.md

examples/spectre_maestro_project/opt_requirement.fix_run.multi_testbench.metrics_waveform.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.multi_testbench.metrics_waveform.md
```

## Required Checks

Run these from the release checkout:

```bash
test -f src/hermes_workflow/templates/spectre_maestro_project/config/process_corners.yaml
! grep -R -n "bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" src/hermes_workflow/templates/spectre_maestro_project/config
python -m pytest tests/test_fix_run_docs.py tests/test_history_warm_start_docs.py tests/test_requirement_intake.py -q
python -m pytest -q
python -m ruff check src tests
git diff --check
```

Packaged template `config/*.yaml` files must be current Mixer starter resources,
not legacy inverter starter resources.

The release `docs/` directory should contain only current product, user, agent,
toolchain, troubleshooting, and explicitly curated maintenance-audit
documentation. The maintained correctness ledger under `docs/audits/` may be
kept in the source repository and GitHub source archive, but it is not installed
as Python runtime package data. Do not include temporary agent work notes,
generated analysis folders, graph outputs, or raw Cadence artifacts in the
release package.
