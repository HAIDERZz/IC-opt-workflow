# Claude /ic-opt Continuation Validation 2026-06-07

Status: verified-only.

This note records a real product-landing validation using the current Claude
runtime adapter. It tested both the first short user command and the follow-up
user request to continue optimization.

## Project

```text
/tmp/ic_auto_opt_c66_claude_real_e2e/Mixer_opt_muti_tb
```

The project was prepared as a fresh user-style directory with only:

```text
opt_requirement.md
cadence_env.csh
```

No generated `config/`, `netlists/`, `runs/`, `reports/`, `ledger/`, or
`state/` artifacts were copied from the source project.

## First User Command

```text
/ic-opt /tmp/ic_auto_opt_c66_claude_real_e2e/Mixer_opt_muti_tb --real --max-evals 100 --batch-size 10 --parallel-jobs 10
```

Run through:

```text
claude -p --dangerously-skip-permissions
```

Result:

- The Claude `/ic-opt` adapter entered the real optimizer route.
- The flow completed 100 real OpenBox/Spectre/OCEAN multi-testbench
  evaluations.
- `reports/optimizer_decision_report.md` was generated.
- The reported recommendation was feasible `real_066`.

Recommended point:

```text
run_id: real_066
F=26
L=40n
VB_LO=310m
W=1u
BW=19.17 GHz
IIP3=3.21 dBm
MAX_GAIN=4.24 dB
NF_3G=11.81 dB
P1DB=-0.90 dBm
objective=-0.0503
```

The run reported `global_optimum_claim=false`. This is best-observed evidence,
not a global optimum proof.

## Follow-Up User Command

After the first result, the simulated user sent only:

```text
请再进行40个点的优化
```

The Claude session correctly mapped the short follow-up request to:

```text
hermes-workflow continue-openbox-real \
  /tmp/ic_auto_opt_c66_claude_real_e2e/Mixer_opt_muti_tb \
  --additional-evals 40 \
  --batch-size 10 \
  --parallel-jobs 12 \
  --cadence-cshrc /tmp/ic_auto_opt_c66_claude_real_e2e/Mixer_opt_muti_tb/cadence_env.csh
```

This proves the agent did not merely stay in a chat loop; it attempted the real
continuation command.

## Continuation Result

The continuation did not append evaluations.

Observed evidence:

```text
reports/optimizer_evaluations.jsonl: 100 rows
ledger/experiment_ledger.jsonl: 84 rows
new OpenBox log: reports/openbox_workdir/hermes_openbox_real_2026-06-07-18-32-36-342837.log
```

The new OpenBox log stopped after advisor initialization and before any
Spectre/OCEAN child process appeared. The Claude command eventually returned:

```text
Continuation Failed — Search Space Exhausted
OpenBox was unable to generate enough unique candidate points — only 8 out of
the requested 10 per batch could be produced after 300 deduplication attempts.
```

The current best candidate remained `real_066`.

## Interpretation

The validation result is mixed:

- Initial one-line Claude `/ic-opt ... --real` real optimization: passed.
- Follow-up natural continuation request parsing: passed.
- Follow-up continuation execution to +40 evaluations: failed.

The failure is not a Spectre/OCEAN tool failure and not an OCEAN formula issue.
It is a product continuation strategy issue: the continuation command can fail
when OpenBox cannot fill the requested `batch_size` with unique candidates
after a prior 100-evaluation run.

## Required Next Product Fix

Before claiming post-result continuation is product-ready, add a narrow
continuation hardening task:

- make continuation resilient when the full requested batch cannot be filled;
- either auto-shrink the candidate batch, continue with a partial unique batch,
  or fail before launching with a concise report that tells the supervisor what
  action is needed;
- keep the behavior file-driven and short-request driven;
- do not add fake-run ladders, new optimizer frameworks, PSF parsing, OCEAN
  formula rewrites, or hand-picked optimizer points.

