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
./.venv/bin/python -m pip install -e .
```

Use the site's Python 3.11+ command if `python3` is older than 3.11.

## Before Sending Changes

Run focused tests for the area you changed. For broad packaging changes, run:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests
git diff --check -- . ':!vendor' ':!.serena'
```

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
