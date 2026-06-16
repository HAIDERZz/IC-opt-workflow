# IC Auto Opt Workflow v0.1.7 使用说明

这份说明面向集成电路方向用户，假设你会使用 Linux 和 Cadence，但不要求你熟悉
Python 工程。

## Hermes 这个名字是什么意思

Hermes 在这里指“信使层”：它把用户写在 `opt_requirement.md` 里的 IC 优化需求，
转换成可执行、可检查、可复现的 workflow contracts，包括 YAML 配置、仿真任务、
验收报告和图表。

因此：

- 用户入口是 `ic-opt` 命令。
- agent 入口也是 `ic-opt` 命令加 `skills/ic-opt/SKILL.md`。
- `hermes_workflow` 是内部 Python 包，负责解析、校验、生成合同、调用工具和写报告。

## 1. 这个项目是做什么的

你把优化需求写进一个标准格式的 `opt_requirement.md`，并提供 Maestro/ADE 已经
能跑通的 point root。然后运行：

```bash
./.venv/bin/ic-opt /path/to/project --real
```

当前产品合同：初次真实优化的机器关键变量只能从 `opt_requirement.md` / 生成的
config 进入，包括最大评估数 `max_evaluations`、批大小 `batch_size`、
候选并发 `parallel_jobs`、单个 Spectre 线程数 `threads_per_run`、优化器 CPU
线程限制 `optimizer_cpu_threads`、优化策略、初始化方式、输出格式、保留策略、
metric 公式、约束和多工艺角设置。不要在 `ic-opt PROJECT --real` 命令行追加
`--max-evals`、`--batch-size`、`--parallel-jobs`、`--threads` 或 `--strategy`。
续跑只保留 `ic-opt PROJECT --real --continue N`，表示追加 N 个评估点。

多工艺角通过 `opt_requirement.md` 的 `Process Corners` 配置，不存在
`--multi-corner` CLI 开关。示例见
`examples/spectre_maestro_project/opt_requirement.multi_corner.md` 和
`examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md`。

项目会自动完成：

```text
读取 opt_requirement.md
-> 生成标准 config/*.yaml
-> 导入 Maestro/ADE netlist bundle
-> 生成 optimizer execution package
-> 调用 OpenBox 产生候选点
-> 对每个候选点运行 Spectre
-> 用 OCEAN 计算指标
-> 聚合多 testbench 指标
-> 生成决策报告和可视化报告
```

如果 Cadence/Spectre/OCEAN 只能在 Linux EDA 服务器上运行，也可以用远程模式：

```bash
ic-opt --ssh-profile eda-lab /remote/path/to/project --real
```

这时 Python 优化器运行在你的本机或工作站上，Spectre/OCEAN 通过 SSH 在远程
Linux 服务器上运行。

## 2. 安装一次产品环境

只需要给工具本身建一个 Python 环境，不要在每个优化项目里建 venv。

```bash
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
python3 --version  # 需要 Python 3.11 或更新版本
python3 -m venv .venv
```

然后根据你当前使用的 shell，选择一种激活方式：

```bash
# bash / zsh
source .venv/bin/activate
```

```csh
# csh / tcsh，这在 EDA 服务器上很常见
source .venv/bin/activate.csh
```

