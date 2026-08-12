# Circuit Knowledge

Record circuit-specific interpretation notes here during execution: topology
assumptions, corner/model-section rationale, OCEAN formula intent, and any
observation about this circuit that later runs or another agent session
should not have to rediscover. This file is prose for humans and agents; it
is never read by the requirement parser, the renderer, or the optimizer, and
it does not change simulation or optimization behavior.

Do not change `config/*.yaml` when adding notes. Those files are generated
from `opt_requirement.md` by `hermes-workflow prepare-from-requirement`
(`config` files are the `MANAGED_CONFIG_FILES` set); a manual edit is
overwritten the next time the project is rendered from the requirement, and
editing a managed config file directly is a `forbidden_actions` violation for
metric-request execution. Put any circuit fact that must affect behavior into
`opt_requirement.md` instead, then re-render.
