# OpenBox Backend Evidence Spike

Date: 2026-06-05

## Purpose

Validate whether OpenBox is worth considering as the optimizer backend before replacing the current native TuRBO path.

This is evidence only. It does not replace TuRBO, modify production optimizer code, run real Cadence tools, call an execution agent, parse PSF, or rewrite OCEAN formulas.

## Environment

- OpenBox local reference: `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box`
- Reference commit: `2ab34cc chore: release v0.9.0`
- Isolated evaluation venv: `/tmp/ic_auto_opt_openbox_spike/.venv`
- Probe scripts:
  - `/tmp/ic_auto_opt_openbox_spike/openbox_fake_inverter_probe.py`
  - `/tmp/ic_auto_opt_openbox_spike/openbox_batch_fake_inverter_probe.py`

## Commands Run

```bash
/tmp/ic_auto_opt_openbox_spike/.venv/bin/python -m pip install -e /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box
```

```bash
MPLCONFIGDIR=/tmp/ic_auto_opt_openbox_spike/mpl \
/tmp/ic_auto_opt_openbox_spike/.venv/bin/python \
/tmp/ic_auto_opt_openbox_spike/openbox_fake_inverter_probe.py
```

```bash
MPLCONFIGDIR=/tmp/ic_auto_opt_openbox_spike/mpl \
/tmp/ic_auto_opt_openbox_spike/.venv/bin/python \
/tmp/ic_auto_opt_openbox_spike/openbox_batch_fake_inverter_probe.py
```

## Probe Model

The fake inverter probe used the current IC optimizer shape without real Spectre/OCEAN:

- Variables:
  - `FN`: stepped integer, `2..16`, `q=2`
  - `WN`: stepped real, `0.2..3.0`, `q=0.2`
  - `WP`: stepped real, `0.2..3.0`, `q=0.2`
  - `FP`: derived as `FP = FN`
- Constraints:
  - `rise - rise_limit <= 0`
  - `fall - fall_limit <= 0`
  - `power - power_limit <= 0`
- Objective:
  - minimize `power / (rise + fall)`

This matches the intended feasible-first IC optimization shape while keeping Cadence tools out of the evidence spike.

## Results

Single-suggestion ask-and-tell probe:

- Candidate count: `40`
- History length: `40`
- Status counts: `23 feasible`, `17 constraint_failed`
- Grid issues: `0`
- Duplicates: `0`
- OpenBox history recorded constraints: `true`
- OpenBox history exposes `get_importance`: `true`
- Best feasible observed fake candidate:
  - `FN=2`, `FP=2`, `WN=2.6000000000000005`, `WP=2.4000000000000004`
  - objective `1238833.4247326655`

Batch ask-and-tell probe:

- Batch count: `10`
- Batch size: `4`
- Candidate count: `40`
- History length: `40`
- Status counts: `24 feasible`, `16 constraint_failed`
- Grid issues: `0`
- Duplicates: `0`
- OpenBox history recorded constraints: `true`
- Best feasible observed fake candidate:
  - `FN=2`, `FP=2`, `WN=1.6`, `WP=2.0`
  - objective `794566.0135539863`

## Findings

OpenBox supports the core backend behaviors we need to evaluate further:

- stepped integer and stepped real variables can be represented with `q`;
- constrained single-objective observations can be recorded through `Observation(..., constraints=[...])`;
- ask-and-tell maps naturally to the existing Hermes/execution-agent handoff model;
- `get_suggestions(batch_size=N)` can generate batch candidates for bounded parallel Spectre execution;
- history retains constraint metadata and exposes an importance hook.

Important caveats:

- real-valued grid entries still appear as binary floats in Python, for example `2.6000000000000005`; Hermes should continue serializing approved Spectre parameter values with compact unit strings or deterministic decimal formatting;
- OpenBox adds a heavier dependency stack than the current local TuRBO path;
- production migration is not a one-line replacement because native TuRBO report fields, CLI names, trace schema, continuation semantics, and dependency setup are backend-specific;
- no real Spectre/OCEAN OpenBox run has been performed yet.

## Decision Impact

The high-level optimizer loop is the same as the current TuRBO route:

```text
define design space -> define constraints -> define objective
-> generate candidate batch -> run IC simulations
-> record metrics -> update optimizer model -> repeat
-> summarize best observed candidate and continuation decision
```

The useful change would be replacing only the optimizer backend seam. The existing Spectre/OCEAN adapter, candidate package contract, run acceptance audit, and completion report should be reused.

Recommended next step:

```text
C-27 OpenBox backend seam MVP
```

Keep it narrow:

- fake evaluator first;
- no real tools until fake OpenBox runner artifacts match current Hermes acceptance expectations;
- no deletion of TuRBO;
- no broad optimizer framework.