激活后继续安装依赖：

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-product.txt
```

如果服务器上的 `python3` 不是 3.11 或更新版本，就使用管理员提供的 Python 3.11+
命令，例如 `python3.11` 或 `python3.12`。重点是 Python 版本要满足要求，不是命令
名字必须叫 `python3.11`。

### macOS 推荐安装方式

macOS 上可以先安装 Homebrew，然后安装 Python 3.11+ 和 Git：

```bash
brew install python@3.11 git
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-product.txt
python -m pip install -e .
```

macOS 本机通常没有 Cadence。推荐用后面的远程 SSH 模式，让 Spectre/OCEAN 在
Linux EDA 服务器上跑。

### Windows 推荐安装方式

Windows 上推荐使用 WSL2 Ubuntu，而不是直接在 PowerShell 里折腾 EDA 流程：

```bash
# 在 WSL2 Ubuntu 里执行
sudo apt update
sudo apt install python3 python3-venv python3-pip git openssh-client
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-product.txt
python -m pip install -e .
```

Windows 用户同样推荐使用远程 SSH 模式：项目和 Cadence 在 Linux 服务器上，本机
只负责运行优化器和查看报告。原生 Windows PowerShell 理论上也可能运行远程模式，
但当前 release 没有正式验证；如果你坚持不用 WSL2，需要自己确认 Python 3.11+、
`ssh`、`scp` 和本机 `tar` 都可用。遇到路径、权限或 tar/ssh 行为问题时，优先
切回 WSL2。

OpenBox 高级代理模型可视化是可选增强。基础优化、Spectre/OCEAN 执行、决策报告、
insight report、续跑和 doctor 检查都不应该被 `pyrfr` 阻塞。如果你需要 OpenBox 的
高级 surrogate verification / importance 图，再安装高级依赖：

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install swig
swig -version
python -m pip install --no-build-isolation pyrfr==0.9.0
python -m pip install -r requirements-advanced.txt
```

如果你已经 `pip install swig`，但仍然看到 `command 'swig' failed`，通常是因为没有
激活 `.venv`，导致 `.venv/bin/swig` 没有进入 `PATH`。先根据 shell 选择正确命令：

```bash
# bash / zsh
source .venv/bin/activate
swig -version
```

```csh
# csh / tcsh
source .venv/bin/activate.csh
swig -version
```

如果你在运行 `source .venv/bin/activate` 时看到 `Badly placed ()'s.`，说明当前 shell
是 csh/tcsh，但你用了 bash 版激活脚本。改用：

```csh
source .venv/bin/activate.csh
```

如果你不想激活 shell，也可以这样显式带上路径：

```bash
env PATH="$PWD/.venv/bin:$PATH" ./.venv/bin/python -m pip install -r requirements-product.txt
```

如果 `pyrfr` 报 `fatal error: Python.h: No such file or directory`，说明服务器缺少
当前 Python 对应的开发头文件。这不是项目代码错误，需要管理员安装和你的 `.venv`
所用 Python 匹配的系统包：

```bash
# Ubuntu / Debian
sudo apt install swig build-essential python3-dev

# RHEL / CentOS / Rocky / AlmaLinux
sudo dnf install swig gcc gcc-c++ python3-devel
```

如果你用的是 Python 3.11，包名也可能是 `python3.11-dev` 或 `python3.11-devel`，
取决于服务器发行版。如果你没有 `sudo`，也没有 `conda`，可以请管理员提供匹配的
Python 开发头文件、`swig`、编译器，或者提供一个已经包含这些依赖的
micromamba/conda 环境。

检查：

```bash
./.venv/bin/ic-opt --help
```

## 3. 准备你的优化项目

建议每个电路一个项目目录：

```bash
mkdir -p ~/spectre_opt_prj/Mixer_opt
```

目录里至少放：

```text
~/spectre_opt_prj/Mixer_opt/
  opt_requirement.md
  cadence_env.csh
```

可选：

```text
constraints.md
```

`cadence_env.csh` 是你自己能 source 后运行 Spectre/OCEAN 的环境设置文件。
不要在需求里写死 Spectre 版本。

## 4. 先做 doctor 体检

