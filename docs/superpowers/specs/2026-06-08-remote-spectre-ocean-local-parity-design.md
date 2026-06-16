# C-70 Remote Spectre/OCEAN Local-Parity Design

Date: 2026-06-08

## Purpose

C-70 fixes the C-69 remote Spectre/OCEAN drift with the smallest possible
change.

Remote mode may change only where Spectre/OCEAN commands execute. It must not
change the proven local Spectre/OCEAN adapter semantics:

- command arguments;
- command working directories;
- OCEAN replay mode;
- generated OCEAN script;
- PSF/log/scalar artifact expectations;
- result manifest semantics;
- metric result manifest semantics;
- multi-testbench child and aggregate failure propagation.

The C-69 SSH runner, remote project reference, cache mirror, doctor, remote
prepare, CLI routing, and report sync are reusable transport/product pieces.
The C-69 remote Spectre/OCEAN adapter semantics are not accepted as a product
execution implementation because they duplicated and diverged from the local
adapter.

## Verified Problem

The local RC project and remote project used the same requirement text:

```text
/home/zzchen/IC-OPT-test/rc_acceptance_project/Mixer_opt_muti_tb/opt_requirement.multi_testbench.md
/home/zzchen/remote_opt/mixer_muti_tb/opt_requirement.md
```

The previously accepted local RC run produced usable multi-testbench evidence:

- cumulative evaluations: 140;
- feasible: 29;
- constraint_failed: 95;
- metric_check_failed: 16;
- best feasible: `real_066`;
- `real_066` parameters:
  `F=26, L=40n, VB_LO=310m, W=1u`;
- `real_066` metrics:
  `BW=19171311625.11458`,
  `MAX_GAIN=4.242801858394763`,
  `NF_3G=11.81241967045868`,
  `IIP3=3.206487765822459`,
  `P1DB=-0.8997623115419788`;
- `real_066` objective: `-0.0503357919658288`.

The same first candidate `real_001`
(`F=14, L=40n, VB_LO=150m, W=0.4u`) shows why the remote failure is not a user
formula regression:

Local RC result:

- `cg_nf/ocean_scalars.tsv`:
  - `BW`: `fail`, `non_scalar`;
  - `MAX_GAIN`: `pass`, `-10.2070446558826`;
  - `NF_3G`: `pass`, `18.96165127950455`;
- `iip3/ocean_scalars.tsv`:
  - `IIP3`: `pass`, `11.72697689571528`;
- `p1db/ocean_scalars.tsv`:
  - `P1DB`: `fail`, `non_scalar`.

Remote C-69 result:

- expected child PSF path
  `runs/real/real_001/testbenches/cg_nf/psf` was missing in the local mirror;
- generated OCEAN script still opened
  `runs/real/real_001/testbenches/cg_nf/psf`;
- remote result manifest claimed success and referenced missing PSF artifacts;
- remote metric manifest could mark the top-level child run as succeeded even
  when individual metric rows failed.

Therefore the root cause is remote adapter semantic drift and artifact
validation failure, not the requirement markdown.

## Non-Negotiable Invariants

1. The local adapter in
   `src/hermes_workflow/execution_adapters/spectre_ocean.py` remains the source
   of truth for Spectre/OCEAN command semantics.
2. Remote mode must use the same Spectre argv as local mode, including
   `+escchars`, request-derived `+preset=...`, request-derived `+mt=...`,
   `+lqtimeout 900`, `-maxw 5`, `-maxn 5`, `-env ade`, `+logstatus`,
   request-derived `-format ...`, `-raw ../psf`, and
   `+log ../psf/spectre.out`.
3. Remote mode must use the same OCEAN argv as local mode:
   `ocean -nograph -replay <script_file> -log <log_file>`.
   It must not switch to `-restore`.
4. Remote mode must use the same cwd rules:
   Spectre cwd is the candidate/testbench `netlist/` directory; OCEAN cwd is
   the project directory.
5. Remote mode must not hardcode `+preset=aps`, output format, Spectre version,
   testbench names, metric names, or OCEAN formulas.
6. Remote mode must not write success manifests by hand.
7. Remote mode must not claim success unless the local mirror contains the
   required artifacts before manifest writing/parsing.
8. Missing remote PSF/log/scalar artifacts are real-tool or artifact-sync
   failures, not user metric formula failures.
