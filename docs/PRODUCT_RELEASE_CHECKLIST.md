# Product Release Checklist

Use this before publishing a release package.

## Product Contract

First real workflow run:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

Continuation for existing optimizer runs:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Initial-run optimizer, fix-run, resource, Spectre, metric, waveform export,
retention, and process-corner settings come from
`PROJECT_DIR/opt_requirement.md` and generated config files.

## Environment

Install from the release root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Dependency smoke:

```bash
./.venv/bin/python -c "import openbox, turbo, torch, gpytorch, scipy, threadpoolctl, hermes_workflow; print('product optimizer env ok')"
```

Entrypoints:

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## Release Examples

Keep these examples current and mirrored into package templates:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
examples/spectre_maestro_project/OPT_REQUIREMENT_README.md
src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_testbench.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_tb_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.history_warm_start.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md
```

Requirement examples must parse with current requirement intake. Placeholder
path failures are acceptable; schema/field failures are not.

The multi-testbench examples must remain based on real validated Mixer
multi-testbench requirements: `cg_nf`, `iip3`, and `p1db` testbenches with
`BW`, `MAX_GAIN`, `NF_3G`, `IIP3`, and `P1DB` routed to their owning
testbenches. Do not replace them with toy one-testbench or one-metric examples.
The history warm-start example must remain a real second-round requirement
shape with a sanitized previous-project path.

## Real Optimization Acceptance

Prove:

- `reports/optimizer_run_report.json` reports pass
- generated `config/optimizer.yaml` and `config/spectre.yaml` match
  `opt_requirement.md`
- child result and metric manifests contain sanitized `command_trace`
- aggregate manifests include expected child evidence for multi-testbench or
  multi-corner projects
- optimizer reports include `runtime_thread_limits` when
  `optimizer_cpu_threads` is set
- `reports/optimizer_decision_report.md` reports a best observed feasible
  candidate when feasible evidence exists
- reports do not claim a mathematical global optimum

## Real Fix-Run Acceptance

Prove:

- `reports/fix_run_report.json` reports pass
- `workflow_mode` is `fix_run`
- the child count matches the expected testbench/corner combinations
- each successful child has result, scalar metric, waveform export, and CSV
  artifacts when waveform exports are requested
- optimizer state and optimizer decision report are not created
- failures are reported through `child_issues`, not hidden by the parent report

## Documentation

Before publishing:

- remove engineering logs, debug records, superpowers plans, build artifacts,
  test cache files, and raw tool evidence from the release package
- check that README, release notes, user guides, agent docs, skills, and
  examples describe the same CLI contract
- run `tests/test_history_warm_start_docs.py`
- compare all `opt_requirement*.md` examples and
  `OPT_REQUIREMENT_README.md` against their
  `src/hermes_workflow/templates/spectre_maestro_project/` mirrors
- verify history warm-start docs use the real `History Warm Start`
  requirement section, `history_warm_start` config name,
  `reports/history_warm_start_audit.json`, and
  `openbox.history_warm_start`
- verify history warm-start docs do not advertise a fake
  `--history-warm-start` CLI flag
- verify `opt_requirement.history_warm_start.md` is present in both examples
  and packaged templates
- check markdown code fences
- check user-facing docs do not advertise stale CLI controls
- keep `RELEASE_NOTES_v0.1.9.md` as the release summary

## Files That Must Not Be Released

Do not publish raw `input.scs`, protected sidecars, encrypted PDK includes,
PSF/raw simulator databases, full Cadence logs, user proprietary Maestro point
roots, or license/server secrets.
