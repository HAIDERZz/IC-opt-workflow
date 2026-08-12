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

This table is enforced by
`tests/test_history_warm_start_docs.py::test_release_checklist_names_complete_requirement_mirror_set`,
which asserts both sides of every pair appear here and that the two files'
contents are identical. Add a template, add its pair here in the same change.

`TASK.md`, `CIRCUIT_KNOWLEDGE.md`, and `FAILURE_PLAYBOOK.md` are intentionally
excluded from this mirror set (`STATIC_MIRROR_FILES` in the same test file
lists only the three files above). They are per-project scratch/entry files
copied into a new project by `create_project_from_template`, not user-facing
example documentation, and are not expected to exist under `examples/`.

## Sync Release Checkout

The release checkout is a separate working tree from the authoritative
development package; it is not automatically current. Before running the
checks below, sync the release checkout from the development package:

```bash
rsync -a --delete \
  --exclude='.git' --exclude='vendor' --exclude='build' --exclude='dist' \
  --exclude='graphify-out' --exclude='.remember' --exclude='*.egg-info' \
  --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
  --exclude='.ruff_cache' --exclude='.mypy_cache' \
  <dev-package>/ <release-checkout>/
```

After syncing, diff every functional file's checksum between the two trees
(same exclude set) and confirm the difference count is zero before proceeding.
A prior sync found 112 stale/missing functional files (root, docs, examples,
skills, src, tests) when this step was skipped; do not assume the release
checkout already reflects the development package.

## Required Checks

Run these from the release checkout, after the sync above:

```bash
rm -rf build dist src/*.egg-info
test -f src/hermes_workflow/templates/spectre_maestro_project/config/process_corners.yaml
! grep -R -n "bridge_test_inv\|FN\|WN\|FP\|WP\|rise\|fall\|DC" src/hermes_workflow/templates/spectre_maestro_project
! grep -rn '/home/[a-z]' docs/audits/
test "$(cat VERSION)" = "$(python -c 'import hermes_workflow; print(hermes_workflow.__version__)')"
test "$(cat VERSION)" = "$(python -c 'import tomllib,pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')"
python -m pytest tests/test_fix_run_docs.py tests/test_history_warm_start_docs.py tests/test_requirement_intake.py tests/test_requirement_intake_fix_run.py tests/test_optimizer_insight_docs.py tests/test_template_coupling_guard.py -q
python -m pytest -q
python -m ruff check src tests
git diff --check
test ! -d build
test ! -d src/ic_auto_opt_workflow.egg-info
```

`rm -rf build dist src/*.egg-info` removes stale build artifacts before the
checks run; a stale `build/lib/.../spectre_maestro_project/` tree or a stale
`*.egg-info/SOURCES.txt` can silently omit newly added requirement templates
from what a source distribution or import-path inspection reports, without
failing any check that only looks at `src/`. The two `test ! -d` lines at the
end confirm the cleanup was not undone by an intervening command.

The desensitized-config grep above now covers the whole
`spectre_maestro_project` template directory (config and the `.md` templates
and docs together), not only `config/`; this was confirmed to produce no
matches against the current template set. The `docs/audits/` grep guards
against a maintenance-audit document that leaks a maintainer's absolute home
directory path before it reaches the GitHub source archive; see the note
below on what `docs/audits/` content is allowed to ship.

Cross-check the two-step install dependency files
(`requirements-product.txt`, and optionally `requirements-advanced.txt`)
against `pyproject.toml`'s `[project.dependencies]` for drift before release;
there is no automated check for this today.

The three version sources (`VERSION`, `pyproject.toml`, and
`src/hermes_workflow/__init__.py`) must agree; the two `test` lines above only
check `VERSION` against each of the other two. There is currently no
committed regression test asserting all three programmatically -- adding one
is a code change and is out of scope for this checklist edit; track it as a
follow-up decision rather than assuming the manual command above is a
permanent substitute.

Packaged template `config/*.yaml` files must be current Mixer starter resources,
not legacy inverter starter resources.

The release `docs/` directory should contain only current product, user, agent,
toolchain, troubleshooting, and explicitly curated maintenance-audit
documentation. The maintained correctness ledger under `docs/audits/` may be
kept in the source repository and GitHub source archive, but it is not installed
as Python runtime package data. Do not include temporary agent work notes,
generated analysis folders, graph outputs, or raw Cadence artifacts in the
release package.

## Package Verification

Confirm the templates that make a project usable actually ship inside the
built wheel, not only inside the `src/` checkout:

```bash
python -m pip install --upgrade build
python -m build --wheel
test "$(unzip -l dist/*.whl | grep -c 'templates/spectre_maestro_project/opt_requirement.*\.md')" = "11"
python -m venv /tmp/ic-opt-wheel-check
/tmp/ic-opt-wheel-check/bin/python -m pip install dist/*.whl
/tmp/ic-opt-wheel-check/bin/ic-opt --help
/tmp/ic-opt-wheel-check/bin/hermes-workflow --help
rm -rf /tmp/ic-opt-wheel-check
```

`pyproject.toml`'s `[tool.setuptools.package-data]` glob is the only thing
that decides whether the eleven `opt_requirement*.md` templates ship in the
wheel; nothing else in this checklist exercises that path. The `build`
package (`python -m pip install build`) is a prerequisite for
`python -m build --wheel` and is not part of the base dev environment; a venv
without it fails this step outright rather than failing the wheel build
itself, so verify it is installed before relying on a red result here as a
real signal.
