# C-7 Real-Tool Debug Lane

Date: 2026-06-03

This is a fast debug record for the C-7 Spectre + OCEAN adapter after the C-12
real-tool practice exposed a real Spectre failure.

Status: `verified-only`. This is not a reviewed implementation task.

## Working-Tree Fix

Root cause for the original C-12 adapter failure:

- C-7 used `-log psf/spectre.out`.
- In this local Spectre invocation, `-log` does not take a file argument.
- Spectre treated `psf/spectre.out` as a second input deck and failed with
  SPECTRE-132.

Working-tree patch:

```text
-log psf/spectre.out -> =log psf/spectre.out
```

Changed files:

```text
src/hermes_workflow/execution_adapters/spectre_ocean.py
tests/test_spectre_ocean_adapter.py
```

Focused verification:

```text
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
```

## Real-Tool Findings

All real-tool debug runs used local `/tmp` projects. Raw decks, protected files,
PSF data, and full simulator logs remain local-only and must not be committed.

### Auxiliary Include Gap

After the `=log` fix, Spectre advanced past SPECTRE-132 and then failed because
the run directory did not contain the relative include file:

```text
include "ade_e.scs"
```

Copying the matching local `ade_e.scs` into the run directory allowed Spectre to
continue.

Implication: the current `netlists/exported/input.scs` contract is too narrow
for Maestro-exported decks that rely on relative include sidecars. A later
scoped fix should preserve the full exported netlist bundle, not only
`input.scs`.

### Variable Unit Formatting Gap

Template variables used values such as:

```text
WN: "0.3 um"
WP: "0.3 um"
```

Hermes rendered those strings exactly into Spectre:

```text
WN=0.3 um WP=0.3 um
```

Spectre interpreted the width values incorrectly for parameter assignment and
hit model binning errors. In a `/tmp` debug project, changing the values to
`0.3u`, `3u`, and `0.2u` let Spectre complete.

Implication: shipped template/fixture variable values should avoid
whitespace-separated Spectre units.

### Metric Namespace/Formulas Gap

With Spectre completing, OCEAN ran and produced a structured metric result
manifest, but the current sample formulas did not pass:

```text
rise: non_scalar
fall: non_scalar
DC: expression_error
```

OCEAN signal probes showed that the standalone adapter result exposed signals
such as:

```text
VOUT
VDD
M0:3
V0:p
```

The sample metrics expect ADE/Maestro-style names:

```text
/VOUT
/VDD
/M0/S
```

Direct OCEAN probes showed that standalone-style formulas such as
`VDC("VDD") * IDC("V0:p")` can produce scalar values. The adapter must not
translate formulas itself; approved formulas must match the actual OCEAN result
namespace, or the execution contract must preserve the Maestro mapping context
that makes the ADE namespace valid.

### Candidate/Formula Behavior Gap

One lower-bound candidate produced `VOUT` max below the 0.9 V threshold, so
rise/fall expressions returned `nil`. That is a valid checked real-run failure,
not a reason for Python to compute metrics or rewrite formulas.

## Current Conclusion

The immediate C-7 command fix is small and safe:

```text
-log psf/spectre.out -> =log psf/spectre.out
```

The next scoped real-tool contract fixes should be chosen separately:

- preserve exported netlist sidecars such as `ade_e.scs`;
- reject or normalize invalid whitespace-unit variable values before approval;
- require user-approved metric formulas to match the actual OCEAN result
  namespace, or preserve the Maestro mapping context that supports the ADE
  namespace;
- keep Python out of PSF parsing and metric computation.
