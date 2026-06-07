# C-60 Product One-Line Real Acceptance

## Status

Completed, verified-only.

## Goal

Verify the product landing shape with a real optimizer run:

```bash
ic-opt PROJECT_DIR --real
```

The run must use a user-supplied project-local `cadence_env.csh` and must not
pass `--cadence-cshrc`.

## Evidence

Workspace:

```text
/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb
```

Preparation:

- Copied only `opt_requirement.md` from the user project.
- Copied the known-good Mixer Cadence/Spectre setup wrapper to
  `PROJECT_DIR/cadence_env.csh`.
- Did not copy old `runs/`, `reports/`, `ledger/`, or `state/`.

Command:

```bash
./.venv/bin/ic-opt /tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb \
  --real \
  --max-evals 100 \
  --batch-size 10 \
  --parallel-jobs 10
```

Result:

- Flow status: `pass`.
- Evaluations: `100`.
- Status counts: `68 constraint_failed`, `16 feasible`,
  `16 metric_check_failed`.
- Recommended action: `accept_best_observed_or_continue`.
- Recommended run: `real_051`.
- Global optimum claim: `false`.
- OpenBox advanced visualization: `generated`.

Recommended candidate:

```text
F=30
L=40n
VB_LO=310m
W=0.8u
BW=19592140591.69946
MAX_GAIN=4.028875688617442
NF_3G=11.79754488809267
IIP3=3.2821304958007
P1DB=-0.8653580069775275
```

Score summary:

```text
combined_score=0.2791539642565037
bottleneck_metric=MAX_GAIN
bottleneck_score=0.05775137723488477
weighted_score=0.7957600006402812
```

## Route Audit

- Aligned with C-58/C-59 product landing route.
- `ic-opt` discovered `PROJECT_DIR/cadence_env.csh` without requiring
  `--cadence-cshrc`.
- No optimizer math, OCEAN formula, Spectre version, multi-testbench
  aggregation, or product environment contract changed.
- This is best-observed evidence only, not a global optimum proof.
