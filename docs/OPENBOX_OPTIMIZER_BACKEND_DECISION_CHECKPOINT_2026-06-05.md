# OpenBox Optimizer Backend Decision Checkpoint

Date: 2026-06-05

## Purpose

Pause optimizer feature development and decide whether the optimizer backend should remain on the current TuRBO path or pivot to OpenBox.

This is a decision checkpoint, not an implementation plan. Do not replace TuRBO, edit optimizer behavior, or run a new real-tool optimization loop until this decision is reviewed.

## Current Project State

- Last completed milestone: C-26 Optimizer Completion And Continuation Decision Report.
- Last valid commit: `ca1c9c1 feat: add optimizer completion decision report`.
- Current TuRBO-backed flow:
  - Hermes generates optimizer task packets.
  - Execution worker runs `hermes-workflow run-native-turbo --parallel`.
  - Spectre/OCEAN execution and metric extraction are already proven for 100-evaluation practice runs.
  - `check-optimizer-run` audits returned artifacts.
  - `summarize-optimizer-run` writes a supervisor decision report.
- Current pause reason:
  - TuRBO is usable but awkward for the actual IC design space because the current local implementation is continuous-first and required custom quantization, duplicate handling, constrained scoring, and batch wrapping.
  - OpenBox may better match discrete/stepped variables, black-box constraints, batch/parallel evaluation, and parameter-importance reporting.

## OpenBox Local Reference

OpenBox was cloned as a local reference outside the project repo:

```text
/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box
```

Reference commit:

```text
2ab34cc chore: release v0.9.0
```

This local reference is not committed into `ic-auto-opt-workflow`.

## Sources Checked

- GitHub: <https://github.com/PKU-DAIR/open-box>
- Documentation: <https://open-box.readthedocs.io/en/latest/>
- Constrained single-objective example: <https://open-box.readthedocs.io/en/stable/examples/single_objective_with_constraint.html>
- HTML visualization: <https://open-box.readthedocs.io/en/stable/visualization/visualization.html>
- Local source examples:
  - `openbox_reference/open-box/examples/optimize_problem_with_constraint.py`
  - `openbox_reference/open-box/examples/ask_and_tell_interface.py`
  - `openbox_reference/open-box/examples/evaluate_async_parallel_optimization.py`
  - `openbox_reference/open-box/docs/en/advanced_usage/complex_space.md`
  - `openbox_reference/open-box/docs/en/advanced_usage/parallel_evaluation.md`
  - `openbox_reference/open-box/docs/en/visualization/visualization.md`

## Preliminary Findings

OpenBox appears directionally better aligned with the IC optimizer problem than the current TuRBO implementation:

- It supports objective results as a dictionary containing `objectives` and, for constrained problems, `constraints`; non-positive constraint values represent feasibility.
- It supports multiple variable types through ConfigSpace/OpenBox space APIs, including real, integer, categorical, and more complex conditional spaces.
- It has documented constrained single-objective and constrained multi-objective examples.
- It has local parallel optimization APIs such as `ParallelOptimizer` with async/sync modes and batch size.
- It has an ask-and-tell interface that may fit the existing Hermes execution-agent packet model better than a direct black-box callback.
- It has built-in history and visualization hooks, including convergence plots, HTML visualization, constraint charts, surrogate validation, and parameter importance. Some advanced importance features require extra dependencies such as `shap` and `lightgbm`.

## Local Evidence Spike

Evidence note:

```text
docs/debug/2026-06-05-openbox-backend-evidence-spike.md
```

The evidence spike installed OpenBox in an isolated `/tmp` virtual environment and ran fake inverter probes only. It did not modify production optimizer code, run real Virtuoso/Spectre/OCEAN, call an execution agent, parse PSF, or rewrite OCEAN formulas.

Observed:

- single-suggestion ask-and-tell probe produced `40` candidates, `0` grid issues, `0` duplicates, and constraint-aware history;
- batch ask-and-tell probe produced `10` batches of `4` candidates, `0` grid issues, `0` duplicates, and constraint-aware history;
- `get_suggestions(batch_size=N)` maps naturally to bounded parallel Spectre execution;
- real-valued grid entries still surface as Python binary floats, so Hermes must continue deterministic Spectre value serialization instead of trusting raw float reprs;
- OpenBox is promising as a backend candidate, but replacing TuRBO is not a one-line swap because report schemas, CLI names, dependency setup, history serialization, continuation semantics, and backend-specific trace fields must be handled deliberately.

## Fit For Our Inverter Optimization

The target problem is naturally discrete/stepped and constrained:

- `FN` is stepped integer.
- `FP = FN` should be an in-space relation or derived parameter, not an independent optimizer variable unless explicitly needed.
- `WN` and `WP` are stepped widths.
- Rise, fall, and power are constraints first.
- FOM/objective should be optimized only after constraints are satisfied.

