# Toolchain Execution Reference

Use this before running Virtuoso, Spectre, OCEAN, OpenBox, native TuRBO,
license probes, optimizer commands, or fix-run commands from the release
package.

## Product Commands

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
./.venv/bin/ic-opt PROJECT_DIR --real
./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`--dry-orchestration` is local-only: it cannot be combined with
`--ssh-profile` or `--continue`, it requires `--real`, and it is not
supported for a `fix_run` workflow (it is a first-run `optimize`-workflow
flag). Remote mode (`--ssh-profile PROFILE`) requires exactly one of
`--doctor`, `--real`, or `--real --continue N`; the CLI rejects a remote
invocation that supplies none of the three.

`opt_requirement.md` supplies workflow mode, initial-run budget, batch size,
Spectre parallelism, Spectre thread count, optimizer CPU cap, algorithm,
strategy, initialization, process corners, output format, metric formulas,
objective, constraints, fixed points, and waveform exports.

`--continue N` only appends `N` evaluations to the existing budget. Algorithm,
strategy, batch size, and every other optimizer setting are resolved from
`config/optimizer.yaml` by the backend resolver, not recorded on the CLI
invocation. Both OpenBox and native TuRBO continuation are supported; enabled
History Warm Start remains an OpenBox-only new-project capability and cannot
be combined with `--continue` (see
[ROLE_MODEL_AND_TERMINOLOGY.md](ROLE_MODEL_AND_TERMINOLOGY.md), "History Warm
Start").

## Product Environment

IC Auto Opt requires Python 3.11 or newer for the interpreter used to create
the virtual environment (`pyproject.toml` declares `requires-python = ">=3.11"`,
and the source uses 3.11-only syntax). EDA servers often ship an older default
`python3`; use the site's `python3.11` (or newer) command if so.

Install from the release root:

```bash
python3 -m venv .venv   # use python3.11 (or newer) here if the site python3 is older
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

Import check:

```bash
./.venv/bin/python -c "
import sys
from hermes_workflow.native_turbo import DEFAULT_TURBO_PATH
sys.path.insert(0, str(DEFAULT_TURBO_PATH))
import openbox, turbo, torch, gpytorch, scipy, threadpoolctl, matplotlib, numpy, hermes_workflow
print('product optimizer env ok')
"
```

`requirements-product.txt` does not pip-install `turbo` (see "Native TuRBO
Resolution" below), so a bare `import turbo` fails unless `DEFAULT_TURBO_PATH`
is inserted into `sys.path` first, as this check does; plain `import
hermes_workflow` does not trigger that insertion itself, since it only
happens inside the native TuRBO entry-point functions. `matplotlib` backs
`visualize-optimizer-run`; `numpy` is imported directly by the native TuRBO
adapter. Neither is checked by `check-toolchain-env` below, so this manual
import check is the only coverage for them.

The low-level `check-toolchain-env` command only verifies the OpenBox path: it
runs `import openbox` and `import hermes_workflow.openbox_backend` in the
target Python, and separately checks that the venv directory, `bin/python`,
`bin/hermes-workflow`, and the Cadence cshrc file exist. It does **not**
import or otherwise check `turbo`, `torch`, `gpytorch`, `scipy`, or
`threadpoolctl` — a project using `algorithm: turbo` can pass
`check-toolchain-env` while native TuRBO is completely unusable. Use the
import check above (or the "Native TuRBO Resolution" section below) to
validate a TuRBO environment. Also note that `check-toolchain-env` defaults
`--cadence-cshrc` to `~/.ic-opt/cadence_env.csh` directly — it does **not**
walk the "Local discovery order" described under "Cadence Environment" below;
pass `--cadence-cshrc` explicitly if the project or `IC_OPT_CADENCE_CSHRC`
supplies a different path.

It checks the environment containing the invoked `hermes-workflow` unless
`--openbox-venv PATH` is supplied. A portable optimizer task package likewise
omits the packaging machine's venv path by default and records an explicit
path only when requested. Packaged post-run audit commands also record
`--expected-backend`, so a task cannot validate artifacts left by a different
optimizer backend. `package-optimizer-task` resolves its default backend from
project configuration; an explicit `--backend` must agree with that resolved
backend.

## Native TuRBO Resolution

Native TuRBO is not installed like a normal package; it is resolved from a
path at import time. `DEFAULT_TURBO_PATH` is
`TURBO_HOME` if that environment variable is set, else
`<release_root>/vendor/TuRBO`, where `<release_root>` is computed as two
parents above the `hermes_workflow` package directory
(`Path(__file__).resolve().parents[2]`). Every native TuRBO entry point
prepends this path with `sys.path.insert(0, ...)` before importing `turbo`.

- The `parents[2]` fallback only lands on the correct `vendor/TuRBO` when
  `hermes_workflow` is installed editable from the release root (the
  `-e .` line in `requirements-product.txt`). A non-editable install, or a
  release root that has been moved after install, breaks the fallback and
  native TuRBO import fails.
- `requirements-product.txt` does not install `turbo` via pip at all;
  `sys.path.insert(0, ...)` is the only mechanism that makes `turbo`
  importable. It runs unconditionally and takes priority over any `turbo`
  package installed by other means (for example, a stray `pip install
  turbo` into the same environment). If `TURBO_HOME` is set to the wrong
  tree, native TuRBO silently imports that wrong `turbo` package instead of
  raising an error — verify `TURBO_HOME` points at the intended
  `vendor/TuRBO` checkout before relying on it.

## Remote Attempt Lock

Every remote `--real` and `--real --continue N` invocation first claims an
exclusive attempt lock on the Remote project before touching anything else,
via `begin_remote_optimizer_attempt`. The lock is a directory,
`state/remote_attempt.lock`, created atomically (`mkdir`) **inside the Remote
project directory** (not the Controller Cache), holding `token` and
`owner.json` (Controller hostname, PID, SSH profile, acquisition time).

If another Controller already holds the lock, the command fails immediately
with an error naming the lock directory and pointing at `owner.json`:
`remote project already has an active optimization attempt: <lock_dir>.
Inspect <owner_path> before manually removing a stale lock.` Locks are
**deliberately never stolen automatically** — if a Controller process dies
while holding the lock, an operator must inspect `owner.json` and manually
remove `state/remote_attempt.lock` on the Remote host before another
Controller can attempt that project again. There is no CLI flag to force or
steal the lock.

## Cadence Environment

Local and remote runs resolve the Cadence cshrc from **different, non-
overlapping** sources. Do not infer shell startup files. Do not hardcode a
Spectre version.

### Local discovery order (no `--ssh-profile`)

`ic-opt PROJECT_DIR ...` discovers the user-approved Cadence setup in this
order, using the first candidate that exists as a file:

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

### Remote lookup (`--ssh-profile PROFILE`)

`ic-opt --ssh-profile PROFILE PROJECT_DIR ...` does **not** use the four-level
local order above. `IC_OPT_CADENCE_CSHRC` and `~/.ic-opt/cadence_env.csh` are
never consulted for a remote run. Instead:

```text
--cadence-cshrc PATH    (interpreted as a path on the Remote host)
else REMOTE_PROJECT_DIR/cadence_env.csh
```

If `--cadence-cshrc` is supplied on a remote invocation, its value is treated
as a POSIX path to be resolved **on the Remote host**, not on the Controller.
If it is omitted, the only fallback is `cadence_env.csh` inside the Remote
project directory itself — there is no environment-variable or
user-home-directory fallback on the remote path. Setting
`IC_OPT_CADENCE_CSHRC` on the Controller machine has no effect on a remote
run.

## Real Workflow Evidence

Evidence paths differ between local and remote runs. All paths below are
relative to a project root; which project root that is depends on mode.

### Local runs

After a local real run (`ic-opt PROJECT_DIR --real ...`), `PROJECT_DIR` holds
the full evidence set directly:

```text
config/optimizer.yaml
config/spectre.yaml
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_flow_run_report.json
reports/optimizer_run_acceptance_report.json
reports/optimizer_run_report.json               (OpenBox backend)
reports/native_turbo_optimizer_report.json       (native TuRBO backend)
reports/optimizer_effectiveness_audit.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.json            (also .md, .html)
reports/optimizer_final_summary.json             (also .md)
reports/multi_testbench_aggregation_report.json  (multi-testbench/corner only)
reports/fix_run_report.json                      (fix_run workflow only)
state/optimizer_state.json
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
supervisor_instruction.json                      (project root, not reports/)
```

`reports/optimizer_run_report.json` is written by the OpenBox backend only.
Native TuRBO writes `reports/native_turbo_optimizer_report.json` +
`reports/native_turbo_optimizer_evaluations.jsonl` instead (the OpenBox-named
pair is still accepted as a legacy alias by post-run audit tooling, but a
TuRBO project will not produce it). Check which backend ran before assuming
either file name exists.

Recommended read order: `optimizer_flow_run_report.json` (did the whole
`ic-opt --real` invocation pass) -> `optimizer_run_acceptance_report.json`
(was the run accepted) -> the backend-specific report -> aggregation /
effectiveness / insight reports for detail.

### Remote runs (`--ssh-profile PROFILE`)

A remote run's authoritative evidence lives on the **Remote** host, under
`REMOTE_PROJECT_DIR`, with the same relative layout as the local list above.
The Controller only ever has a partial, transient copy in the **Controller
Cache** at `~/.ic-opt/remote_runs/<ssh_profile>/<sha256(profile + remote_dir)[:16]>`:

- `config/optimizer.yaml`, `config/spectre.yaml`, and the rest of `config/`
  are written **only** into the Controller Cache during preparation. They are
  **never synced back to the Remote project** — do not expect
  `REMOTE_PROJECT_DIR/config/optimizer.yaml` to exist.
- After a successful run, only `ledger/`, `state/`, `execution_package/`, and
  `reports/` (plus the parent run manifest) are published from the Controller
  Cache back to `REMOTE_PROJECT_DIR`, with the overall flow report
  (`reports/optimizer_flow_run_report.json`) uploaded **last** — its presence
  on the Remote host is what signals that the rest of that run's evidence
  already landed.
- The Controller Cache itself is rebuilt from scratch on every `prepare`
  call (any pre-existing cache directory is deleted, then recreated), so it
  is not a place to keep results between runs; treat it as a working copy,
  not a backup.
- `supervisor_instruction.json` and the doctor/license-probe reports are
  Controller-side preflight artifacts and are not part of the Remote
  publication set above.

For multi-corner projects, inspect `reports/multi_testbench_aggregation_report.json`
(and its per-run copy at `runs/real/<run_id>/multi_testbench_aggregation_report.json`)
and confirm each expected corner/testbench child appears in the aggregate
evidence. See
[PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md](PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md)
for the field-level meaning of that report.

For command traceability, confirm `command_trace` includes sanitized
Spectre/OCEAN argv summaries and does not include cshrc contents, SSH wrappers,
or secrets.

For CPU-limit audit, confirm optimizer reports include `runtime_thread_limits`
with requested and effective thread evidence.

For fix-run, confirm `reports/fix_run_report.json` reports
`workflow_mode: fix_run`, expected child counts, waveform CSV paths when
requested, and no optimizer state or optimizer decision report.

## See Also

- [OPTIMIZER_ALGORITHM_MODES.md](OPTIMIZER_ALGORITHM_MODES.md) — algorithm and
  strategy selection, initialization budget rules.
- [ROLE_MODEL_AND_TERMINOLOGY.md](ROLE_MODEL_AND_TERMINOLOGY.md) — Controller
  / Remote / Controller Cache roles and the current artifact glossary.
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md` — full
  `opt_requirement.md` field reference.
