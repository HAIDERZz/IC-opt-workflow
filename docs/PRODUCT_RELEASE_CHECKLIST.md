# Product Release Checklist

Use this before publishing a release package.

## Product Contract

First real run:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

Continuation:

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Initial-run optimizer, resource, Spectre, metric, retention, and process-corner
settings come from `PROJECT_DIR/opt_requirement.md` and generated config files.

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

Keep these examples current:

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
```

Requirement examples must parse with current requirement intake. Placeholder
path failures are acceptable; schema/field failures are not.

For the fix-run example, additionally verify:

- `opt_requirement.fix_run.md` parses as `Workflow.mode: fix_run`
- the packaged template at
  `src/hermes_workflow/templates/spectre_maestro_project/opt_requirement.fix_run.md`
  is byte-for-byte identical to the example
- fix-run example does not reference `psfascii` or optimizer-only CLI flags

## Real Run Acceptance

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

## Documentation

Before publishing:

- remove engineering logs, debug records, superpowers plans, build artifacts,
  test cache files, and raw tool evidence from the release package
- check that README, release notes, user guides, agent docs, skills, and
  examples describe the same CLI contract
- check markdown code fences
- check user-facing docs do not advertise stale CLI controls
- keep `RELEASE_NOTES_v0.1.7.md` as the release summary

## Files That Must Not Be Released

Do not publish raw `input.scs`, protected sidecars, encrypted PDK includes,
PSF/raw simulator databases, full Cadence logs, user proprietary Maestro point
roots, or license/server secrets.