正式跑真实工具之前，强烈建议先执行：

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt --doctor
```

它会检查 `opt_requirement.md`、Cadence 环境文件、OpenBox/Hermes Python
环境、config/netlist 准备情况和 continuation 所需历史文件。它不会启动
Spectre/OCEAN，也不会生成优化候选点。

v0.1.6 之后，本地 `--doctor` 已经直接接入产品级 doctor 流程，不会误进入
optimizer，也不需要加 `--real`。因此它适合作为每个新项目或修改后项目的第一步。

如果你把任务交给 agent 做，agent 应该默认先运行 doctor。doctor 不通过时，不应
继续真实优化，而应先告诉你哪个文件、字段或路径有问题。因为
`opt_requirement.md` 是严格结构化文件，很多问题都属于章节名、字段名、缩进、
metric 名字或 Maestro point root 路径的小错误，先 doctor 能避免白跑真实工具。

## 5. 写 opt_requirement.md

参考：

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/OPT_REQUIREMENT_README.md
```

核心内容包括：

- 设计变量，比如 `F`, `W`, `L`, `VB_LO`
- 每个变量的范围和步进
- Maestro/ADE point root 路径
- 指标公式，也就是 OCEAN 可以计算的表达式
- 约束条件
- FoM / objective
- Spectre 并行资源设置

多 testbench 场景下，每个 metric 要写清楚来自哪个 testbench。例如 Mixer 可能有：

```text
cg_nf: 计算 CG / NF / BW
iip3: 计算 IIP3
p1db: 计算 P1dB
```

`opt_requirement.md` 至少需要 1 个 testbench。当只有一个 testbench 时，就是单 TB
特例；当一个 candidate 的指标必须从多个 Maestro/ADE 设置里取得时，再使用
`testbenches:` 列表。格式上没有固定最大数量，实际限制来自仿真时间、license、
磁盘空间和 `parallel_jobs`。

### Maestro/ADE point root 到底填哪一层

先在 Maestro/ADE 里把每个 testbench 跑通一次。然后去仿真结果目录里找单个
仿真点的 leaf 目录，常见形状是：

```text
~/simulation/<library>/<cell>/<test_name>/results/maestro/Interactive.<N>/<point>/<run_name>/
```

`maestro_point_root` 应该填最后这个 `<run_name>/` 目录。判断标准很简单：

```bash
ls <maestro_point_root>
# 应该能看到：netlist/  psf/

ls <maestro_point_root>/netlist/input.scs
# 应该能找到 input.scs
```

例如 ADE 结果路径是：

```text
.../results/maestro/Interactive.45/1/<run_name>/
```

那就把这一整层 leaf 目录填进 `maestro_point_root`。不要填
`Interactive.45`，不要填 `Interactive.45/1`，也不要填更深的 `netlist/`
或 `psf/` 子目录。

### FoM / objective 怎么写

`Objective` 不是 OCEAN 公式，而是用已经提取出来的 metric 名字做数学运算。脚本
内部的 optimizer 始终按“objective 越小越好”工作。

如果你的 FoM 本来就是越小越好，写：

```yaml
direction: minimize
expression: "(rise + fall) * DC"
```

如果你的 FoM 是越大越好，写 `direction: maximize`。工具会保留用户 FoM 原值，
并在内部自动转换成 `objective = -FoM` 交给最小化器：

```yaml
direction: maximize
expression: "gain / NF_3G"
```

对于多指标 RF/模拟电路，更推荐先把每个指标归一化成 0 到 1 的 score，再组合成
一个越大越好的综合分数。例如：

```yaml
direction: maximize
expression: >-
  0.7*min(
    max(0,min(1,10*(ln(BW/19e9)/ln(10))/0.5)),
    max(0,min(1,(MAX_GAIN-4)/0.5)),
    max(0,min(1,(12-NF_3G)/0.1)),
    max(0,min(1,(IIP3-0)/0.5)),
    max(0,min(1,(P1DB+2)/0.5))
  )
  +0.3*(
    0.15*max(0,min(1,10*(ln(BW/19e9)/ln(10))/0.5))
    +0.10*max(0,min(1,(MAX_GAIN-4)/0.5))
    +0.25*max(0,min(1,(12-NF_3G)/0.1))
    +0.30*max(0,min(1,(IIP3-0)/0.5))
    +0.20*max(0,min(1,(P1DB+2)/0.5))
  )
```

