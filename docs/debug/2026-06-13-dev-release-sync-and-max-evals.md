# Dev/Release Sync And Max Evals Precedence

## Context

After C76 multi-corner work and C77 optimizer-mode work, the development package
and the v0.1 release package diverged. Several release product files existed in
the development tree only as untracked files, while C77 optimizer files also
remained untracked. This made local execution depend on files that would not be
included in a normal commit.

## Root Causes

- `ic-opt --max-evals` defaulted to `100` in the product CLI, so omitting the
  option still overrode `config/optimizer.yaml` / `opt_requirement.md`.
- `optimizer_flow.optimize_project()` and
  `remote_optimizer_flow.optimize_remote_project()` still typed the evaluation
  budget as a required integer, so the fixed CLI `None` semantics were not
  represented through the flow boundary.
- v0.1.6 product hardening files, packaged agent skill files, examples, release
  docs, and vendored OpenBox files were present in the release package but not
  tracked by the development package.

## Fixes Applied

- Changed product CLI `--max-evals` default to `None` and passed the value
  through local and remote flows.
- Allowed `optimizer_flow` and `remote_optimizer_flow` to accept `None` for
  `max_evals`; explicit positive integers still validate.
- Synchronized v0.1.6 structured remote doctor, package metadata, advanced
  requirements, packaged/root agent skill, release docs, examples, and vendored
  OpenBox files into the development package index.
- Kept C77 strategy options in development CLI paths instead of overwriting them
  with v0.1.6 code.

## Verification

- `python -m pytest tests/test_product_cli.py tests/test_product_cli_remote.py tests/test_remote_doctor.py tests/test_product_doctor.py tests/test_agent_skill.py tests/test_optimizer_flow.py tests/test_remote_optimizer_flow.py tests/test_optimizer_strategy.py tests/test_optimizer_effectiveness.py`
- `python -m pytest tests/test_product_cli.py tests/test_product_cli_remote.py tests/test_remote_doctor.py tests/test_product_doctor.py tests/test_agent_skill.py tests/test_optimizer_flow.py tests/test_remote_optimizer_flow.py tests/test_optimizer_strategy.py tests/test_optimizer_effectiveness.py tests/test_openbox_backend.py tests/test_native_turbo.py tests/test_requirement_intake.py`
- `python -m pytest -q`
- `python -m ruff check src tests`
- `git diff --check`
- `python tools/check_development_cadence.py`
