# IC Auto Opt 使用说明：给集成电路用户看的版本

这份说明面向集成电路专业的使用者。你不需要理解本项目的全部代码，也不需要
在聊天窗口里反复描述电路细节。正确用法是：把要求写进固定格式文件，然后在
你正在使用的 agent 窗口里发一条短命令。

## 一句话目标

你希望最终这样使用：

```text
/ic-opt /home/你的用户名/spectre_opt_prj/项目名 --real
```

然后 agent 自动完成：

1. 读取你的 `opt_requirement.md`；
2. 生成 optimizer 所需 YAML 配置；
3. 复制 Maestro/ADE 已经跑通过的 netlist bundle；
4. 检查项目是否可以真实运行；
5. 派一个执行 subagent 去跑 Spectre/OCEAN/OpenBox；
6. 主管 agent 读取报告，并告诉你最佳已观察点、指标、约束通过情况和下一步建议。

## 先分清两个入口

### 1. Shell 自动化入口

```bash
ic-opt PROJECT_DIR --real
```

这是自动化脚本入口。它可以自己跑完整流程，适合调试和命令行用户。

### 2. Agent 产品入口

```text
/ic-opt PROJECT_DIR --real
```

这是 agent 入口。当前 agent CLI 的主会话是 supervisor agent，它应该调用同
一个 CLI 里的 execution subagent 来执行真实优化任务。

C-65 之后，项目目标是第二种：你在 Claude、OpenCode、Codex 等当前 agent
窗口里发一句 `/ic-opt ...`，由当前 runtime 自己派 subagent。不是让 OpenCode
或 Codex 再去调用 `claude -p`。

## 第一次安装

进入 `ic-auto-opt-workflow` 仓库：

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
```

创建并安装产品 Python 环境：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

确认命令存在：

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

## 安装你正在用的 agent 入口

如果你用 Claude：

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
```

如果你用 OpenCode：

```bash
./.venv/bin/hermes-workflow install-runtime-adapter opencode
```

检查安装状态：

```bash
./.venv/bin/hermes-workflow runtime-adapter-status
```

## 配置 Cadence/Spectre/OCEAN 环境

你需要提供一个 `csh` 环境脚本，比如：

```text
/home/你的用户名/cadence_env.csh
```

推荐放到用户级固定位置：

```bash
mkdir -p ~/.ic-opt
cp /path/to/你的/cadence_env.csh ~/.ic-opt/cadence_env.csh
```

也可以放在每个项目目录里：

```text
PROJECT_DIR/cadence_env.csh
```

本项目不会自动猜 `.bashrc` 或 `.zshrc`，也不会硬编码某个 Spectre 版本。

## 创建一个优化项目

推荐目录：

```text
~/spectre_opt_prj/项目名/
├── opt_requirement.md
├── constraints.md
└── context/
```

只必须有 `opt_requirement.md`。`constraints.md` 是给主管 agent 看的额外说明，
比如“某些偏置区不建议使用”“优先看 NF”“这次先粗略跑 100 点”等。

不要手动创建这些目录：

```text
config/
netlists/
runs/
reports/
ledger/
state/
execution_package/
```

这些由 Hermes 自动生成。

## opt_requirement.md 写什么

当前产品合同：初次真实优化的机器关键变量只能来自 `opt_requirement.md` / 生成的
config，包括 `max_evaluations`、`batch_size`、`parallel_jobs`、
`threads_per_run`、`optimizer_cpu_threads`、optimizer strategy、
initialization、output format、保留策略、metric 公式、约束和多工艺角设置。
不要在 `ic-opt PROJECT --real` 后追加 `--max-evals`、`--batch-size`、
`--parallel-jobs`、`--threads` 或 `--strategy`。续跑只保留一个命令行入口：
`ic-opt PROJECT --real --continue N`，表示追加 N 个评估点，其余配置仍从项目
requirement/config 继承。

