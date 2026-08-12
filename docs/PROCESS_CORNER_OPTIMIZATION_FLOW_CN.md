# 多工艺角优化流程

多工艺角由 `opt_requirement.md` 的 `Process Corners` 配置。优化器不会只看某一个
corner，也不会为每个 corner 单独维护一套搜索历史。每个候选参数会先跑完配置的
testbench/corner 组合，再聚合成一个 optimizer observation。

`objective_policy`/`constraint_policy` 只在 `Workflow.mode: optimize` 下由用户
配置生效；`Workflow.mode: fix_run` 下这两个字段**不允许用户显式填写**——写了
就在 intake 阶段直接报错拒绝，省略时内部渲染才会用 `nominal`/`nominal` 补齐，
见下方「fix-run 与 Process Corners」一节——这是本文档最容易踩坑的一点，请优先读。

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
  - id: nominal
    model_file: /abs/path/to/nominal_models.scs
    variables:
      temperature: '27'
```

`objective_policy` 决定多个 corner 的 objective 如何合成，取值只有
`nominal` 或 `worst_case`。`constraint_policy` 决定约束如何判定，取值只有
`nominal` 或 `all_corners`。两者独立配置，不要求一致。

只要 `objective_policy` 或 `constraint_policy` 任一取值为 `nominal`，
`corners` 列表里就必须存在一个 `id: nominal` 的 corner，否则请求校验阶段就会
失败（`nominal policy requires a corner with id 'nominal'`）。聚合阶段
（`multi_testbench_aggregation`）对 `objective_policy == nominal` 这一种情况
另有一道独立的 fail-closed 检查（同样的 `ValueError`），作为二次防线。上面示例
同时用了 `worst_case`/`all_corners`，因此不强制要求 `nominal` corner；如果把
`objective_policy` 或 `constraint_policy` 任一改成 `nominal`，就必须像示例里
一样补一个 `id: nominal` 的 corner。

corner 除了示例中的 `model_section`（选择同一个 model 文件里的 section）外，还
支持 `model_file`（指定一个不同的、绝对 POSIX 路径的 model 文件，用于整体切换
模型库）与 `description`（自由文本说明）。

### 未配置 `Process Corners` 段时的默认形态

`opt_requirement.md` 如果没有 `Process Corners` 段，intake 会自动生成：

```yaml
objective_policy: nominal
constraint_policy: nominal
corners:
  - id: nominal
```

也就是单角工程本质上是 `Process Corners` 的一个默认特例；报告里
`corner: null`/单一 `nominal` corner 就是这个默认形态的体现，不代表配置缺失。

## 单个候选点流程

```text
candidate parameters
  -> render each configured testbench/corner child
  -> run Spectre/OCEAN for each child, one after another (serial)
  -> collect child metrics and statuses
  -> build parent aggregate manifest
  -> compute one aggregate objective/status
  -> send one observation to optimizer