这里的 `min(...)` 是瓶颈分数，防止某一个指标很差但平均分很高；后面的加权和用于
在都满足基本要求时继续区分优劣。当前 objective 表达式支持 metric 名字、数字、
四则运算、括号，以及 `min(...)`、`max(...)`、`ln(...)`。

## 6. 先做离线检查

这个命令不会启动 Spectre/OCEAN：

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt --real --dry-orchestration
```

如果这里失败，通常是 `opt_requirement.md`、路径、格式或环境文件位置有问题。

## 7. 跑真实优化

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt --real
```

如果你的环境文件不叫 `cadence_env.csh`：

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt \
  --real \
  --cadence-cshrc /path/to/cadence_env.csh
```

真实运行必须能访问 Cadence license 和系统进程服务。不要在限制 sandbox 里运行
真实 Spectre/OCEAN。

## 8. 远程 SSH 模式

远程模式适合这种情况：

- 你的 Linux EDA 服务器不能随便安装 Python 包；
- 你的 Windows/macOS/Linux 本机可以安装这个项目；
- Cadence、PDK、license、Spectre/OCEAN 都在远程 Linux 服务器上；
- 优化项目目录也放在远程 Linux 服务器上。

远程项目目录和本地模式完全一样：

```text
/remote/path/to/Mixer_opt/
  opt_requirement.md
  constraints.md          # 可选
  cadence_env.csh         # 远程服务器上的 Cadence 环境文件
```

`--ssh-profile` 指的是本机 OpenSSH 能识别的连接名。它可以直接写成
`user@server`，但更推荐在本机 `~/.ssh/config` 里写一个稳定别名，这样命令更短，
也更不容易写错。

你需要自己配置免密 SSH 登录。推荐在本机 `~/.ssh/config` 写一个 profile：

```sshconfig
Host eda-lab
  HostName your.eda.server
  User your_user_name
  IdentityFile ~/.ssh/id_ed25519
```

如果本机还没有 SSH key，先生成一个：

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

然后把公钥放到远程 EDA 服务器。如果系统有 `ssh-copy-id`：

```bash
ssh-copy-id eda-lab
```

如果没有 `ssh-copy-id`，就把本机 `~/.ssh/id_ed25519.pub` 的内容追加到远程服务器的
`~/.ssh/authorized_keys`。这一步如果你不熟悉，建议让服务器管理员帮你做。

第一次连接远程服务器时，SSH 可能会询问是否信任 host key。先手动连一次：

```bash
ssh eda-lab true
```

看到 `Are you sure you want to continue connecting` 时，确认服务器地址没错后输入
`yes`。这一步只需要做一次。

然后确认不会要求输入密码：

```bash
ssh -o BatchMode=yes eda-lab true
```

这里的 `BatchMode=yes` 很重要。如果这条命令失败，说明免密 SSH 还没准备好，
不要继续跑 `ic-opt --ssh-profile`。

再确认远程项目文件确实存在：

```bash
ssh eda-lab 'test -f /remote/path/to/Mixer_opt/opt_requirement.md'
ssh eda-lab 'test -f /remote/path/to/Mixer_opt/cadence_env.csh'
```

上面两条命令没有输出、返回成功，就说明远程路径基本可用。

然后运行：

```bash
ic-opt --ssh-profile eda-lab /remote/path/to/Mixer_opt --doctor

ic-opt --ssh-profile eda-lab /remote/path/to/Mixer_opt --real

