# C-21 OCEAN Metric Extraction Retry Policy

Date: 2026-06-04

## Scope

C-21 handled the residual C-20 real-tool blocker where Spectre completed but
OCEAN metric extraction failed with command/license return code `35`.

This was intentionally narrow:

- retry OCEAN metric extraction only;
- never rerun Spectre for an OCEAN-only command failure;
- never retry candidate-level non-scalar metric failures;
- keep native Maestro/ADE netlist layout and approved OCEAN formulas unchanged.

## Code Change

The C-7 Spectre/OCEAN adapter now retries OCEAN up to three attempts after a
non-zero OCEAN command return code. The final metric result manifest records:

- `ocean.attempts`
- `ocean.return_codes`
- final `ocean.return_code`

`check-metric-results` validates that the attempt count matches the return-code
history and that the final return code matches the final entry.

## Verification

Focused tests:

```text
python3 -m pytest tests/test_spectre_ocean_adapter.py -q
```

Result: `58 passed`.

Adjacent regression:

```text
python3 -m pytest tests/test_metric_results.py tests/test_native_turbo.py tests/test_spectre_ocean_adapter.py -q
```

Result: `128 passed, 1 skipped`.

Focused lint:

```text
python3 -m ruff check src/hermes_workflow/execution_adapters/spectre_ocean.py src/hermes_workflow/metric_results.py tests/test_spectre_ocean_adapter.py
```

Result: passed.

## Real-Tool Rerun

Local-only practice directory:

```text
/tmp/ic_auto_opt_c21/bridge_test_inv
```

Command shape:

```text
.venv/bin/hermes-workflow run-native-turbo /tmp/ic_auto_opt_c21/bridge_test_inv --parallel --max-evals 100 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh
```

Manifest audit:

- 100 real run directories
- 100 result manifests succeeded
- 100 metric manifests produced
- 86 metric manifests succeeded
- 14 metric manifests failed with candidate-level `rise/fall non_scalar`
- 0 final OCEAN command/license failures
- 0 missing metric manifests
- 0 retry attempts were needed in this rerun

Settings audit:

- `preset=ax`
- `threads_per_run=10`
- `parallel_jobs=10`
- `output_format=psfxl`

## Conclusion

C-21 closes the known OCEAN command/license failure class at the adapter
contract level. The real rerun did not reproduce a license failure, but it
proved the retry manifest fields and schema change do not break the 100-point
parallel optimizer path. Candidate-level non-scalar metric failures remain
valid optimizer outcomes and are not retried.