```

**一个候选点内部的 testbench × corner child 是串行执行的**（双层
`for testbench_id: for corner_id:` 循环，无并发）。`batch_size` 与
`spectre.parallel_jobs` 控制的并行度只作用在**候选点之间**，不会让同一个候选点
的多个 child 并行跑。因此单候选点的墙钟时间 ≈ 该候选所有 child 仿真时长之和；
一个 3 testbench × 3 corner 的工程，单候选就是 9 次串行 Spectre 仿真。估算总
墙钟时间时，用「单候选串行时长 × 候选总数 / 候选间并行度」而不是简单除以
`parallel_jobs`。

child manifest 记录单个仿真的 Spectre/OCEAN 结果。parent aggregate manifest 记录
这个候选点在所有 child 上的聚合结果。

## Objective 和 Constraint

常用策略：

- `objective_policy: worst_case`：优化器使用 worst-case corner objective。
- `constraint_policy: all_corners`：所有 corner 都满足约束时，候选点才可行。

### corner 选择优先级：先约束、后 objective

聚合报告里的 `selected_corner`/`worst_corner` 不是单纯按 `objective_policy`
选出来的——判定顺序是**先约束、后 objective**：

1. 只要存在违反约束的 corner（按 `constraint_policy` 决定检查哪些 corner），
   `selected_corner`（同时也是 `worst_corner`）就取**违规 corner 中 objective
   最大的那个**，与 `objective_policy` 无关。这也是 `aggregate_status` 变成
   `constraint_failed` 的路径。
2. 只有当所有相关 corner 都可行时，才按 `objective_policy` 选：`nominal`
   取 `nominal` corner 的 objective；`worst_case` 取所有 corner 中 objective
   最大的作为 `worst_corner`。

这解释了为什么报告里 `selected_corner` 有时和「objective 最差的可行 corner」
不一致——一旦有违规 corner，规则会先看约束。

### 失败语义：fail-closed，不是逐 corner 罚分

任一 child 的 real 结果失败（`real_failed`），**整个父候选**就标记
`aggregate_status = real_check_failed`、`RealRunResultStatus.FAILED`，随后
后端把**整条候选**按 `failure_penalty` 记入 optimizer history。这不是「该
失败 corner 单独打惩罚分、其余可行 corner 仍参与聚合」——只要有一个 child
失败，这一整个候选点的所有 corner 数据都不会进入 objective/constraint 判定，
history 里只留一条 `failure_penalty` 记录。

报告里的推荐点是 best observed feasible candidate，不是全局最优证明。

## 优化器如何使用多 corner 结果

优化器看到的是聚合后的单条 observation：

```text
parameters -> aggregate objective/status -> optimizer history
```

OpenBox 和 native TuRBO 都使用这个聚合 observation 生成下一批候选参数。

## fix-run 与 Process Corners（重要：语义与 optimize 不同）

fix-run **可以**使用同一个 `Process Corners` 结构渲染 testbench/corner
child，但两个 policy 字段在 fix-run 下的语义和 optimize 完全不同：

- `Workflow.mode: fix_run` 下，requirement 的 `Process Corners` 段**不允许
  用户显式填写** `objective_policy`/`constraint_policy`——只要这两个字段
  任一出现在 requirement 里（不论写的是什么值，哪怕就是写 `nominal`），
  intake 校验阶段就直接失败，报错 "Process Corners aggregation policies
  are not supported for fix_run workflow; fix-run executes every declared
  corner"（见 `requirement_intake.py` 的
  `_validate_requirement_section_models`）。也就是说，把本文档开头
  「Requirement 配置」一节的 `worst_case`/`all_corners` 示例原样抄进一个
  fix_run 工程，intake 会**直接报错拒绝**，而不是静默接受或静默丢弃用户
  写的值。
- 只有当 requirement 里**完全省略**这两个字段时，intake 才会在内部为
  `ProcessCornerConfig` schema 校验补上 `objective_policy: nominal`、
  `constraint_policy: nominal` 这两个默认值。这只是满足校验模型所需的内部
  渲染细节，不是"覆盖用户填写的值"——按上一条规则，用户在 fix_run 下根本
  不能填写这两个字段，也就无所谓"覆盖"。

fix-run **不进入 optimizer aggregation**：它不调用 `multi_testbench_aggregation`
模块，不生成 `reports/multi_testbench_aggregation_report.json`，也没有
"parent aggregate manifest"、聚合后的 objective/status，或
`selected_corner`/`worst_corner` 这些概念（那些是 optimize 工作流专属，见下一
节）。每个固定点在各 testbench/corner child 上各自的仿真、metric 和 waveform
export 结果，会被直接收集进 `FixRunPointReport`，再汇总成一份 `FixRunReport`
（写入 `reports/fix_run_report.json`），供人工逐 child 核对（见
`fix_run_flow.py` 的 `run_fix_run_project`）。fix-run 也不会生成 optimizer
observation，不会进入下一批候选参数。

## 验收时看什么

真实验收时检查（`RUN_ID` 形如 `real_001`）。**optimize** 工作流的产物树：

```text
PROJECT_DIR/
  reports/
    multi_testbench_aggregation_report.json   # 最近一次候选的聚合报告（仅 optimize）
    optimizer_decision_report.md
  runs/real/<RUN_ID>/
    result_manifest.json                       # 父 result manifest（仅 optimize）
    metrics/metric_result_manifest.json         # 父 metric manifest（仅 optimize）
    multi_testbench_aggregation_report.json     # 同一份聚合报告的按-run 副本（仅 optimize）
    testbenches/<TESTBENCH_ID>/
      corners/<CORNER_ID>/
        result_manifest.json                    # child result manifest
        metrics/metric_result_manifest.json      # child metric manifest
