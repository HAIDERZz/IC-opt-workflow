# 多工艺角优化流程

多工艺角由 `opt_requirement.md` 的 Process Corners 配置。优化器不会只看某一个
corner，也不会为每个 corner 单独维护一套搜索历史。每个候选参数会先跑完配置的
testbench/corner 组合，再聚合成一个 optimizer observation。

## 1. requirement 配置

典型配置：

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: "27"
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: "125"
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: "-40"
```

`objective_policy` 决定多个 corner 的 objective 如何合成。`constraint_policy`
决定约束如何判定。

## 2. 单个候选点的流程

```text
candidate parameters
  -> run each configured testbench/corner child
  -> collect child metrics and statuses
  -> build parent aggregate manifest
  -> compute one aggregate objective/status
  -> send one observation to optimizer
```

child manifest 记录单个仿真的 Spectre/OCEAN 结果。parent aggregate manifest 记录
这个候选点下所有 child 的证据、corner 结果、聚合 objective 和聚合状态。

## 3. objective 聚合

优化器内部统一按 minimize 处理：

- 对 minimize 目标，内部 objective 等于 FoM。
- 对 maximize 目标，内部 objective 等于 `-FoM`。
- 仿真失败使用 `failure_penalty`。
- 约束失败使用 `failure_penalty + constraint_penalty`。

在 `objective_policy: worst_case` 下，系统比较的是每个 corner 的内部 objective。
内部 objective 最大的 corner 是最坏 corner，因为它对 minimize 优化器最不利。

## 4. constraint 聚合

`constraint_policy: all_corners` 表示所有配置的 corner 都必须满足约束。只要一个
corner 违反约束，这个候选点就不是 feasible。

如果某个 child 仿真失败或 metric 失败，parent aggregate 会保留失败证据，聚合状态
也会反映失败。优化器收到的是带 penalty 的 observation，而不是缺失数据。

## 5. OpenBox 和 TuRBO 看到什么

OpenBox 和 native TuRBO 都只接收聚合后的 observation：

```text
parameters -> aggregate objective/status -> optimizer history
```

OpenBox 更新的是聚合 objective。native TuRBO 更新 trust region 时也使用聚合
objective 和聚合状态。下一批候选参数由优化器根据这些聚合历史生成。

## 6. 报告里应该看什么

真实验收时检查：

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
parent aggregate manifest
reports/optimizer_decision_report.md
```

重点确认：

- parent aggregate 里列出了预期 testbench/corner child；
- selected corner 和 worst corner 与 policy 解释一致；
- `constraint_policy: all_corners` 下每个 corner 的约束结果都有证据；
- OpenBox/TuRBO 下一批参数使用的是聚合 observation；
- 报告说的是 best observed feasible candidate，而不是全局最优证明。
