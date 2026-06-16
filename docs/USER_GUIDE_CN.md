# IC Auto Opt Workflow v0.1.7 使用说明

IC Auto Opt 用 `opt_requirement.md` 描述一次 IC 优化任务，然后运行
Spectre/OCEAN 和优化器，最后写出报告。普通用户只需要记住两个入口：

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
```

已有 run 继续追加点数：

```bash
ic-opt PROJECT_DIR --real --continue N
```

初次运行的预算、并行数、Spectre 线程数、优化器 CPU 限制、算法、策略、初始化、
工艺角、输出格式、metric 公式和约束都写在 `opt_requirement.md`。CLI 只负责选择
运行方式。

## 1. 安装

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

macOS 本机通常没有 Cadence 环境。推荐在本机运行优化器，用 remote 模式让
Spectre/OCEAN 在 Linux EDA 服务器上执行。Windows 推荐使用 WSL2 Ubuntu。

## 2. Cadence 环境

`ic-opt` 按下面顺序寻找 Cadence setup：

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

这个文件通常是用户已有的 `csh`/`tcsh` 环境脚本。它需要能找到 `spectre`、
`ocean` 和 license 工具。不要把 `.bashrc`、`.zshrc` 或硬编码的 Spectre 版本当作
产品配置。

## 3. 项目目录

推荐结构：

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

只需要手写 `opt_requirement.md`。`constraints.md` 可以放人工偏好和注意事项，
`context/` 可以放截图、旧报告或电路说明。`config/`、`netlists/`、`runs/`、
`reports/`、`ledger/` 和 `state/` 由工具生成。

每个 testbench 先在 Maestro/ADE 里跑一个已知可用点，然后把 point root 写进
`opt_requirement.md`。point root 必须包含：

```text
<maestro_point_root>/netlist/input.scs
```

## 4. opt_requirement.md 写什么

`opt_requirement.md` 至少需要描述：

- 项目名称和 Maestro/ADE point root
- design variables、范围和 step
- OCEAN metric 表达式
- constraints、objective 或 FoM
- Spectre 设置：`parallel_jobs`、`threads_per_run`、`output_format: psfxl`
- 优化器设置：`algorithm`、`strategy`、`max_evaluations`、`batch_size`
- `optimizer_cpu_threads`
- `initialization` 和 `random_seed`
- license probe 和 artifact 保留策略
- Process Corners，如果需要多工艺角

示例文件：

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
```

## 5. 优化算法

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

`openbox_auto` 是默认自动模式。`random_baseline` 用于诊断。TuRBO 适合变量 step
较细的场景，例如约 `0.1u`，因为连续候选点 snap 到合法网格后扰动很小。step 很粗、
finger count 类整数、类别变量或大量重复 snap 点的场景，不优先用 TuRBO。

详细说明见 `docs/OPTIMIZER_ALGORITHM_MODES.md`。

## 6. 多工艺角

多工艺角写在 `opt_requirement.md` 的 Process Corners 里。常见策略：

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

流程说明见 `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`。

## 7. Local 运行

先检查项目：

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
```

运行真实优化：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

追加点数：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

## 8. Remote 运行

remote 模式让本地负责优化器和报告，让远程 Linux EDA 服务器执行 Spectre/OCEAN：

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`PROFILE` 是本机 SSH 配置里的 profile。remote 模式不会在 EDA 服务器上安装本项目
或 OpenBox。

## 9. 看结果

优先看：

```text
reports/optimizer_decision_report.md
reports/optimizer_run_report.json
reports/license_probe_report.json
reports/project_doctor_report.json
```

真实仿真 trace 看：

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

多 testbench 或多工艺角项目还要看 parent aggregate manifest。重点确认：

- algorithm、strategy、initialization、random_seed 生效；
- budget、batch size、并行数、Spectre 线程数、optimizer CPU cap 生效；
- `output_format: psfxl` 生效；
- license probe 状态正确；
- `command_trace` 记录了 sanitized Spectre/OCEAN argv；
- 多工艺角结果按 configured policy 聚合。

报告里的推荐点是 best observed feasible candidate，不是数学意义上的全局最优证明。

## 10. Agent 使用

让 agent 操作时，把下面两个东西给它：

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

agent 应该调用同一个产品 CLI，并检查上面的过程文件后再汇报。release 包只保留
`skills/ic-opt/SKILL.md` 这一份 agent skill 说明。