OpenBox may let us express this more directly:

```text
objective: minimize power / (rise + fall)
constraints:
  rise - rise_limit <= 0
  fall - fall_limit <= 0
  power - power_limit <= 0
```

Important correction: OpenBox still minimizes objectives. Maximization remains a sign convention or reciprocal/objective transform unless a specific OpenBox API proves otherwise.

## Migration Impact Estimate

Likely reusable without major change:

- Spectre/OCEAN adapter and metric extraction.
- Real-run package preparation.
- Result and metric manifests.
- Acceptance audit and completion report concepts.
- Execution-agent task packet shape.
- Practice-first evidence discipline.

Likely needs replacement or adapter layer:

- `src/hermes_workflow/native_turbo.py` runner internals.
- `run-native-turbo` CLI naming and implementation.
- Native TuRBO report fields that are algorithm-specific.
- Tests that assert TuRBO-specific phases, batches, and duplicate behavior.

Recommended migration shape if accepted:

- Do not delete TuRBO code immediately.
- Add a backend seam such as `optimizer_backend: turbo | openbox`.
- Build one OpenBox proof path with fake evaluator first.
- Run one real 100-evaluation OpenBox optimizer practice using the already-proven Spectre/OCEAN evaluator.
- Only after real practice evidence, decide whether TuRBO becomes legacy or stays as an optional backend.

## Key Questions Before Replacing TuRBO

1. Can OpenBox represent our exact finite stepped search space without silently sampling off-grid values?
2. Can `FP = FN` be represented cleanly through a condition/derived parameter without wasting evaluations?
3. Does constrained optimization produce better feasible candidates than our current penalty-based objective on the same budget?
4. Does `ParallelOptimizer` or ask-and-tell fit the existing execution-agent handoff model with bounded Spectre concurrency?
5. Can OpenBox history be serialized in a stable, deterministic artifact that Hermes can audit?
6. Can OpenBox visualization/importance be produced from real IC run history without installing a heavy or fragile dependency stack?
7. What is the minimum viable replacement: direct `Optimizer`, `ParallelOptimizer`, or `Advisor` ask-and-tell?

## Recommended Next Step

Do a narrow OpenBox backend seam MVP before making a replacement decision.

Proposed next milestone:

```text
C-27 OpenBox Backend Seam MVP
```

Scope:

1. Add a backend seam that can support the current TuRBO implementation and a new OpenBox implementation.
2. Build an OpenBox fake-evaluator runner that emits Hermes-compatible optimizer artifacts.
3. Keep Spectre/OCEAN execution, candidate packaging, acceptance audit, and completion report contracts reusable.
4. Verify constraints, batch suggestions, and deterministic value serialization through tests before any real-tool run.
5. Decide after that whether to run one real 100-evaluation OpenBox acceptance.

Explicitly out of scope for C-27:

- No real Spectre/OCEAN run.
- No replacement of production TuRBO code.
- No deletion of existing TuRBO artifacts.
- No broad optimizer framework rewrite.
- No SHAP/visualization productization until OpenBox backend viability is proven.

## Resume Prompt

```text
请继续 IC auto optimization workflow。当前 repo 是 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow，branch 是 plan-a-hermes-file-contract-mvp。先阅读 AGENTS.md、docs/CURRENT_TASK_STATE.json、docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md、docs/EXECUTION_PROGRESS_2026-05-29.md、docs/COMPACT_RESUME_CHECKPOINT.md、docs/OPENBOX_OPTIMIZER_BACKEND_DECISION_CHECKPOINT_2026-06-05.md、docs/debug/2026-06-05-openbox-backend-evidence-spike.md。

当前状态：C-26 已完成并提交，commit: ca1c9c1。项目暂停在 optimizer backend 决策点。OpenBox 已作为只读参考 clone 到 /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/openbox_reference/open-box，参考 commit: 2ab34cc。OpenBox local-only fake inverter evidence spike 已完成，证明 stepped variables、constraints、ask-and-tell、batch suggestions 方向可行。下一步先决定是否写窄 scoped C-27 OpenBox backend seam MVP design/plan。

禁止事项：不要直接替换 TuRBO；不要删除现有 native_turbo 代码；不要运行真实 Virtuoso/Spectre/OCEAN；不要运行 execution agent；不要解析 PSF；不要重写 OCEAN 公式；不要创建 broad optimizer framework；不要提交 raw input.scs、ade_e.scs、PSF/raw、完整 Cadence log、docs/OCEAN_DOC_*、docs/toolchain_evidence/。

建议下一步：根据 docs/OPENBOX_OPTIMIZER_BACKEND_DECISION_CHECKPOINT_2026-06-05.md，先决定是否写 C-27 OpenBox evidence spike design spec。C-27 只做本地 fake-evaluator/OpenBox API 验证和迁移影响评估，不跑真实工具。
```
