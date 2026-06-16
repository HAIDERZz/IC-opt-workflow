# IC Auto Opt Agent 使用速查

这份文档说明如何让 agent 操作当前版本的 IC Auto Opt。核心原则很简单：
`opt_requirement.md` 是初次运行的唯一配置入口，agent 只负责读取它、调用产品
CLI、检查过程文件并汇报结果。

## 两个入口

标准产品入口：

```bash
ic-opt PROJECT_DIR --real
```

追加仿真入口：

```bash
ic-opt PROJECT_DIR --real --continue N
```

让 agent 协助时，把 `skills/ic-opt/SKILL.md` 和项目目录交给 agent。agent 仍应
调用上面的产品 CLI，不应让用户在聊天里重新描述公式、变量范围、并行数、线程数、
优化算法或工艺角。

## opt_requirement.md 负责什么

下面这些初次运行配置都必须写在 `opt_requirement.md`：

- Maestro/ADE point root 和 testbench 定义
- OCEAN metric 表达式
- design variables、范围、step
- constraints、objective 或 FoM
- `max_evaluations`、`batch_size`
- Spectre `parallel_jobs`、`threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`、`strategy`、`initialization`、`random_seed`
- `output_format: psfxl`
- Process Corners 和 multi-corner policy
- retention、license check、artifact 策略

产品 CLI 只保留本文列出的操作入口。唯一保留的数量变化入口是
`--continue N`，用于在已有 run 基础上追加 N 个新仿真点。

## Local 和 Remote

Local doctor：

```bash
ic-opt PROJECT_DIR --doctor
```

Local real run：

```bash
ic-opt PROJECT_DIR --real
```

Remote doctor：

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
```

Remote real run：

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

`--ssh-profile PROFILE` 只选择远端执行 profile，不是 optimizer/resource 覆盖。

## 优化策略

当前文档中应把下面三种生产策略作为并列选项解释：

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`openbox_auto` 是默认自动模式。`random_baseline` 只用于诊断。TuRBO 适合变量
合法 step 足够细、连续候选点 snap 到合法网格后扰动很小的场景，例如约 `0.1u`；
step 很粗、finger count 类整数、类别变量、或大量候选点 snap 后重复时，不优先用
TuRBO。

## Multi-Corner

多工艺角通过 `opt_requirement.md` 的 Process Corners 配置。示例：

```text
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

agent 汇报结果时，应说明 objective/constraint policy、被选中的 run、各 corner
聚合结果，以及 worst-case 或 all-corners 约束判断。

## Agent 必须检查的过程文件

不能只看 CLI 退出码。真实 workflow 验收至少要看：

- `reports/project_doctor_report.json`
- `reports/license_probe_report.json`
- `reports/optimizer_run_report.json`
- `reports/optimizer_decision_report.md`
- child `result_manifest.json`
- child `metric_result_manifest.json`
- multi-testbench / multi-corner parent aggregate manifest

重点核对 requirement 变量是否传递并生效：算法、策略、初始化、随机种子、budget、
batch size、并行数、Spectre 线程数、optimizer CPU cap、process corners、
`output_format: psfxl`、license probe 和 `command_trace`。
