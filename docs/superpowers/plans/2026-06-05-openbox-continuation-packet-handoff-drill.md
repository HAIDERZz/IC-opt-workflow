# C-42 OpenBox Continuation Packet Handoff Drill

Date: 2026-06-05

Design spec:

```text
docs/superpowers/specs/2026-06-05-openbox-continuation-production-handoff-design.md
```

## Goal

Validate that the C-40 generated OpenBox continuation packet is sufficient for a
production-style execution-agent handoff: generate the packet, follow the packet
semantics, run a small real continuation, then close out with supervisor audit
reports.

## Route Audit

- Active spec:
  `docs/superpowers/specs/2026-06-05-openbox-continuation-production-handoff-design.md`
- Top-level plan:
  `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
- Alignment: uses the accepted Spectre/OCEAN/OpenBox path and C-40 packet
  contract to validate the production handoff loop.
- Drift: none intended. Do not create a new optimizer backend, do not change
  formulas, do not hand-pick candidates, do not run fake ladders, and do not
  alter objective or constraint semantics.

## Workspace

Source accepted workspace:

```text
/tmp/ic_auto_opt_c39_continuation_002/bridge_test_inv
```

C-42 drill workspace:

```text
/tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv
```

The C-42 workspace is a copy of the accepted C-39 continuation result. The drill
continues it by 10 additional OpenBox evaluations through the generated packet
path.

## Task 1: Generate Production Continuation Packet

- [x] Copy the accepted C-39 workspace into the C-42 drill workspace.
- [x] Run `check-optimizer-run`, `summarize-optimizer-run`, and
  `finalize-optimizer-run` before continuation to prove the starting point is an
  accepted optimizer state.
- [x] Generate an OpenBox continuation packet with:

```bash
.venv/bin/hermes-workflow package-optimizer-task /tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv --backend openbox --continuation --additional-evals 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh --parallel
```

- [x] Verify the generated packet includes `check-toolchain-env`,
  `/tmp/ic_auto_opt_openbox_spike/.venv`, `continue-openbox-real`,
  `finalize-optimizer-run`, and returned supervisor report artifacts.

## Task 2: Execute Real Continuation Through Packet Semantics

- [x] Run the toolchain environment gate from the generated packet.
- [x] Run the real OpenBox continuation with the known-good environment from
  `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`:

```bash
csh -fc 'source /home/zzchen/cadence_ic231_env.csh; setenv PATH /tmp/ic_auto_opt_openbox_spike/.venv/bin:$PATH; setenv MPLCONFIGDIR /tmp/ic_auto_opt_c42_packet_handoff_001/mpl_cache; cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow; hermes-workflow continue-openbox-real /tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv --additional-evals 10 --batch-size 10 --parallel-jobs 10 --cadence-cshrc /home/zzchen/cadence_ic231_env.csh'
```

- [x] Stop for user intervention if an unexpected tool, license, packet, or
  metric extraction failure appears.

## Task 3: Closeout And Evidence

- [x] Run:

```bash
.venv/bin/hermes-workflow check-optimizer-run /tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv
.venv/bin/hermes-workflow summarize-optimizer-run /tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv
.venv/bin/hermes-workflow finalize-optimizer-run /tmp/ic_auto_opt_c42_packet_handoff_001/bridge_test_inv
```

- [x] Record a sanitized evidence note under `docs/debug/`.
- [x] Update `docs/CURRENT_TASK_STATE.json`,
  `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md`, and this plan.
- [x] Run cadence and diff checks.
- [x] Commit with a concise C-42 message.

## Acceptance

- The generated packet contains the required C-40 production handoff commands
  and artifacts.
- The real continuation adds 10 cumulative evaluations using OpenBox, Spectre,
  and OCEAN through the known-good environment.
- The closeout reports pass and keep `global_optimum_claim=false`.
- No raw Cadence netlists, PSF/raw data, full logs, or protected sidecars are
  committed.