ic-opt --ssh-profile eda-lab /remote/path/to/Mixer_opt --real --continue 20
```

远程并发建议：

- `parallel_jobs` 在 `opt_requirement.md` 里设置，是 candidate 级别并发，
  不是每个 testbench 的并发数。
- 多 testbench candidate 会在每个 candidate 内部跑它需要的 testbench。
- 开启多 corner 后，这个语义也不变；单个 candidate 内部仍然按
  `testbench x corner` 串行执行。
- 正常远程多 testbench 或多 corner 项目，建议在 `opt_requirement.md`
  里从 `parallel_jobs: 4` 到 `parallel_jobs: 8` 开始。
- `parallel_jobs: 24` 或 `36` 更像压力测试，容易触发远程 SSH 服务端限制，比如
  `kex_exchange_identification: Connection closed by remote host`。
- `optimizer_cpu_threads` 只限制本机 optimizer/OpenBox 侧 CPU 使用，不限制远程
  Spectre/OCEAN 进程数量，也不限制 SSH 连接数。

### 候选 run 目录保留 (`keep_failed_runs` / `keep_successful_runs`)

`opt_requirement.md` 里的 `Spectre Settings.keep_successful_runs` 和
`keep_failed_runs` 控制每个候选点 `runs/real/<run_id>` 目录在结果记录完成后是否
保留。两个开关都在候选点 finalize 之后才生效，不会破坏 result_manifest、metric
聚合、目标函数计算或 `record_real_result` 需要的中间产物。

- `keep_successful_runs: true`：候选点产出可用真实观测时保留 run 目录。
  注意约束（constraint）失败但指标 scalar 全部有效的情况，仍然算"成功观测"，
  由这个开关控制。
- `keep_successful_runs: false`：结果记录完成后删除该 run 目录。
- `keep_failed_runs: true`：候选点在真实执行、metric 提取、聚合、结果检查或结果
  记录中失败时保留 run 目录方便排查。
- `keep_failed_runs: false`：失败被分类并写入报告后删除该 run 目录。

`ledger/`、`state/`、最佳候选状态、`reports/` 下的优化报告以及
`state/run_retention/<run_id>.json` 决策报告不会被这两个开关删除。远程模式下，
同一份策略也会清理远程 `<remote_project_dir>/runs/real/<run_id>`，仅在产物已下载
完毕后执行。

多 corner 只通过 `opt_requirement.md` 里的 `Process Corners` 配置启用，
没有 `--multi-corner` 命令行开关；如果不写这个 section，就保持原来的单 corner
行为。Monte Carlo 仍然不在这条 real-run 优化主流程里，建议作为后优化验证步骤。

如果远程 Cadence 环境文件不叫 `cadence_env.csh`，传入远程路径：

```bash
ic-opt --ssh-profile eda-lab /remote/path/to/Mixer_opt \
  --real \
  --cadence-cshrc /remote/path/to/cadence_env.csh
```

报告会保留在远程项目目录：

```text
/remote/path/to/Mixer_opt/reports/
```

同时也会镜像到本机：

```text
~/.ic-opt/remote_runs/<ssh-profile>/<project-hash>/reports/
```

远程模式不会在 EDA 服务器上安装 OpenBox 或本项目，也不会改变 Spectre/OCEAN 的
核心调用逻辑。它只是用 SSH 把“本地已验收的 Spectre/OCEAN 流程”搬到远程服务器
执行，并把报告同步回来。

## 9. 查看结果

优先看：

```text
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
reports/optimizer_final_summary.md
reports/optimizer_visuals/
```

`optimizer_visuals/` 默认输出 PNG 图片，包括 FoM、收敛、状态分布、约束 margin、
瓶颈分数和变量-目标关系图，适合直接在报告、agent 窗口或普通图片预览器里查看。

常见结论：

```text
accept_best_observed_or_continue
```

意思是当前有一个 best observed feasible 点，但不是全局最优证明。你可以接受，也
可以继续增加点数。

## 10. 继续追加优化

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt --real --continue 40
```

续跑时只接受继续点数 `N`：策略、资源、batch_size、parallel_jobs、Spectre 设置等
均由项目里 `opt_requirement.md` / `config/optimizer.yaml` 决定。不要给产品 CLI 加
`--parallel-jobs`、`--batch-size` 或 `--strategy`；这些不是产品续跑入口。
混用不同并行设置会让验收器拒绝
这份优化历史。

