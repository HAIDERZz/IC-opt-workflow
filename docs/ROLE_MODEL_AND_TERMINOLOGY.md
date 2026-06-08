# Role Model And Terminology

Date: 2026-06-02

This document locks the project role model. Future plans, specs, prompts, and implementation work should use these meanings.

## Locked Role Model

The original workflow model has two agent roles and one deterministic tooling
layer:

```text
User
-> Supervisor agent
-> Hermes workflow tooling
-> Execution agent
-> Virtuoso / Spectre / OCEAN
-> Execution artifacts
-> Hermes workflow tooling checks
-> Supervisor agent decision
```

## Supervisor Agent

The supervisor agent is the planning and decision-making agent.

In the v0.1 product route, the current user-facing agent normally performs this
role and calls the deterministic `ic-opt` CLI directly. A separate execution
agent is optional, not required for normal use.

It uses Hermes workflow tooling, but it is not the same thing as Hermes.

The supervisor agent owns:

- translating the user's optimization goal into project configuration files
- reviewing or approving exact OCEAN metric formulas before real execution
- calling Hermes workflow commands in the required order
- reading machine-readable Hermes reports
- deciding whether to approve the first real run
- deciding whether to retry, revise contracts, escalate, or stop after failures
- deciding when validated real metrics are ready for later optimizer/ledger steps

The supervisor agent must not:

- run real Spectre directly
- run real OCEAN directly
- parse PSF or waveform databases
- translate Calculator/OCEAN formulas into Python
- trust execution-agent prose as proof of success
- advance the workflow without the required Hermes reports

## Hermes Workflow Tooling

Hermes is the deterministic file-contract and validation tooling in this repository.

In older discussions, "Hermes" sometimes referred to a local supervisor agent. That meaning is no longer used for this project. From this point forward, Hermes means the workflow tooling and its file contracts.

Hermes workflow tooling owns:

- YAML schemas and cross-file validation
- project template generation
- execution package generation
- netlist templating of approved top-level Spectre parameters
- deterministic dry-run candidate rendering
- preflight health reports
- first-real-run approval files
- post-approval real-run package preparation
- result handoff validation
- OCEAN metric result contract validation
- machine-readable reports

Hermes workflow tooling must not:

- run real Virtuoso
- run real Spectre
- run real OCEAN
- run optimizer-side tool actions
- parse PSF or waveform data
- compute Calculator/OCEAN metrics in Python
- approve formulas on behalf of the user or supervisor agent
- trust chat history as workflow state

Hermes workflow state is file state. If it is not in a validated contract file or report, it is not trusted workflow evidence.

## Execution Agent

The execution agent is the tool-side agent that operates Cadence and bridge tooling.

The execution agent may be implemented with a native subagent in the current
runtime, a scripted worker, or a future adapter. The role is defined by
responsibilities, not by a specific model vendor.

The execution agent owns:

- inspecting or exporting Maestro/Virtuoso setup when instructed
- placing or exporting `netlists/exported/input.scs`
- consuming approved `runs/real/<run_id>/` packages after supervisor approval
- running standalone Spectre through the approved adapter boundary
- running batch OCEAN through the approved adapter boundary
- evaluating exact approved OCEAN formulas from `metric_extraction_request.json`
- writing `result_manifest.json`
- writing OCEAN scalar artifacts and `metric_result_manifest.json`
- preserving logs, status, paths, hashes, and failure evidence

The execution agent must not:

- change approved project contracts during execution
- edit or reinterpret approved OCEAN formulas
- run real Spectre before the first-real-run approval gate
- write outside allowed project run directories
- report success only in chat prose
- update optimizer ledger or state unless a later plan explicitly grants that responsibility

## Trust Boundary

The supervisor agent and execution agent communicate through files, not trust.

The supervisor agent may ask the execution agent to perform tool-side work, but the supervisor agent may accept the result only after Hermes workflow tooling validates the returned files.

Required trust chain for a real metric result:

```text
approve
-> prepare-real-run
-> execution agent runs C-7 adapter
-> result_manifest.json
-> metric_result_manifest.json
-> check-real-run passes
-> check-metric-results passes
-> supervisor agent may continue
```

If an execution agent says "the run passed" but Hermes workflow tooling reports fail, the run failed.

If Hermes workflow tooling reports pass but the execution agent prose says something different, the supervisor agent follows the Hermes workflow report and investigates the discrepancy separately.

## Naming Rules For Future Docs

Use these terms:

- `supervisor agent`
- `execution agent`
- `Hermes workflow tooling`
- `Hermes file contracts`
- `execution-side adapter`
- `virtuoso-bridge-lite tool layer`

Avoid these ambiguous terms:

- `Hermes agent`
- `Hermes supervisor agent`
- `real Hermes service`
- any vendor-specific execution agent name as a permanent role name

It is acceptable to mention a specific agent platform only as one possible local
implementation. It is not the locked role name.

## Project Goal Fit

This role model still satisfies the original project goal:

- the supervisor agent is constrained by deterministic contracts and reports
- the execution agent is constrained by prepared packages and artifact schemas
- reusable workflow modules prevent each new optimization from being rebuilt from scratch
- real Cadence work remains behind explicit approval and adapter boundaries
- metric calculation stays in OCEAN, not in agent-written Python

Future development should preserve this role model unless the project deliberately creates a new design spec that replaces it.
