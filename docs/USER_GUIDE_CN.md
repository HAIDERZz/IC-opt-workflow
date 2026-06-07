# IC Auto Opt Workflow v0.1.1 使用说明

这份说明面向集成电路方向用户，假设你会使用 Linux 和 Cadence，但不要求你熟悉
Python 工程。

## 1. 这个项目是做什么的

你把优化需求写进一个标准格式的 `opt_requirement.md`，并提供 Maestro/ADE 已经
能跑通的 point root。然后运行：

```bash
./.venv/bin/ic-opt /path/to/project --real
```

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

## 2. 安装一次产品环境

只需要给工具本身建一个 Python 环境，不要在每个优化项目里建 venv。

```bash
cd /path/to/IC-opt-workflow
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-product.txt
./.venv/bin/python -m pip install -e .
```

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

正式跑真实工具之前，建议先执行：

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt --doctor
```

它会检查 `opt_requirement.md`、Cadence 环境文件、OpenBox/Hermes Python
环境、config/netlist 准备情况和 continuation 所需历史文件。它不会启动
Spectre/OCEAN，也不会生成优化候选点。

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

## 6. 先做离线检查

这个命令不会启动 Spectre/OCEAN：

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt \
  --real \
  --dry-orchestration \
  --max-evals 100 \
  --batch-size 10
```

如果这里失败，通常是 `opt_requirement.md`、路径、格式或环境文件位置有问题。

## 7. 跑真实优化

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt \
  --real \
  --max-evals 100 \
  --batch-size 10
```

如果你的环境文件不叫 `cadence_env.csh`：

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt \
  --real \
  --cadence-cshrc /path/to/cadence_env.csh
```

真实运行必须能访问 Cadence license 和系统进程服务。不要在限制 sandbox 里运行
真实 Spectre/OCEAN。

## 8. 查看结果

优先看：

```text
reports/optimizer_decision_report.md
reports/optimizer_insight_report.md
reports/optimizer_final_summary.md
```

常见结论：

```text
accept_best_observed_or_continue
```

意思是当前有一个 best observed feasible 点，但不是全局最优证明。你可以接受，也
可以继续增加点数。

## 9. 继续追加优化

```bash
./.venv/bin/ic-opt ~/spectre_opt_prj/Mixer_opt \
  --continue 40
```

续跑时如果已有优化历史，默认继承历史里已经验收过的资源设置；如果没有历史，
才使用项目里的 `config/spectre.yaml`。不要习惯性加 `--parallel-jobs`，除非你
明确想改变资源；混用不同并行设置会让验收器拒绝这份优化历史。

## 10. 和 Agent 配合使用

最终推荐的用户交互是短指令：

```text
/ic-opt ~/spectre_opt_prj/Mixer_opt --real
```

所有关键需求都应该在 `opt_requirement.md` 和 `constraints.md` 里。用户不应该在
聊天窗口里长篇解释每个指标、公式和变量。

Agent 的职责：

- 读取项目文件
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

## 11. 当前 v0.1.1 边界

- 已经支持 shell 自动化的完整真实流程。
- Claude/OpenCode runtime adapter 是产品化方向的一部分，但不同 agent runtime 的
  原生 subagent 行为仍需要继续实测。
- 结果是 best observed，不是全局最优证明。
- 发布到 GitHub 前还需要选择开源许可证。
