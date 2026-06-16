# 多工艺角优化流程

多工艺角由 `opt_requirement.md` 的 `Process Corners` 配置。优化器不会只看某一个
corner，也不会为每个 corner 单独维护一套搜索历史。每个候选参数会先跑完配置的
testbench/corner 组合，再聚合成一个 optimizer observation。

## Requirement 配置

```yaml
objective_policy: worst_case
constraint_policy: all_corners
corners:
  - id: tt
    model_section: Post_simu_top_tt
    variables:
      temperature: '27'
  - id: ss
    model_section: Post_simu_top_ss
    variables:
      temperature: '125'
  - id: ff
    model_section: Post_simu_top_ff
    variables:
      temperature: '-40'
```

`objective_policy` 决定多个 corner 的 objective 如何合成。`constraint_policy`
决定约束如何判定。

## 单个候选点流程

```text
candidate parameters
  -> render each configured testbench/corner child
  -> run Spectre/OCEAN for each child
  -> collect child metrics and statuses
  -> build parent aggregate manifest
  -> compute one aggregate objective/status
  -> send one observation to optimizer
```

child manifest 记录单个仿真的 Spectre/OCEAN 结果。parent aggregate manifest 记录
这个候选点在所有 child 上的聚合结果。

## Objective 和 Constraint

常用策略：

- `objective_policy: worst_case`：优化器使用 worst-case corner objective。
- `constraint_policy: all_corners`：所有 corner 都满足约束时，候选点才可行。

失败 child 会按 failure penalty 进入聚合结果。报告里的推荐点是 best observed
feasible candidate，不是全局最优证明。

## 优化器如何使用多 corner 结果

优化器看到的是聚合后的单条 observation：

```text
parameters -> aggregate objective/status -> optimizer history
```

OpenBox 和 native TuRBO 都使用这个聚合 observation 生成下一批候选参数。

fix-run 也可以使用同一个 `Process Corners` 结构，但它不会生成 optimizer
observation，也不会进入下一批候选参数；它只记录每个固定点在各 child 上的仿真、
metric 和 waveform export 结果。

## 验收时看什么

真实验收时检查：

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
parent aggregate manifest
reports/optimizer_decision_report.md
reports/fix_run_report.json
```

重点核对：

- parent aggregate 列出了预期的 testbench/corner child
- selected corner、worst corner 与 policy 解释一致
- `constraint_policy: all_corners` 下每个 corner 的约束结果都有证据
- 下一批参数使用的是聚合 observation
- 报告没有把 best observed feasible candidate 写成全局最优
- fix-run 报告没有创建 optimizer state 或 optimizer decision report
