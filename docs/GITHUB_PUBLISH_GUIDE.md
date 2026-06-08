# GitHub Publishing Guide

This guide is for publishing the v0.1 source package to GitHub for the first
time.

## Target Repository

Current intended repository:

```text
HAIDERZz/IC-opt-workflow
```

The repository is released under the MIT License. Keep proprietary Cadence,
PDK, and project artifacts out of the source repository.

## What To Publish

Publish the source repository contents:

```text
README.md
pyproject.toml
requirements-product.txt
src/
docs/
examples/
skills/
vendor/
tests/
tools/
RELEASE_NOTES_v0.1.md
LICENSE
```

`tests/` is intentionally kept in the GitHub source repository so other
developers can verify parser, workflow, optimizer, reporting, and agent skill
behavior.

## What Not To Publish

Do not commit user/project generated artifacts:

```text
.venv/
runs/
reports/
ledger/
state/
execution_package/
config/
netlists/
psf/
*.log
input.scs
cadence_env.csh
```

Do not publish private Cadence setup files, PDK files, real Maestro point-root
bundles, PSF databases, license server information, or machine-specific paths.

## Required Pre-Publish Checks

From the package root:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pytest tests/test_product_cli.py tests/test_requirement_intake.py tests/test_openbox_backend.py tests/test_optimizer_task_package.py tests/test_toolchain_env.py -q
./.venv/bin/python -m ruff check src tools
```

Run a sensitive-path scan from the parent directory before pushing. Use markers
that match your own workstation paths, usernames, temporary run prefixes, and
private storage mounts:

```bash
grep -R -n "<LOCAL_HOME_MARKER>\\|<USER_NAME>\\|<PRIVATE_TMP_PREFIX>\\|<PRIVATE_STORAGE_MARKER>" ic-auto-opt-workflow-v0.1
```

Expected result: no output.

## First Git Push

From the package root:

```bash
git init
git add .
git commit -m "release: v0.1.0"
git branch -M main
git remote add origin git@github.com:HAIDERZz/IC-opt-workflow.git
git push -u origin main
```

If SSH is not configured, use the HTTPS remote instead:

```bash
git remote add origin https://github.com/HAIDERZz/IC-opt-workflow.git
```

## Optional v0.1 Tag And Release

After the first push:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Then create a GitHub release from tag `v0.1.0` and use
`RELEASE_NOTES_v0.1.md` as the release notes.

## License Status

The project uses the MIT License. See `LICENSE`.
