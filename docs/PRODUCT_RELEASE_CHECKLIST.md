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

Keep the complete example-to-packaged-template mirror set current. The hard
constraint tests in `tests/test_fix_run_docs.py` and `tests/test_package.py`
verify that source-facing examples match packaged runtime templates and that
packaged template resources are not hidden by `.gitignore`.

Mirror roots:

```text
examples/spectre_maestro_project/
src/hermes_workflow/templates/spectre_maestro_project/
```

Mirror set:

```text
examples/spectre_maestro_project/OPT_REQUIREMENT_README.md
examples/spectre_maestro_project/METRICS.md
examples/spectre_maestro_project/constraints.md
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
src/hermes_workflow/templates/spectre_maestro_project/OPT_REQUIREMENT_README.md
src/hermes_workflow/templates/spectre_maestro_project/METRICS.md
src/hermes_workflow/templates/spectre_maestro_project/constraints.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_testbench.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.multi_tb_corner.md
src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md
```

Focused mirror/package-resource guard:

```bash
./.venv/bin/python -m pytest tests/test_fix_run_docs.py tests/test_package.py -q
```

Requirement examples must parse with current requirement intake. Placeholder
path failures are acceptable; schema/field failures are not.

## Post-v0.1.8 Follow-up: Decouple Generic Tests From The Release Template

The product runtime is metric/variable-generic (the fake evaluator derives
values for every declared metric; `tests/helpers/project_factory.py` builds
arbitrary projects and proves arbitrary metrics/variables flow through validate,
dry-run, and the fake optimizer). For v0.1.8, several generic behavior tests
still build a project via `create_project_from_template()` (the Mixer release
example) and then derive netlist templates / fake-runner scalars / expected
values from the project config, so they do not assume the Mixer circuit but
they do still touch the packaged template.

Tracked follow-up (do NOT block v0.1.8):

- Migrate generic optimizer / result-recording / status / finalize / dry-run /
  backend / adapter tests away from `create_project_from_template()` to the
  generic `tests/helpers/project_factory.py` builder, so no generic test
  depends on the packaged release template.
- Consider making `optimizer_insights.py` figure-of-merit scoring and display
  unit selection fully config/unit-driven instead of the current optional,
  graceful name-based heuristics (mixer FOM fallback; `rise`/`fall`/`delay`/
  `time` and `dc`/`power` display scaling). These are guarded and no-op for
  arbitrary metrics today, so they are not a v0.1.8 blocker.

A non-blocking guard test in `tests/test_fix_run_docs.py` asserts this section
is present so the follow-up is not silently dropped.

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
- check markdown code fences
- check user-facing docs do not advertise stale CLI controls
- keep `RELEASE_NOTES_v0.1.8.md` as the release summary

## Files That Must Not Be Released

Do not publish raw `input.scs`, protected sidecars, encrypted PDK includes,
PSF/raw simulator databases, full Cadence logs, user proprietary Maestro point
roots, or license/server secrets.
