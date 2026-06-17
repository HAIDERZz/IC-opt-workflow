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
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
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
