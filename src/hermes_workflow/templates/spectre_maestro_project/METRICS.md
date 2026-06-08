# Metric Contract Notes

Metric definitions live in `config/metrics.yaml`.

`maestro_formula` is preserved for traceability and review. The first MVP does not implement a generic Maestro calculator parser.

`objective.expression` is not an OCEAN formula. It combines already extracted
scalar metric names. Use `direction: minimize` when the expression is
lower-is-better. Use `direction: maximize` when the expression is
higher-is-better; the optimizer stores the user FoM and internally minimizes
`-FoM` for feasible candidates.
