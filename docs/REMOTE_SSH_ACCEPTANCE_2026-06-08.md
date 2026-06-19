# C-69 Remote SSH Orchestration Evidence And C-70 Parity Correction

Date: 2026-06-08

## Implementation Status

C-69 remote SSH mode is implemented as SSH/product-route plumbing, but its
Spectre/OCEAN adapter is no longer accepted as production-equivalent to the
local proven adapter.

Post-acceptance artifact inspection found that the C-69 remote adapter
hand-built Spectre/OCEAN commands and success manifests instead of delegating to
the local adapter semantics. Therefore this document is retained as evidence
that SSH orchestration, remote project/cache routing, doctor, report mirroring,
and continuation routing can work. It is not sufficient evidence that remote
Spectre/OCEAN is correct.

The correction is tracked by:

```text
docs/superpowers/specs/2026-06-08-remote-spectre-ocean-local-parity-design.md
docs/superpowers/plans/2026-06-08-remote-spectre-ocean-local-parity.md
```

C-70 local/unit implementation status as of 2026-06-09:

- implemented in commits `4fb3d29` and `84afe18`;
- remote mode reuses canonical local Spectre/OCEAN argv wrappers;
- remote mode validates required PSF/log/scalar artifacts;
- remote mode delegates result and metric manifest semantics to local helpers;
- remote mode preserves multi-testbench aggregation;
- targeted tests passed with `98 passed`;
- full pytest passed with `733 passed, 1 warning`;
- real remote parity acceptance remains pending user authorization.

The intended route remains:

- local workstation runs `ic-opt`, OpenBox/controller logic, closeout checks,
  and report interpretation;
- remote Linux EDA host runs Spectre/OCEAN through user-configured
  passwordless OpenSSH;
- the remote project directory remains the source of truth;
- local reports are mirrored under `~/.ic-opt/remote_runs/`;
- no OpenBox or `ic-auto-opt-workflow` Python package installation is required
  on the remote EDA server.

## Real Remote Target

- SSH profile: `zzchen@10.113.216.131`
- Clean remote project:
  `/home/zzchen/remote_opt/mixer_muti_tb_c69_accept_20260608_001`
- Local cache mirror:
  `/home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/150c658badc47d17`

The SSH host key was accepted by the user before product commands were run, and
passwordless SSH was verified with:

```bash
ssh -o BatchMode=yes zzchen@10.113.216.131 true
```

## Doctor Acceptance

Command:

```bash
./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 \
  /home/zzchen/remote_opt/mixer_muti_tb_c69_accept_20260608_001 --doctor
```

Result:

```text
remote doctor completed
remote report: /home/zzchen/remote_opt/mixer_muti_tb_c69_accept_20260608_001/reports/ic_opt_doctor_report.json
local report: /home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/150c658badc47d17/reports/ic_opt_doctor_report.json
```

## Real Remote Smoke Result

Command:

```bash
./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 \
  /home/zzchen/remote_opt/mixer_muti_tb_c69_accept_20260608_001 \
  --real --max-evals 10 --batch-size 2 --parallel-jobs 2
```

Result:

- `ic-opt` exited successfully.
- `hermes-workflow check-optimizer-run` accepted the local mirror.
- `reports/optimizer_run_report.json` recorded `evaluation_count=10`.
- All 30 child testbench result manifests succeeded.
- All 10 aggregate result manifests succeeded.
- All 10 aggregate metric manifests failed at metric validation, not at the
  remote Spectre/OCEAN tool layer.
- `reports/optimizer_decision_report.md` recommended no primary run because no
  feasible/scalar candidate was available.

Metric failure classification for this user-provided remote project:

- `BW`: expression error on 10 candidates
- `MAX_GAIN`: expression error on 10 candidates
- `NF_3G`: non-scalar on 10 candidates
- `IIP3`: non-scalar on 10 candidates
- `P1DB`: expression error on 10 candidates

This result is downgraded to a remote orchestration smoke. It proves that the
product can drive SSH commands and sync reports, but it does not prove
Spectre/OCEAN local-parity correctness.

Known C-70 blocker:

- the remote adapter could report success while required child `psf/` artifacts
  were missing from the local mirror;
- the remote adapter used a hand-built Spectre command instead of the local
  canonical adapter command;
- the remote adapter used OCEAN `-restore` instead of the local canonical
  `-replay ... -log ...` command;
- failed scalar rows could still leave child-level success claims.

The current project formulas must not be changed to compensate for this
adapter/layout bug. C-70 must first make remote mode execute and materialize the
same artifacts as local mode.

## Remote Continuation Acceptance

Command:

```bash
./.venv/bin/ic-opt --ssh-profile zzchen@10.113.216.131 \
  /home/zzchen/remote_opt/mixer_muti_tb_c69_accept_20260608_001 \
  --continue 4 --batch-size 2 --parallel-jobs 2
```

Result:

```text
remote continuation completed
local report: /home/zzchen/.ic-opt/remote_runs/zzchen@10.113.216.131/150c658badc47d17/reports/optimizer_flow_run_report.json
```

Acceptance checks:

- `hermes-workflow check-optimizer-run` accepted the refreshed local mirror.
- Local `reports/optimizer_run_report.json` recorded `evaluation_count=14`.
- Local `reports/optimizer_evaluations.jsonl` contained 14 rows.
- Remote `reports/optimizer_run_report.json` also recorded
  `evaluation_count=14`.
- Remote `reports/optimizer_evaluations.jsonl` also contained 14 rows.
- Status counts after continuation: `{"metric_check_failed": 14}`.
- Flow closeout steps passed: `run-openbox-real`, `check-optimizer-run`,
  `summarize-optimizer-run`, `finalize-optimizer-run`,
  `visualize-optimizer-run`, and `decide-optimizer-run`.

## Local Regression Evidence

After the remote multi-testbench and remote symlink-materialization fixes:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check src tests
./.venv/bin/python tools/check_development_cadence.py
git diff --check
```

Results:

- Full pytest: `718 passed, 1 warning`
- Ruff: passed
- Development cadence check: passed
- Whitespace diff check: passed

## Preserved Design Compliance

- Passwordless SSH is user-configured; the product does not manage passwords or
  private keys.
- The remote project remains the source of truth and receives refreshed
  reports.
- Local cache mirror is deterministic:
  `~/.ic-opt/remote_runs/<profile>/<hash>/`.
- Remote mode does not require the product Python environment on the EDA
  server.
- Remote Spectre/OCEAN commands do not hardcode a Spectre version.
- No PSF parsing, no OCEAN formula rewrite, and no synthetic merged
  multi-testbench deck were introduced.
- Maestro/ADE symlinks are validated against the remote Maestro history root
  before dereferenced transfer into the local controller cache.

## Not Yet Accepted After C-69

Before remote Spectre/OCEAN can be called production-accepted, C-70 must prove:

- remote Spectre uses the same argv as the local adapter;
- remote OCEAN uses the same argv as the local adapter;
- remote PSF/log/scalar artifacts are downloaded before manifest writing;
- success manifests cannot reference missing artifacts;
- failed requested metric rows produce failed metric manifests exactly as local
  mode does;
- at least one real remote parity check matches known local multi-testbench
  artifact behavior.
