# Metric Contract Notes

Metric definitions come from the `Metrics` section of `opt_requirement.md` and
are rendered to `config/metrics.yaml`. Optimize requires scalar Metrics;
fix-run accepts Metrics, Waveform Exports, or both.

## Metric Fields

```yaml
- name: NF_3G
  unit: dB
  testbench: cg_nf
  result: pnoise
  ocean_expression: 'value(getData("NF") 3e+09)'
  required_signals:
    - NF
```

- `name` is the unique metric identifier used by Constraints and Objective.
- `unit` is part of the metric identity. A Constraint value for this metric
  must use exactly the same unit string.
- `testbench` is omitted for a top-level single-testbench Maestro Source. It is
  required when `Maestro Source.testbenches` is used and must equal one of its
  declared IDs.
- `result` is optional. When present, the OCEAN replay emits
  `selectResult('<result>)` (SKILL reference-symbol form, no closing quote)
  before evaluating `ocean_expression`. Requirement validation rejects unsafe
  result identifiers before simulation. It is normally omitted when the
  expression already contains an explicit `?result` selector.
- `ocean_expression` is copied exactly into the OCEAN replay script. IC Auto
  Opt does not rewrite an ADE/Maestro-approved formula.
- `required_signals` is optional provenance and history-compatibility metadata.
  It is copied into metric request/result contracts, but the workflow does not
  inspect PSF to prove those signal names exist. Missing data still fails when
  the OCEAN expression errors, returns nil, or does not return a finite scalar.

Scalar metric nil and non-finite policies are fixed to `fail`; they are not
user-overridable requirement fields. A metric definition that changes
`result`, `required_signals`, unit, formula, or testbench route is a different
metric definition for History Warm Start compatibility. The internally
recorded Maestro formula provenance is also part of that compatibility
signature even though it is not a requirement input field, so the list above
is not the complete signature.

## Constraint Units

Constraint operators are `lt`, `le`, `gt`, and `ge`. The value contains a
number, whitespace, and the exact Metric unit:

```yaml
- metric: NF_3G
  op: lt
  value: 9 dB
```

Do not compare a `dB` metric against `Hz`, omit the unit, or rely on implicit
conversion. The requirement is rejected before simulation when the unit does
not match.

## Scalar Versus Waveform Results

Optimizer Metrics must evaluate to finite real scalars. Full waveform CSV
export belongs in fix-run `Waveform Exports`; it is a separate evidence
contract and does not turn a waveform into an optimizer metric.
