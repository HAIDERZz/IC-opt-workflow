# Real Tool Evidence Index

Date: 2026-06-03

Status: `verified-only` inventory. This file is a sanitized index only.

Local evidence bundle:

```text
/tmp/ic_auto_opt_real_tool_evidence/
```

Local manifests:

```text
/tmp/ic_auto_opt_real_tool_evidence/manifests/file_tree.txt
/tmp/ic_auto_opt_real_tool_evidence/manifests/hashes.sha256
```

Bundle size at inventory time: about 24 MB, 777 hashed files.

## Do Not Commit Raw Evidence

The local bundle may contain real `input.scs`, protected Cadence sidecars such
as `ade_e.scs`, PSF/raw result data, full Cadence logs, Maestro snapshot files,
and local execution transcripts. These files are local debug evidence only.

Do not stage or commit:

```text
docs/OCEAN_DOC_*
docs/toolchain_evidence/
raw input.scs
ade_e.scs
PSF/raw data
full Cadence logs
```

## Evidence Sets

### Inverter Spectre/OCEAN Smoke

Local copy:

```text
/tmp/ic_auto_opt_real_tool_evidence/inverter_spectre_ocean_smoke/
```

Source:

```text
docs/toolchain_evidence/2026-06-01-spectre-ocean-bridge-smoke/
```

Cell:

```text
Virtuoso_Bridge_test/bridge_test_inv
```

Key conclusion:

- Batch OCEAN opened the Maestro point-level PSF.
- Standalone Spectre replay of the full Maestro netlist bundle succeeded.
- Batch OCEAN opened the standalone PSF directly.
- OCEAN-produced scalar `rise`, `fall`, and `DC` values matched the Maestro
  point-level OCEAN values.

Important detail for C-7 closure:

- The successful standalone replay used the full netlist bundle, including
  `input.scs`, `ade_e.scs`, and simulator side files.
- This supports C-7 closure Task 1: the project contract must preserve exported
  netlist sidecars instead of copying only `input.scs`.

### Mixer PSS/PAC OCEAN Probe

Local copy:

```text
/tmp/ic_auto_opt_real_tool_evidence/mixer_pss_pac_ocean_probe/
```

Source:

```text
docs/toolchain_evidence/2026-06-01-pss-pac-directplot-ocean-probe/
```

Cell:

```text
Virtuoso_Bridge_test/Mixer_PSS_CG_Noise
```

Key conclusion:

- Batch OCEAN opened the Maestro point-level PSS/PAC/PNoise PSF.
- Standalone Spectre replay succeeded.
- Batch OCEAN opened the standalone Spectre PSF.
- Scalar probes using the captured `vh`/`db`/`bandwidth`/`ymax` formula path
  matched between Maestro point-level PSF OCEAN and standalone PSF OCEAN.

Important detail for C-7 closure:

- `drplPacVolGnExpDen` was callable in batch OCEAN in this environment, but a
  hand-written `drpl*` candidate was not equivalent to the captured `vh`
  formula.
- The project must evaluate exact user/project-approved formulas and must not
  translate formulas between dialects in Python.

### C-7 Adapter Debug Context

Local copy:

```text
/tmp/ic_auto_opt_real_tool_evidence/c7_debug_adapter_context/
```

Source:

```text
/tmp/ic_auto_opt_c7_debug/
```

Key conclusion:

- The root cause for the C-12 SPECTRE-132 failure was the adapter command
  argument `-log psf/spectre.out`.
- The committed fix `51fc057` uses `=log psf/spectre.out`.
- Follow-up blockers observed during debug are exported sidecars, Spectre-safe
  unit formatting, and metric namespace/formula alignment.

Sanitized debug note:

```text
docs/debug/2026-06-03-c7-real-tool-debug-lane.md
```

### C-12 Controlled Real-Tool Practice

Local copy:

```text
/tmp/ic_auto_opt_real_tool_evidence/c12_controlled_real_tool_practice/
```

Source:

```text
/tmp/ic_auto_opt_c12/
```

Key conclusion:

- Hermes prepared and approved `real_001`.
- The C-7 adapter boundary was exercised once after user confirmation.
- The returned result represented a real tool failure, not a checked metric
  success.
- Hermes `check-real-run` accepted the failed result manifest structurally,
  `check-metric-results` rejected missing/failed metric output, and recovery
  classified the run as `tool_result_failed`.

Important detail for C-7 closure:

- This is the failing practice case that the closure fixes must eventually
  turn into a passing real closure smoke, without manually repairing manifests.

## Current Closure Direction

The next planned implementation task is:

```text
C-7 Real Tool Closure Fixes Task 1: Exported Netlist Bundle Sidecars
```

Do not rerun real tools until sidecar, unit-format, and formula-contract fixes
are complete and the user explicitly authorizes the final closure smoke.