9. Metric result manifest top-level status must match local writer behavior:
   any failed requested metric row makes the manifest failed and returns an
   adapter failure result.
10. Multi-testbench remote mode must preserve one child native Maestro/ADE
    bundle per testbench and aggregate child metric manifests exactly like
    local mode.

## Explicitly Out Of Scope

C-70 must not:

- redesign remote SSH profiles;
- redesign project cache layout;
- change OpenBox/TuRBO behavior;
- change optimizer ask-and-tell, continuation, reports, visualization, or FoM
  scoring;
- add remote Python product installation;
- add PSF parsing;
- rewrite OCEAN formulas;
- merge multiple testbenches into one Spectre deck;
- change `opt_requirement.md` grammar;
- change user resource settings;
- add broad new accessor/framework layers.

## Required Architecture

The implementation must keep C-70 as a narrow correction.

Allowed changes:

- expose small public wrappers or helpers from the local adapter for:
  - canonical Spectre argv;
  - canonical OCEAN argv;
  - result manifest writing;
  - metric result manifest writing;
  - existing artifact filtering;
- make the remote adapter call those shared helpers instead of duplicating
  command and manifest logic;
- download remote artifacts before calling local manifest/parsing helpers;
- make remote tests verify command parity and missing-artifact failure.

Preferred shape:

```text
remote_spectre_ocean.py
  load local adapter context
  render/write the same OCEAN replay script locally
  upload candidate/testbench run directory
  execute canonical Spectre argv remotely in canonical cwd
  download psf/, spectre stdout/stderr/log artifacts
  fail before manifest success if required Spectre artifacts are absent
  execute canonical OCEAN argv remotely in canonical cwd
  download metrics/, ocean stdout/stderr/log/scalars
  call local metric manifest writer
  call local result manifest writer
  upload final local manifests back to remote
```

If the code needs to rename private local helpers, do it surgically:

- `_spectre_argv` may become `build_spectre_argv` with a compatibility wrapper;
- `_ocean_argv` may become `build_ocean_argv` with a compatibility wrapper;
- manifest writers may be exposed as narrow internal helpers, but their payload
  semantics must not be forked.

## Acceptance Standard

C-70 is accepted only when all of the following pass.

Unit/regression evidence:

- remote Spectre command parity test proves the remote adapter uses canonical
  local Spectre argv and does not contain the C-69 hardcoded `+preset=aps`
  command construction;
- remote OCEAN command parity test proves `-replay` and `-log` are used;
- missing remote PSF causes a failed adapter result and does not write a
  success manifest;
- failed OCEAN scalar rows make the metric result manifest failed and make the
  adapter return failed;
- multi-testbench remote child failures propagate to aggregate failure
  classification.

Real parity evidence:

- use the known multi-testbench mixer requirement that already passed locally;
- run the smallest meaningful remote real parity check;
- verify remote/local mirror child artifacts exist for at least the first
  candidate:
  `psf/`, `psf/spectre.out`, `spectre.stdout`, `spectre.stderr`,
  `metrics/ocean.log`, `metrics/ocean.stdout`, `metrics/ocean.stderr`,
  and `metrics/ocean_scalars.tsv`;
- compare the first candidate against the local RC pattern:
  - `cg_nf`: `MAX_GAIN` and `NF_3G` pass, `BW` may remain non-scalar for the
    known weak-gain candidate;
  - `iip3`: `IIP3` passes;
  - `p1db`: `P1DB` may remain non-scalar for the known candidate;
- if the first remote candidate parameters do not match the known local first
  candidate, record that fact and compare the nearest identical candidate
  generated by the deterministic optimizer history instead of changing metric
  formulas.

Documentation evidence:

- `docs/REMOTE_SSH_ACCEPTANCE_2026-06-08.md` must state that C-69 accepted SSH
  orchestration only and that C-70 is the Spectre/OCEAN parity fix;
- progress state must not claim production remote Spectre/OCEAN acceptance
  until the real parity evidence above exists.

## Stop Conditions

Stop and return to the user before coding further if implementation pressure
would require any of these:

- changing metric formulas to make remote pass;
- changing requirement markdown grammar;
- creating a new remote execution architecture beyond the current SSH runner;
- adding remote product Python installation;
- modifying optimizer candidate generation;
- treating missing PSF/log artifacts as metric formula failures.
