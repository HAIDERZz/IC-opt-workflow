# 多工艺角优化流程说明

本文说明 `ic-opt` 在启用多个 process corner 时的真实优化数据流。重点结论：

- 优化器不是固定使用 `tt`、`ff` 或 `ss` 中某一个工艺角。
- 每个候选点都会运行所有配置的 testbench 和所有配置的 corner。
- 多个 corner 的结果会先聚合成一个“内部最小化 objective 标量”，再交给 OpenBox 或 native TuRBO 生成下一批参数。
- `objective_policy: worst_case` 表示优化器使用最坏 corner 的内部 objective；`constraint_policy: all_corners` 表示任意 corner 违反约束都会使该候选点不可行。

## 配置入口

多工艺角来自 `opt_requirement.md`，经 requirement intake 生成 `config/process_corners.yaml`。

典型配置：

```yaml
process_corners:
  objective_policy: worst_case
  constraint_policy: all_corners
  corners:
    - id: tt
      ...
    - id: ff
      ...
    - id: ss
      ...
```

当前支持的 policy：

- `objective_policy: nominal`
  - objective 只使用 nominal corner。如果没有名为 `nominal` 的 corner，则使用配置中的第一个 corner。
- `objective_policy: worst_case`
  - 每个 corner 先单独计算内部 objective。
  - 选择内部 objective 最大的 corner 作为 worst/selected corner。
  - 因为优化器内部统一做 minimize，所以“最大内部 objective”就是最坏情况。
- `constraint_policy: nominal`
  - 只检查 nominal corner 的约束。
- `constraint_policy: all_corners`
  - 检查所有配置 corner 的约束。
  - 任意 corner 约束失败，则整个 candidate 标记为 `constraint_failed`。

## 一次 candidate 的执行流程

以 3 个 testbench 和 3 个 corner 为例，一个 candidate 会展开成 9 个 child simulation：

```text
candidate_N
  |
  +-- cg_nf / tt
  +-- cg_nf / ff
  +-- cg_nf / ss
  |
  +-- iip3  / tt
  +-- iip3  / ff
  +-- iip3  / ss
  |
  +-- p1db  / tt
  +-- p1db  / ff
  +-- p1db  / ss
```

每个 child simulation 会产生：

```text
runs/real/real_NNN/testbenches/<testbench>/corners/<corner>/result_manifest.json
runs/real/real_NNN/testbenches/<testbench>/corners/<corner>/metrics/metric_result_manifest.json
```

随后 `aggregate_multi_testbench_run()` 聚合这个 candidate 的所有 child results，并写出：

```text
runs/real/real_NNN/result_manifest.json
runs/real/real_NNN/metrics/metric_result_manifest.json
runs/real/real_NNN/multi_testbench_aggregation_report.json
reports/multi_testbench_aggregation_report.json
```

## 聚合流程图

```text
opt_requirement.md
  |
  v
generated config:
  config/optimizer.yaml
  config/spectre.yaml
  config/process_corners.yaml
  |
  v
optimizer proposes candidate parameters
  |
  v
prepare real_NNN packages
  |
  v
run all testbench x corner children
  |
  v
child result_manifest.json
child metric_result_manifest.json
  |
  v
aggregate_multi_testbench_run()
  |
  +-- collect metrics by corner
  |     tt_metrics
  |     ff_metrics
  |     ss_metrics
  |
  +-- evaluate each corner independently
  |     tt_objective / tt_status
  |     ff_objective / ff_status
  |     ss_objective / ss_status
  |
  +-- apply constraint_policy
  |     all_corners: any failed corner => candidate constraint_failed
  |
  +-- apply objective_policy
        worst_case: choose max internal objective as selected/worst corner
  |
  v
single optimizer observation:
  status
  objective
  fom
  constraint_penalty
  metrics
  result_manifest path
  metric_result_manifest path
```

## 优化器看到什么

OpenBox 和 native TuRBO 不直接处理 9 份 child simulation 的原始结果。它们看到的是聚合后的单条 observation。

```text
candidate parameters
  -> all testbench/corner simulations
  -> aggregate objective/status
  -> optimizer observation
```

OpenBox 的后续流程：

```text
aggregate observation
  |
  v
OpenBox observation:
  objectives=[trace.objective]
  constraints=<constraint residuals>
  |
  v
advisor.update_observations(...)
  |
  v
advisor suggests next batch
```

native TuRBO 的后续流程：

```text
aggregate observation
  |
  v
NativeTurboEvaluationTrace:
  objective=<aggregate objective>
  status=<aggregate status>
  metrics=<selected/aggregate metrics>
  |
  v
TuRBO updates trust region from historical X/fX
  |
  v
TuRBO proposes next batch
```

## Objective 的内部标量语义

优化器内部统一最小化 objective。

- 如果用户目标是 `minimize`，内部 objective 等于 FoM。
- 如果用户目标是 `maximize`，内部 objective 等于 `-FoM`。
- 如果 metric 失败，内部 objective 使用 `failure_penalty`。
- 如果 constraint 失败，内部 objective 使用 `failure_penalty + constraint_penalty`。

因此在 `objective_policy: worst_case` 下，系统比较的是每个 corner 的“内部 objective”，不是直接比较原始指标值。

## 真实 artifact 示例

来自 remote native TuRBO 40 点真实 workflow：

```text
runs/real/real_002/multi_testbench_aggregation_report.json
```

该 candidate 的聚合结果：

```text
constraint_policy = all_corners
objective_policy  = worst_case
status            = constraint_failed
selected_corner   = ss
worst_corner      = ss

corner_objectives:
  ff = 1000000.0000004189
  ss = 1000000.257517249
  tt = 1000000.0004128144
```

这里 `ss` 的内部 objective 最大，因此这个 candidate 返回给优化器的 objective 是 `1000000.257517249`。这说明多 corner flow 并不是固定使用 `tt`。

## 如何检查一个 run 是否真的用了多 corner

检查以下文件：

```text
config/process_corners.yaml
runs/real/real_NNN/multi_testbench_aggregation_report.json
runs/real/real_NNN/result_manifest.json
runs/real/real_NNN/metrics/metric_result_manifest.json
reports/*optimizer*_evaluations.jsonl
```

重点字段：

```text
constraint_policy
objective_policy
selected_corner
worst_corner
corner_objectives
corner_status_counts
corner_metrics
```

如果 `corner_objectives` 同时包含 `tt`、`ff`、`ss`，并且 optimizer evaluation row 中的 objective 与 worst-case selected corner 对应，则说明多 corner objective 已经进入优化器。

## 当前报告易误读点

当整个优化没有 feasible candidate 时，`reports/optimizer_decision_report.md` 会推荐：

```text
Recommended run: none
Basis: no_feasible_candidate
```

这种情况下，decision report 可能没有充分展示每个 candidate 的 `corner_objectives` 和 corner failure 分布，容易让用户误以为系统只看了某个 corner。

更可靠的审计文件是：

```text
runs/real/real_NNN/multi_testbench_aggregation_report.json
reports/*optimizer*_evaluations.jsonl
```

后续应增强 decision/insight report，在 no-feasible 场景下也展示：

- 各 corner 的失败分布
- 代表性 candidate 的 `corner_objectives`
- worst/selected corner 的来源
- 最接近可行 candidate 的 per-corner metric 表