```

`reports/multi_testbench_aggregation_report.json` 与
`runs/real/<RUN_ID>/multi_testbench_aggregation_report.json` 内容相同，是同一
份报告的两个落盘位置。报告里与验收直接相关的字段：

| 字段 | 含义 |
| --- | --- |
| `child_statuses` | 每个 testbench/corner child 的 result/metric 状态列表 |
| `objective_policy` / `constraint_policy` | 本次聚合实际生效的两个 policy |
| `selected_corner` / `worst_corner` | 按上面「先约束、后 objective」规则选出的 corner |
| `corner_objectives` | 每个 corner 各自的 objective 值 |
| `corner_status_counts` | 各 corner 状态（`feasible`/`constraint_failed`/`metric_failed`）计数 |
| `corner_metrics` | 每个 corner 的 metric 名到数值的映射 |

重点核对：

- `child_statuses` 列出了预期的 testbench/corner child，数量与
  `Process Corners.corners` × testbench 数一致
- `selected_corner`、`worst_corner` 与「先约束、后 objective」的选择规则解释
  一致，不要默认它等于 objective 最差的 corner
- `constraint_policy: all_corners` 下每个 corner 的约束结果都有证据
  （`corner_status_counts`/`corner_metrics`）
- 下一批参数使用的是聚合 observation，而不是某个单一 corner 的结果
- 报告没有把 best observed feasible candidate 写成全局最优

**fix-run** 工作流的产物树没有上面这套聚合结构——不存在
`multi_testbench_aggregation_report.json`，也不存在 `runs/real/<RUN_ID>/`
根目录下的父 `result_manifest.json`/父 `metrics/metric_result_manifest.json`
（这些都由 `multi_testbench_aggregation` 模块生成，fix-run 流程不调用它）：

```text
PROJECT_DIR/
  reports/
    fix_run_report.json                        # 仅 fix-run 工作流
  runs/real/<RUN_ID>/
    testbenches/<TESTBENCH_ID>/
      corners/<CORNER_ID>/
        result_manifest.json                    # child result manifest
        metrics/metric_result_manifest.json      # child metric manifest
```

fix-run 重点核对：

- fix-run 报告（`FixRunReport`，即 `reports/fix_run_report.json`）没有创建
  optimizer state 或 optimizer decision report
  （`optimizer_state_created`/`optimizer_decision_report_created` 两个字段
  恒为 `false`），也没有 `objective_policy`/`constraint_policy`、
  `selected_corner`/`worst_corner` 这类聚合字段——它只按固定点列出每个
  child 的 manifest 路径和 issue，核对时逐 child 看，不要去找一份不存在的
  聚合结果
- 要核对 fix-run 实际生效的 policy，去看物化后的
  `config/process_corners.yaml`：只要 requirement 省略了
  `objective_policy`/`constraint_policy`（fix-run 下唯一允许的写法），里面
  就会是 `objective_policy: nominal`、`constraint_policy: nominal`；如果
  requirement 显式写了这两个字段中任意一个，工程在 intake 阶段就已经报错
  退出，不会走到这一步
