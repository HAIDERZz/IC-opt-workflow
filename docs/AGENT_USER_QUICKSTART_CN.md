# IC Auto Opt Agent 使用速查

agent 操作当前版本的 IC Auto Opt 时，只做三件事：读取
`opt_requirement.md`、调用产品 CLI、检查过程文件后汇报。

`opt_requirement.md` 是初次运行的唯一配置入口。它通过 `Workflow.mode` 选择
优化或 fix-run。预算、并行数、Spectre 线程数、优化器 CPU 限制、算法、策略、
初始化、工艺角、输出格式、metric 公式、固定点和 waveform export 都在这个文件里。

## 命令

Local:

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
```

Remote:

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`--continue N` 是追加仿真入口。`--ssh-profile PROFILE` 只选择远端执行 profile，
不是资源或优化器覆盖。

## History Warm Start

`History Warm Start` 是新建 optimize 项目时引用同一电路旧项目历史的入口，不是
`--continue N`。`--continue N` 只给同一个项目追加预算，不重新读取用户改过的
`opt_requirement.md`。History warm-start 不支持 fix-run，也不能和 `--continue` 一起跑。

最小 section：

```yaml
enabled: true
sources:
  - path: /path/to/previous_same_circuit_project
    label: round1
max_observations: 200
warm_start_strategy: topk
```

它会生成 `config/history_warm_start.yaml`。第一版要求新旧项目变量名完全一致，metric
定义一致；旧点超出当前空间会记为 `out_of_current_space`。运行后必须检查
`reports/history_warm_start_audit.json`、`reports/history_warm_start_audit.md`，以及
`reports/optimizer_run_report.json` 里的 `openbox.history_warm_start`。有约束项目通常显示
`initial_configurations_from_history`；无约束单目标项目才可能显示
`transfer_learning_history`。

## Optimizer Insight Report

优化或 finalize 后，agent 应优先查看：

```text
reports/optimizer_insight_report.html
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
```

HTML 是给用户阅读的主报告；JSON 是机器可读合同；Markdown 是文本备份。
Pareto/trade-off 分析只基于已有 raw metrics 做报告层 trade-off 总结，不表示
OpenBox 已启用 multi-objective optimizer mode，也不改变 candidate 选择或 objective。
Space Compression Advisory 使用 OpenBox compressor dry-run，只给出人工复盘建议，
不会自动应用到 optimizer。用户认可后，可以把建议范围写进新的
`opt_requirement.md` 再开下一轮。

## Requirement 内容

- Maestro/ADE point root 和 testbench 定义
- OCEAN metric 表达式
- design variables、范围和 step
- constraints 和 objective
- `max_evaluations`、`batch_size`
- Spectre `parallel_jobs`、`threads_per_run`
- `optimizer_cpu_threads`
- `algorithm`、`strategy`、`initialization`、`random_seed`
- `output_format: psfxl`
- Process Corners 和 multi-corner policy
- retention、license check、artifact policy

fix-run requirement 还包含：

- `Workflow.mode: fix_run`
- `Fixed Points`
- `Waveform Exports`

fix-run 不创建 optimizer state，也不写 optimizer decision report。

fix-run 中 `parallel_jobs` 是同一个 fixed point 内 testbench/corner child 的并发数；
`threads_per_run` 是每个 Spectre 子进程的线程数。fixed points 仍串行执行，agent
不能添加 CLI 参数来覆盖这个值。

## 优化策略

生产使用时，把下面三种策略看成并列选择：

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

TuRBO 适合变量合法 step 足够细的场景，例如约 `0.1u`。step 很粗、
finger count 类整数、类别变量、或大量候选点 snap 后重复时，优先考虑
`openbox_prf_eic`。

`random_baseline` 只用于诊断。

## Multi-Corner

多工艺角通过 `opt_requirement.md` 的 `Process Corners` 配置。示例：

```text
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

agent 需要报告 objective policy、constraint policy、被选中的 run、各 corner
聚合结果，以及 worst-case 或 all-corners 约束判断。

## Fix-Run

fix-run 使用同一个产品命令：

```bash
ic-opt PROJECT_DIR --real
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

使用模板：

```text
examples/spectre_maestro_project/opt_requirement.fix_run.md
```

正确的 pnoise waveform expression 形式是：

```text
getData("NF" ?result "pnoise")
```

## 必查过程文件

不要只看退出码。真实 workflow 验收至少看：

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.html
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

multi-testbench / multi-corner 项目还要看 parent aggregate manifest。

fix-run 项目必须看：

```text
reports/fix_run_report.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv
```

重点核对 requirement 变量是否传递并生效：算法、策略、初始化、随机种子、budget、
batch size、并行数、Spectre 线程数、optimizer CPU cap、process corners、
`output_format: psfxl`、license probe 和 `command_trace`。
