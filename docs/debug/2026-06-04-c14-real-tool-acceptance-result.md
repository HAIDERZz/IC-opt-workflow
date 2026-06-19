# C-14 Real-Tool Acceptance Result

Date: 2026-06-04

## Scope

Accepted path:

```text
suggest-candidate
-> prepare-candidate-real-run
-> C-7 Spectre/OCEAN adapter
-> check-real-run
-> check-metric-results
-> record-real-result or recovery classification
```

## Local Evidence

```text
/tmp/ic_auto_opt_c14/evidence/real_tool_acceptance_001/
```

## Result

- Seed `real_001`: passed real-tool execution, result checks, metric checks, and result recording.
- Suggested `real_002`: passed `suggest-candidate`, candidate package preparation, real-tool execution, result checks, metric checks, and result recording.
- Ledger state: 2 rows recorded, both with scalar OCEAN metrics and `simulation_status = real_constraint_fail`.
- Optimizer state: `current_evaluations = 2`.

Observed scalar metrics:

| Run | Candidate | Rise | Fall | DC |
| --- | --- | --- | --- | --- |
| `real_001` | `real_001` | `7.52016846017672e-11 s` | `1.078998721053984e-10 s` | `0.0002588877964196586 W` |
| `real_002` | `candidate_000002` | `3.326181720494057e-11 s` | `4.973593602698243e-11 s` | `0.0009838038264352862 W` |

The `real_constraint_fail` rows are valid optimizer observations: Spectre and OCEAN succeeded, but the points did not satisfy the configured performance constraints.

## Decision

Proceed to narrow optimizer loop productization.

C-14 proves the minimum real-tool path works with native Maestro/ADE netlist layout and approved OCEAN formulas. The next scope should stay narrow: one small loop that repeatedly requests a single candidate, prepares a candidate real-run package, runs the existing C-7 adapter, records the result or classified failure, and stops on an explicit evaluation budget.

## Safety

Python did not parse PSF data.
Approved OCEAN formulas were not rewritten.
Native Maestro/ADE netlist layout was preserved.
Raw Cadence artifacts remain local-only.

## Runtime Note

Spectre must run outside the Codex sandbox for this environment. A sandboxed attempt failed before OCEAN with pipe/socket permission errors, while the same adapter path succeeded through the approved Cadence `csh -fc` execution path.