低层 `hermes-workflow` 命令只用于开发和诊断某个内部阶段，不是产品入口。普通用户和
agent 操作都应使用 `ic-opt`，不要把低层调试参数当作 requirement 的替代入口。

## 11. 和 Agent 配合使用

最终推荐的用户交互是短指令：

```text
/ic-opt ~/spectre_opt_prj/Mixer_opt --real
```

所有关键需求都应该在 `opt_requirement.md` 和 `constraints.md` 里。用户不应该在
聊天窗口里长篇解释每个指标、公式和变量。

Agent 的职责：

- 读取项目文件
- 先运行 `ic-opt PROJECT --doctor`，检查 `opt_requirement.md`、point root、环境文件
  和远程 SSH 是否准备好
- doctor 不通过时停止，并告诉用户需要修改的具体文件、字段或路径
- 调用 `ic-opt`
- 等真实流程完成
- 读取报告
- 给用户解释 best observed、可行点数量、失败分类、是否建议继续

Agent 不应该：

- 改 OCEAN 公式
- 直接解析 PSF
- 自己手选点代替 optimizer
- 在用户没要求时改变并行资源
- 把失败点当作主推荐点

如果 agent 遇到报错，应先参考：

```text
docs/TROUBLESHOOTING_CN.md
```

如果看到优化器或 doctor 的 `*.json` 报告，优先读取 `structured_issues` 字段；
再兼容地回退到旧的 `issues` 数组。`structured_issues` 里建议按
`code`、`stage`、`likely_cause`、`recommended_action`、`evidence` 读。

里面按报错信息列出了常见原因和修复方式，包括 `opt_requirement.md` 格式错误、
Maestro point root 层级错误、OCEAN 非标量、SSH host key、免密登录、远程高并发
导致的 `kex_exchange_identification`，以及旧版本 manifest missing。

## 12. 常见报错先看哪里

完整排错表在：

```text
docs/TROUBLESHOOTING_CN.md
```

几个最高频问题：

- `opt_requirement.md` 格式或字段错误：先跑 `--doctor`，按报告修文件，不要在聊天里
  临时补公式。
- `maestro_point_root` 错误：必须填到 leaf run 目录，里面能看到
  `netlist/input.scs` 和 `psf/`。
- OCEAN metric 非标量：公式返回了 waveform/list/空值/NaN，需要改成能返回单个数的
  OCEAN 表达式。
- 远程 `Host key verification failed`：先手动 `ssh PROFILE true` 并接受正确 host key。
- 远程 `Permission denied` 或 BatchMode 失败：免密 SSH 没配好。
- 远程高并发出现 `kex_exchange_identification`：降低 `parallel_jobs`，正常先用 4-8。
- `result_manifest.json missing`：当前版本已针对 SSH/tool 异常路径补失败 manifest；
  如果仍出现，请保留 run 目录并更新到最新版本后复查。

## 13. 当前 v0.1.6 边界

- 已经支持 shell 自动化的完整真实流程。
- 已经支持本地和远程 doctor 检查；本地 doctor 不会启动 Spectre/OCEAN，也不会误走
  optimizer 路径。
- requirement 和 optimizer 报告中已经优先提供结构化诊断字段
  `structured_issues`，agent 应优先读取其中的 `code`、`likely_cause`、
  `recommended_action` 和 `evidence`。
- 已经支持远程 SSH 执行：本机运行优化器，远程 Linux EDA 服务器运行 Spectre/OCEAN。
- 已经提供平台无关 `skills/ic-opt/SKILL.md`，任何能运行 shell 命令并读取文件的
  agent 都可以按这份 skill 操作 `ic-opt`。
- 结果是 best observed，不是全局最优证明。
- 项目使用 MIT License 发布；Cadence、PDK 和仿真 license 不包含在本项目内。
