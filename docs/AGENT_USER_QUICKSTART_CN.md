# IC Auto Opt 使用说明：给集成电路用户看的版本

这份说明面向集成电路专业的使用者。你不需要理解本项目的全部代码，也不需要
在聊天窗口里反复描述电路细节。正确用法是：把要求写进固定格式文件，然后在
你正在使用的 agent 窗口里发一条短命令。

## 一句话目标

你希望最终这样使用：

```text
/ic-opt ~/spectre_opt_prj/项目名 --doctor
/ic-opt ~/spectre_opt_prj/项目名 --real
/ic-opt --ssh-profile eda-lab /remote/path/to/项目名 --real
```

如果看完报告后想在已有 N 个点基础上继续追加 M 个点：

```text
/ic-opt ~/spectre_opt_prj/项目名 --continue M
/ic-opt --ssh-profile eda-lab /remote/path/to/项目名 --continue M
```

然后 agent 自动完成：

1. 读取你的 `opt_requirement.md`；
2. 先运行 doctor，检查 `opt_requirement.md`、Maestro/ADE point root、环境文件和
   SSH 是否准备好；
3. 生成 optimizer 所需 YAML 配置；
4. 复制 Maestro/ADE 已经跑通过的 netlist bundle；
5. 检查项目是否可以真实运行；
6. 调用 `ic-opt` 跑 Spectre/OCEAN/OpenBox 优化流程；
7. 读取报告，并告诉你最佳已观察点、指标、约束通过情况和下一步建议。

## 先分清两个入口

### 1. Shell 自动化入口

```bash
ic-opt PROJECT_DIR --doctor
ic-opt PROJECT_DIR --real
ic-opt PROJECT_DIR --continue 40
ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real
```

这是自动化脚本入口。它可以自己跑完整流程，适合调试和命令行用户。

### 2. Agent 产品入口

```text
/ic-opt PROJECT_DIR --doctor
/ic-opt PROJECT_DIR --real
/ic-opt PROJECT_DIR --continue 40
/ic-opt --ssh-profile PROFILE REMOTE_PROJECT --real
/ic-opt --ssh-profile PROFILE REMOTE_PROJECT --continue 40
```

这是 agent 入口。agent 的默认职责是根据平台无关 skill 操作 `ic-opt` CLI，
等待流程完成，读取报告并解释结果。native subagent 只是可选高级模式，不是默认
产品路线。

对新的或修改过的项目，agent 应先执行 `--doctor`。doctor 不通过时，agent 应停止并
指出具体文件、字段或路径问题，而不是继续跑真实 Spectre/OCEAN。
本地 doctor 是独立检查命令，不需要也不应该加 `--real`。如果 doctor 或 optimizer
JSON 报告里有 `structured_issues`，agent 应优先读取其中的 `code`、
`likely_cause`、`recommended_action` 和 `evidence`，再回退到普通 `issues`。

如果项目在远程 Linux EDA 服务器上，用户只需要提供 SSH profile 和远程项目路径。
agent 不应该把项目复制成本地流程，也不应该在远程服务器上安装 Python 包。

## 第一次安装

进入 `ic-auto-opt-workflow` 仓库：

```bash
cd /path/to/ic-auto-opt-workflow-v0.1
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

## 给 agent 使用的 skill

平台无关 skill 在：

```text
skills/ic-opt/SKILL.md
```

任何能运行 shell 命令、读取文件的 agent 都可以按这个 skill 工作。不同 agent
平台的 skill 安装目录可能不同；把这份 `SKILL.md` 放到你当前 agent 能读取的
skill/command 目录即可。这个 skill 本身不绑定任何具体 agent 平台。

如果你是用 `pip install` 安装的，而不是从源码目录里使用，可以用下面命令找到
安装后的 skill 文件：

```bash
hermes-workflow agent-skill-path
```

## 配置 Cadence/Spectre/OCEAN 环境

你需要提供一个 `csh` 环境脚本，比如：

```text
/path/to/cadence_env.csh
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

远程模式下，`cadence_env.csh` 放在远程项目目录或用远程路径传给
`--cadence-cshrc`。本机只需要能通过免密 SSH 登录远程服务器：

```bash
ssh -o BatchMode=yes eda-lab true
```

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

打开你正在使用的 agent 窗口，并确认它能读取 `skills/ic-opt/SKILL.md`。

然后只发一句：

```text
/ic-opt ~/spectre_opt_prj/项目名 --real
```

如果报告建议继续优化，或者你想追加更多点数，再发一句：

```text
/ic-opt ~/spectre_opt_prj/项目名 --continue 40
```

正常情况下，agent 会：

1. 运行 doctor 检查 `opt_requirement.md`、point root、环境文件和 SSH；
2. 生成配置；
3. 生成执行包；
4. 调用 `ic-opt` CLI 真实运行；
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

`optimizer_visuals/` 默认是 PNG 图片。agent 汇报结果时应优先引用这些图片路径，
不要要求用户打开 SVG。

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
- 远程 SSH 免密登录或 host key 没准备好；
- 远程高并发触发 SSH 连接限制，需要降低 `parallel_jobs`；
- agent 问你是否接受当前 best observed；
- 你想继续追加更多 evaluations；
- 你想改搜索范围、FoM 或约束。

遇到报错时，先看：

```text
docs/TROUBLESHOOTING_CN.md
```

常见情况包括 `opt_requirement.md` 格式错误、Maestro point root 层级错误、OCEAN
非标量、SSH `Host key verification failed`、`Permission denied`、远程高并发
`kex_exchange_identification` 和旧版本 manifest missing。

当前边界：agent skill 的默认路线是单 agent 操作 `ic-opt` CLI。用户说“请再进行
40 个点的优化”时，agent 应转换成 `ic-opt PROJECT --continue 40`。续跑时 agent
不应随手覆盖 `parallel_jobs`，应默认继承项目 `config/spectre.yaml` 里的资源设置，
除非用户明确要求改变资源。

## 一句原则

用户少说话，文件多承载。

机器关键内容写进 `opt_requirement.md`；用户偏好和解释写进 `constraints.md`；
agent 窗口只需要一句：

```text
/ic-opt PROJECT_DIR --real
```
