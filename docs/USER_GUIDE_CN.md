# IC Auto Opt Workflow v0.1.7 使用说明

IC Auto Opt 用 `opt_requirement.md` 描述一次 IC 优化任务。工具根据这个文件准备
Spectre/OCEAN 仿真、调用优化器、聚合 metric，并写出过程文件和报告。

常用入口：

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --real --continue N
```

`--continue N` 是保留的追加仿真入口。初次运行的预算、batch size、并行数、
Spectre 线程数、优化器 CPU 限制、算法、策略、初始化、工艺角、输出格式、
metric 公式和约束都来自 `opt_requirement.md`。

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

## 四个 Requirement 模板

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
```

这五个模板来自同一个已验证 Mixer requirement。真实路径已替换为占位路径。
使用时复制其中一个为项目里的 `opt_requirement.md`，再替换 Maestro point root、
变量范围、约束和公式。

## `opt_requirement.md` 写什么

- Maestro/ADE point root 和 testbench 路由
- design variables、范围和 step
- OCEAN metric 表达式
- constraints 和 objective
- Spectre 设置：`parallel_jobs`、`threads_per_run`、`output_format: psfxl`
- 优化器设置：`algorithm`、`strategy`、`max_evaluations`、`batch_size`
- `optimizer_cpu_threads`
- `initialization` 和 `random_seed`
- license probe 和 artifact 保留策略
- `Process Corners`，如果需要多工艺角

## 优化算法

生产使用时，把下面三种策略看成并列选择：

```yaml
algorithm: openbox
strategy: openbox_gp_eic
```

```yaml
algorithm: openbox
strategy: openbox_prf_eic
```

```yaml
algorithm: turbo
strategy: turbo_trust_region
```

TuRBO 适合变量 step 较细的场景，例如约 `0.1u`，因为连续候选点 snap 到合法网格
后的扰动很小。finger count 这类粗整数、类别变量或大量重复 snap 点的空间，优先
考虑 `openbox_prf_eic`。

`random_baseline` 用于诊断，不作为生产优化策略。

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

## Local 运行

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
./.venv/bin/ic-opt PROJECT_DIR --real
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

## Remote 运行

Remote 模式让本地负责优化器和报告，让远程 Linux EDA 服务器执行 Spectre/OCEAN：

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`PROFILE` 是本机 SSH 配置里的 profile。

## 看结果

主要报告：

```text
reports/project_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
```

真实仿真过程文件：

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

验收时检查：

- algorithm、strategy、initialization、random_seed 是否来自 requirement
- budget、batch size、并行数、Spectre 线程数、optimizer CPU cap 是否生效
- `output_format: psfxl` 是否生效
- license probe 是否执行并写入报告
- `command_trace` 是否记录 sanitized Spectre/OCEAN argv
- 多工艺角结果是否按 configured policy 聚合

## Agent 使用

让 agent 操作时，把下面两个东西给它：

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

agent 应调用同一个产品 CLI，并检查上述过程文件后再汇报。

## Fix-Run 模式

Fix-run 模式在用户指定的设计点上运行 Spectre/OCEAN 仿真，不启动优化器。
适用于已知参数值的验证、表征和波形导出。

在 `opt_requirement.md` 中设置 `Workflow.mode` 为 `fix_run`：

```yaml
## Workflow
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

使用与优化运行相同的命令启动：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

工作流根据 `opt_requirement.md` 中的 `Workflow.mode` 自动选择 fix-run 路径，
无需额外命令行参数。

### Fix-Run 需要的配置

- `Design Variables` — 参数声明（范围和步长）
- `Fixed Points` — 一个或多个要仿真的设计点
- `Process Corners` — 每个点的工艺角（可选）
- `Waveform Exports` — 导出为 CSV 的 OCEAN 表达式

### Fix-Run 输出

输出是仿真归档，不是优化报告。不会生成 `optimizer.yaml`、
`optimizer_state.json` 或 `optimizer_decision_report.md`。检查：

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```
