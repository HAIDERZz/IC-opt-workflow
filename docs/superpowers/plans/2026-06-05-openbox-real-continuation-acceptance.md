# C-39 OpenBox Real Continuation Acceptance Plan

Date: 2026-06-05

## Goal

Validate C-38 continuation on a real, previously accepted OpenBox optimizer
project without mutating the canonical C-34 evidence directory.

## Scope

This is a practice-backed real-tool acceptance task, not a new optimizer feature.

In scope:

- Copy the known-good C-34 OpenBox project to a C-39 `/tmp` workspace.
- Run `check-toolchain-env` before real execution.
- Run `continue-openbox-real` for a small additional batch.
- Run `check-optimizer-run`, `summarize-optimizer-run`, and
  `finalize-optimizer-run`.
- Record sanitized evidence under `docs/debug/`.

Out of scope:

- Changing optimizer logic.
- Running a fresh 100-evaluation optimizer job.
- Replacing TuRBO or deleting native TuRBO.
- Python PSF parsing.
- OCEAN formula rewriting.
- Committing raw Cadence artifacts or `/tmp` workspaces.

## Route Audit

- Active spec: `docs/superpowers/specs/2026-06-05-openbox-continuation-multi-run-workflow-design.md`
- Active implementation: C-38 commit `2a46c1f`
- Toolchain reference: `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`
- Alignment: C-39 proves the accepted C-38 continuation command on the real
  OpenBox/Spectre/OCEAN path and then uses existing C-25/C-26/C-32 closeout.
- Drift: None intended. This acceptance task does not create new contracts or
  broaden optimizer behavior.

## Commands

Prepare copied workspace:

```bash
rm -rf /tmp/ic_auto_opt_c39
mkdir -p /tmp/ic_auto_opt_c39
cp -a /tmp/ic_auto_opt_c34_clean2/bridge_test_inv /tmp/ic_auto_opt_c39/bridge_test_inv
```

Toolchain gate:

```bash
.venv/bin/hermes-workflow check-toolchain-env \
  --openbox-venv /tmp/ic_auto_opt_openbox_spike/.venv \
  --cadence-cshrc /home/zzchen/cadence_ic231_env.csh \
  --report /tmp/ic_auto_opt_c39/toolchain_environment_report.json
```

Real continuation command:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH; setenv MPLCONFIGDIR /tmp/ic_auto_opt_c39/mpl_cache; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; hermes-workflow continue-openbox-real /tmp/ic_auto_opt_c39/bridge_test_inv --additional-evals 20 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

Closeout:

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c39/bridge_test_inv
.venv/bin/hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_c39/bridge_test_inv
.venv/bin/hermes-workflow finalize-optimizer-run /tmp/ic_auto_opt_c39/bridge_test_inv
```

## Acceptance Criteria

- Toolchain gate passes.
- `continue-openbox-real` completes without workflow-level real-tool failure.
- Cumulative `reports/optimizer_run_report.json` has:
  - `backend=openbox`
  - `execution_mode=real`
  - `evaluation_count=120`
  - `openbox.continuation.enabled=true`
  - `openbox.continuation.prior_evaluation_count=100`
  - `openbox.continuation.additional_evals=20`
- The new run ids start after the prior C-34 run ids.
- `check-optimizer-run` accepts the cumulative artifacts.
- `finalize-optimizer-run` completes.
- Sanitized evidence is recorded without raw PSF, `input.scs`, or full Cadence
  logs.

## Result

Status: complete, verified-only.

Actual workspace:

```text
/tmp/ic_auto_opt_c39_continuation_002/bridge_test_inv
```

First attempt:

- Workspace: `/tmp/ic_auto_opt_c39_continuation_001/bridge_test_inv`
- Result: failed before Spectre/OCEAN with `optimizer state is completed`.
- Root cause: C-38 continuation could warm-start reports/traces, but explicit
  candidate package preparation still rejected a prior completed optimizer
  state.
- Fix: add a continuation-only allowance for explicit OpenBox candidate
  packaging. Normal non-continuation completed/stopped-state guards remain in
  place.

Second attempt:

- Toolchain gate passed with `/tmp/ic_auto_opt_c39_toolchain_probe_002.json`.
- `continue-openbox-real` completed `120` cumulative evaluations.
- `check-optimizer-run`: accepted.
- `summarize-optimizer-run`: `accept_best_observed`, confidence `medium`,
  `global_optimum_claim=false`.
- `finalize-optimizer-run`: passed.
- Continuation metadata: prior `100`, additional `20`, target `120`.
- New run ids: `real_101` through `real_120`.
- New continuation statuses: `15 feasible`, `5 constraint_failed`, `0`
  `metric_check_failed`, `0 real_check_failed`.
- Cumulative statuses: `58 feasible`, `56 constraint_failed`, `6`
  `metric_check_failed`.
- Best observed remained `real_071`.

Sanitized evidence:

```text
docs/debug/2026-06-05-c39-openbox-real-continuation-acceptance.md
```
