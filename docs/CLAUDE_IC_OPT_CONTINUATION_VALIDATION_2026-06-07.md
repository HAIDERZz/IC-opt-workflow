# Claude /ic-opt Continuation Validation 2026-06-07

> Historical command notice: command examples in this evidence note may show
> old workload/resource CLI flags. Current release product first runs read those
> values only from `opt_requirement.md`; only `ic-opt PROJECT --real --continue N`
> remains as a product CLI budget delta.

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

## Original Continuation Result

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
Continuation failed: search space exhausted
OpenBox was unable to generate enough unique candidate points: only 8 out of
the requested 10 per batch could be produced after 300 deduplication attempts.
```

The current best candidate remained `real_066`.

## Hardening Verification

The exposed continuation issue has a narrow code fix:

- `continue-openbox-real` accepts partial unique batches instead of failing only
  because OpenBox could not fill the full requested batch.
- OpenBox continuation model replay is capped at 40 prior traces. The full
  optimizer ledger is still preserved for reports and duplicate detection.
- `continue-openbox-real` repairs a missing base
  `execution_package/execution_manifest.json` before running.
- Generated continuation task packages no longer hardcode `--parallel-jobs`;
  they inherit `config/spectre.yaml` unless the user explicitly requests a
  resource change.

Targeted tests passed:

```text
tests/test_openbox_backend.py
tests/test_optimizer_task_package.py
tests/test_product_cli.py
tests/test_optimizer_completion.py
tests/test_optimizer_finalize.py
tests/test_optimizer_status.py
tests/test_optimizer_decision.py
```

Real repair validation on the same project reached:

```text
reports/optimizer_evaluations.jsonl: 140 rows
optimizer_run_report.evaluation_count: 140
optimizer_run_report.openbox.continuation.model_replay_evaluation_count: 40
status_counts: constraint_failed=95, feasible=29, metric_check_failed=16
best candidate: real_066
```

Important caveat: during manual repair validation, the first 100 evaluations
used the project `parallel_jobs=12`, while a manual repair command used
`--parallel-jobs 10`. `check-optimizer-run` correctly rejected that mixed
resource history as `Spectre setting drift detected: parallel_jobs`. The
product fix is therefore not to loosen acceptance, but to ensure generated
continuation commands inherit project resources by default.

## Interpretation

The validation result is now split:

- Initial one-line Claude `/ic-opt ... --real` real optimization: passed.
- Follow-up natural continuation request parsing: passed.
- The original follow-up continuation execution exposed a real product bug.
- The continuation hardening fix is implemented and directly validated to
  reach 140 cumulative evaluations, with the resource-inheritance caveat above.

The original failure was not a Spectre/OCEAN tool failure and not an OCEAN
formula issue. It was a product continuation strategy issue: OpenBox could fail
when it could not fill the requested `batch_size` with unique candidates after
a prior 100-evaluation run.

## Next Product Drill

Run a clean runtime-agent continuation drill using the generated continuation
task package, with no manual `--parallel-jobs` override. The acceptance checker
should continue to reject mixed-resource ledgers.
