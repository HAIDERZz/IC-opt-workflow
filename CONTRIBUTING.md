# Contributing

IC Auto Opt is file-driven analog/RF optimization software for Cadence
Spectre/OCEAN projects.

Keep the product flow simple:

```text
opt_requirement.md -> ic-opt PROJECT --real -> reports/artifacts
```

## Development Setup

Use one repository-level Python environment:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e ".[dev]"
```

`requirements-product.txt` already installs the package in editable mode
(`-e .`), so the last command only needs the `dev` extra
(`pytest`, `ruff`) that "Before Sending Changes" below requires. `scipy` is
not repeated in the `dev` extra because `-e .` already installs it from
`pyproject.toml`'s main `dependencies`. Skipping the `dev` extra install
makes `pytest`/`ruff` unavailable.

Use the site's Python 3.11+ command if `python3` is older than 3.11.

## Before Sending Changes

Tests are flat under `tests/` (roughly 80 `test_*.py` files, no per-area
subpackages) plus a shared `tests/fixtures/` directory, so target an area
with `pytest tests/test_<name>.py` or `-k` rather than a subdirectory path.

Run focused tests for the area you changed. For broad packaging changes, or
any change to the CLI, requirement templates, or the docs listed in "Docs
And Template Contract" below, run the full suite — it is the enforcement
mechanism for that contract and can take a while:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests
git diff --check -- . ':!vendor'
```

## Docs And Template Contract

Several tests fail on documentation/template drift alone, independent of any
code change:

- `examples/spectre_maestro_project/*` and
  `src/hermes_workflow/templates/spectre_maestro_project/*` must contain the
  same 11 `opt_requirement*.md` files plus `OPT_REQUIREMENT_README.md`,
  `METRICS.md`, and `constraints.md`, byte-for-byte identical between the two
  trees.
- README.md, `docs/USER_GUIDE_CN.md`, `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`,
  `docs/AGENT_USER_QUICKSTART_CN.md`, `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`,
  both `OPT_REQUIREMENT_README.md` copies, and `skills/ic-opt/SKILL.md` must
  each name all 11 requirement template filenames, and must never contain the
  nonexistent `--history-warm-start` CLI flag string.
- `docs/PRODUCT_RELEASE_CHECKLIST.md` must list both the `examples/...` and
  `src/hermes_workflow/templates/...` path for every mirrored file above.
- README.md, `docs/USER_GUIDE_CN.md`, `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`,
  `docs/AGENT_USER_QUICKSTART_CN.md`, and `skills/ic-opt/SKILL.md` also carry
  a separate contract requiring the `reports/optimizer_insight_report.json`
  `/.md`/`.html` paths and specific report-layer boundary wording
  (`tests/test_optimizer_insight_docs.py`).

Adding, renaming, or removing a requirement template, or editing any doc
above without updating the rest of the set, fails `pytest -q`
(`tests/test_history_warm_start_docs.py`,
`tests/test_optimizer_insight_docs.py`) even when the change looks purely
editorial.

## Release Checklist

A version bump changes three files together: `VERSION`, `pyproject.toml`
(`version = "..."`), and `src/hermes_workflow/__init__.py`
(`__version__ = "..."`). Add a matching `RELEASE_NOTES_vX.Y.Z.md` and update
README's "Current Release" section in the same change.

## Contribution Boundaries

- Do not commit `.venv`, generated project artifacts, PSF databases, raw Spectre
  output, Cadence logs, PDK files, or private Maestro point roots.
- Do not hardcode machine-specific paths or Spectre versions.
- Do not rewrite user-approved OCEAN formulas in code.
- Do not replace the file-contract workflow with chat-only behavior.
- Keep new features narrow, real-flow oriented, and backed by tests.

## License

By contributing, you agree that your contributions are provided under the MIT
License. See `LICENSE`.
