# GitHub Publishing Guide

Target repository:

```text
HAIDERZz/IC-opt-workflow
```

The project is released under the MIT License. Keep proprietary Cadence, PDK,
and project artifacts out of the source repository.

## Publish Contents

Publish source-package contents such as:

```text
README.md
pyproject.toml
requirements-product.txt
requirements-advanced.txt
src/
docs/
examples/
skills/
vendor/
tests/
tools/
RELEASE_NOTES_v0.1.7.md
LICENSE
```

`tests/` is intentionally kept so developers can verify parser, workflow,
optimizer, reporting, and agent skill behavior.

## Do Not Publish User Artifacts

Do not commit:

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
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests
git diff --check -- . ':!vendor' ':!.serena'
```

Use the site's Python 3.11+ command if `python3` is older than 3.11.

Run a sensitive-path scan from the parent directory before pushing. Use markers
that match your own workstation paths, usernames, temporary run prefixes, and
private storage mounts:

```bash
grep -R -n "<LOCAL_HOME_MARKER>\\|<USER_NAME>\\|<PRIVATE_TMP_PREFIX>\\|<PRIVATE_STORAGE_MARKER>" ic-auto-opt-workflow-v0.1
```

Expected result: no output.

## Push

From the package root:

```bash
git status --short
git add .
git commit -m "release: v0.1.7"
git push origin main
git tag -f v0.1.7
git push -f origin v0.1.7
```

Use `RELEASE_NOTES_v0.1.7.md` for GitHub release notes.