多工艺角通过 `opt_requirement.md` 的 `Process Corners` 配置。示例见
`examples/spectre_maestro_project/opt_requirement.multi_corner.md` 和
`examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md`。

`opt_requirement.md` 是机器要读的正式需求文件，不是聊天记录。

它要包含：

- 项目名；
- 一个或多个 Maestro/ADE point root；
- 设计变量和范围；
- OCEAN metric 公式；
- 约束条件；
- 优化目标或 FoM；
- Spectre 设置；
- optimizer 设置；
- 用户批准 checklist。

每个 Maestro/ADE point root 必须来自一次你确认能跑通的 Maestro/ADE 仿真点，
并且里面要有：

```text
maestro_point_root/netlist/input.scs
```

对于 Mixer 这类电路，如果 CG/NF、IIP3、P1dB 需要不同 testbench，就在
`opt_requirement.md` 里写多个 testbench。每个 metric 指明属于哪个
testbench。项目会保留每个 testbench 的原生 Maestro/ADE 文件结构，不会把它们
强行合成一个 Spectre deck。

## 正式运行

打开你使用的 agent CLI，比如 Claude 或 OpenCode。

然后只发一句：

```text
/ic-opt /home/你的用户名/spectre_opt_prj/项目名 --real
```

正常情况下，agent 会：

1. 检查 `opt_requirement.md`；
2. 生成配置；
3. 生成执行包；
4. 调用同 runtime 的 execution subagent 真实运行；
5. 写报告；
6. 汇报结果。

你不应该再把公式、变量范围、testbench 路径复制到聊天里。那些应该已经写在
`opt_requirement.md`。

## 结果看哪里

最重要的是：

```text
PROJECT_DIR/reports/optimizer_decision_report.md
```

它会告诉你：

- 一共跑了多少个点；
- feasible / constraint_failed / metric_check_failed 各有多少；
- 当前推荐点是哪一个；
- 推荐点的参数；
- 推荐点的指标；
- 这是不是全局最优。

注意：optimizer 给的是 `best observed`，也就是“已经跑过的样本中最好的点”，
不是数学证明的全局最优。

更详细的分析：

```text
PROJECT_DIR/reports/optimizer_insight_report.md
PROJECT_DIR/reports/optimizer_visuals/
PROJECT_DIR/reports/openbox_advanced_visualization/
```

## 常见状态是什么意思

`feasible`：

```text
这个点真实仿真成功，并且满足你写的约束。
```

`constraint_failed`：

```text
真实仿真和 OCEAN 计算成功，但这个点不满足约束。这通常是合法失败样本。
```

`metric_check_failed`：

```text
某些 metric 没有得到合法标量。可能是公式在这个候选点下无定义，也可能是用户
公式或 testbench 设置需要检查。
```

`real_check_failed`：

```text
真实工具、文件结构、license、环境或结果 manifest 出了结构性问题。
```

## 什么时候需要你介入

你通常只需要在这些时候介入：

- `opt_requirement.md` 格式写错；
- Maestro point root 路径不对；
- OCEAN 公式在已知正确点上都算不出标量；
- 约束过严，几乎没有 feasible 点；
- agent 问你是否接受当前 best observed；
- 你想继续追加更多 evaluations；
- 你想改搜索范围、FoM 或约束。

当前边界：C-66 已验证 Claude 能把“请再进行40个点的优化”这种短句转成
continuation 命令；后续也已经做了窄修复，使 OpenBox 在已有 100 个点后凑不满
完整唯一候选批次时可以使用部分批次继续。续跑时 agent 不应随手覆盖
`parallel_jobs`，应默认继承项目 `config/spectre.yaml` 里的资源设置，除非用户明确
要求改变资源。

## 一句原则

用户少说话，文件多承载。

机器关键内容写进 `opt_requirement.md`；用户偏好和解释写进 `constraints.md`；
agent 窗口只需要一句：

```text
/ic-opt PROJECT_DIR --real
```
