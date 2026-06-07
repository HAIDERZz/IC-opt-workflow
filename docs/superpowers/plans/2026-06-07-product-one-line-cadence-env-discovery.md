# C-59 Product One-Line Cadence Environment Discovery

## Status

Completed, verified-only.

## Goal

Reduce product-entry friction so the common user-facing shape can be:

```bash
ic-opt PROJECT_DIR --real
```

or in supervisor-agent sessions:

```text
/ic-opt PROJECT_DIR --real
```

without requiring a long prompt or a repeated `--cadence-cshrc` flag every run.
The Cadence environment path is still user supplied; C-59 only supports
remembering or locating that user-provided anchor.

## Scope

Add a narrow Cadence cshrc discovery layer to the product `ic-opt` entrypoint
only. The lower-level `hermes-workflow optimize` command remains explicit and
strict.

User-supplied anchor discovery order:

1. explicit `--cadence-cshrc PATH`;
2. `PROJECT_DIR/cadence_env.csh`;
3. environment variable `IC_OPT_CADENCE_CSHRC`;
4. user config `~/.ic-opt/cadence_env.csh`.

If none exists, fail closed with a short actionable message. Do not infer random
`.bashrc`/`.zshrc` content and do not hardcode a Spectre version.

Completion evidence:

- `ic-opt --cadence-cshrc` is optional.
- `ic-opt --help` shows `ic-opt [OPTIONS] PROJECT_DIR`; `--cadence-cshrc` is
  not required.
- Product CLI tests cover explicit override, project-local discovery,
  `IC_OPT_CADENCE_CSHRC`, and fail-closed missing env.
- One-line dry orchestration passed at
  `/tmp/ic_auto_opt_c59_dry_5J81NM/Mixer_opt_muti_tb` using
  `PROJECT_DIR/cadence_env.csh`:

```bash
./.venv/bin/ic-opt /tmp/ic_auto_opt_c59_dry_5J81NM/Mixer_opt_muti_tb \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 12
```

## Tasks

### Task 1: Product Entrypoint Env Discovery

Status: Complete.

- Make `ic-opt --cadence-cshrc` optional.
- Resolve the Cadence cshrc from the discovery order above.
- Pass the resolved path to the existing optimizer flow.
- Do not change optimizer math, metric formulas, multi-testbench aggregation, or
  low-level `hermes-workflow optimize` validation.

### Task 2: Tests

Status: Complete.

- Cover explicit override.
- Cover project-local `cadence_env.csh`.
- Cover `IC_OPT_CADENCE_CSHRC`.
- Cover fail-closed missing env.

### Task 3: Docs And State

Status: Complete.

- Update product quickstart and agent manual to describe one-line invocation and
  discovery order.
- Update current state/progress files with the C-59 checkpoint.

## Non-Goals

- No new optimizer features.
- No real Spectre/OCEAN run unless a later acceptance task explicitly asks for
  it.
- No per-project Python virtualenv.
- No Spectre version hardcoding.
- No natural-language requirement parser.
