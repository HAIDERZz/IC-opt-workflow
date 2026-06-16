# IC Auto Opt Workflow v0.1.8 使用说明

IC Auto Opt 用 `opt_requirement.md` 描述一次真实 Spectre/OCEAN 工作流。当前
release 支持两种模式：

- `optimize`：运行优化器，搜索满足约束的候选参数
- `fix_run`：运行用户指定的固定参数点，导出指定 waveform CSV，不创建优化器状态

两种模式都通过 `opt_requirement.md` 的 `Workflow.mode` 选择。没有单独的 fix-run
命令行开关。

## 常用入口

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

`--continue N` 只用于已经存在的优化任务。初次运行的预算、batch size、并行数、
Spectre 线程数、优化器 CPU 限制、算法、策略、初始化、工艺角、输出格式、
metric 公式、固定点和 waveform export 都来自 `opt_requirement.md`。

## 安装

在 release 根目录执行：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

检查入口：

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## Cadence 环境

`ic-opt` 按下面顺序寻找 Cadence setup：

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

这个脚本需要能找到 `spectre`、`ocean` 和 license 工具。不要把 `.bashrc` 或
`.zshrc` 当作 Cadence `csh` 环境脚本。

## 项目目录

推荐结构：

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

只需要手写 `opt_requirement.md`。`constraints.md` 用来放人工偏好和说明，不会生成
真实执行合同。`config/`、`netlists/`、`runs/`、`reports/`、`ledger/` 和
`state/` 由工具生成。

每个 testbench 先在 Maestro/ADE 中跑一个已知可用点，然后把 point root 写入
`opt_requirement.md`。point root 必须包含：

```text
<maestro_point_root>/netlist/input.scs
```

## Requirement 模板

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
```

`opt_requirement.fix_run.md` 以真实跑通的 15-corner Mixer requirement 为结构基准。
使用时把它复制为项目根目录的 `opt_requirement.md`，替换 Maestro point root、
固定参数点、corner 变量和 waveform export。

## 优化模式

优化 requirement 可以省略 `Workflow` section；省略时默认 `mode: optimize`。

优化 requirement 写：

- Maestro/ADE point root 和 testbench 路由
- design variables、范围和 step
- OCEAN scalar metric 表达式
- constraints 和 objective
- Spectre 设置：`parallel_jobs`、`threads_per_run`、`output_format: psfxl`
- 优化器设置：`algorithm`、`strategy`、`max_evaluations`、`batch_size`
- `optimizer_cpu_threads`
- `initialization` 和 `random_seed`
- license probe 和 artifact 保留策略
- `Process Corners`，如果需要多工艺角

生产使用时，把下面三种策略看成并列选择：

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`

`random_baseline` 用于诊断，不作为生产优化策略。

## Fix-Run 模式

fix-run requirement 必须写：

```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

并包含：

- `Fixed Points`：用户指定的一个或多个候选点
- `Waveform Exports`：需要导出的 waveform CSV，例如
  `getData("NF" ?result "pnoise")`
- `Spectre Settings`、`Process Corners` 和 approval checklist

fix-run 不运行优化器，不生成 `state/optimizer_state.json`，也不生成
`reports/optimizer_decision_report.md`。

示例中的 `temperature` 只是传给 netlist 的普通参数名，workflow 不会把它特殊映射成
Spectre simulator option。

## 多工艺角

多工艺角写在 `Process Corners`：

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

流程说明见 `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`。

## 看结果

优化报告：

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

fix-run 报告：

```text
reports/fix_run_report.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/metric_result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv
```

验收时不要只看退出码。必须检查报告和 child artifacts。

## Agent 使用

让 agent 操作时，把下面两个东西给它：

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

agent 应调用同一个产品 CLI，并检查上述过程文件后再汇报。
