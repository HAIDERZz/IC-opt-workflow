# Contributing

Thank you for looking at IC Auto Opt Workflow.

This project is early v0.1 software for file-driven analog/RF optimization with
Cadence Spectre/OCEAN and OpenBox. Contributions should keep the product goal
simple:

```text
opt_requirement.md -> ic-opt PROJECT --real -> reports
```

## Development Setup

Use one repository-level Python environment:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e .
```

## Before Sending Changes

Run focused tests for the area you changed. For broad packaging changes, run:

```bash
./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_requirement_intake.py tests/test_openbox_backend.py tests/test_optimizer_task_package.py tests/test_toolchain_env.py -q
./.venv/bin/python -m ruff check src tools
```

## Contribution Boundaries

- Do not commit `.venv`, generated project artifacts, PSF databases, raw
  Spectre output, Cadence logs, PDK files, or private Maestro point roots.
- Do not hardcode machine-specific paths or Spectre versions.
- Do not rewrite user-approved OCEAN formulas in code.
- Do not replace the file-contract workflow with ad hoc chat-only behavior.
- Keep new features narrow, real-flow oriented, and backed by tests.

## License

By contributing, you agree that your contributions are provided under the
project's MIT License. See `LICENSE`.
