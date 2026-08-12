# 排障指南

先运行 doctor：

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
```

Remote 模式默认 Controller 与 Remote Host 的文件系统完全隔离。远端路径只能通过
配置的 SSH transport 检查，或先明确下载到 Controller cache 后再由本地代码读取；
Controller 上偶然存在同名路径不能作为远端文件存在的依据。

## 找不到 `opt_requirement.md`

检查传入的 `PROJECT_DIR`。`opt_requirement.md` 必须在项目根目录。

## requirement 校验失败

真实运行前，建议先离线校验 requirement（不跑仿真、不需要 Cadence 环境）：

```bash
./.venv/bin/hermes-workflow check-requirement PROJECT_DIR
```

常见的 requirement 校验诊断码：

- `REQUIREMENT_SECTION_MISSING` — 必填 section 缺失或重复出现，报错形如
  `Required section is missing: <name>` 或 `Section <name> appears more than
  once.`
- `REQUIREMENT_YAML_INVALID` — section 下的 YAML block 语法错误或不是单一
  fenced YAML block（"Requirement section YAML is invalid."）
- `OBJECTIVE_UNKNOWN_METRIC` — objective 表达式引用了 `Metrics` 里没有声明的
  metric 名（"Objective expression references unknown metric `<name>`."）
- `OBJECTIVE_UNSAFE_EXPRESSION` — objective 表达式数学上无效，例如除零或返回
  非有限值（"Objective expression is unsafe or invalid."）
- `OBJECTIVE_UNSUPPORTED_FUNCTION` — objective 表达式用了不支持的函数或语法
  节点（"Objective expression uses an unsupported function or AST node."）
- `CONSTRAINT_UNKNOWN_METRIC` — constraint 引用了未声明的 metric（"Constraint
  references unknown metric `<name>`."）
- `VARIABLE_RANGE_INVALID` — design variable 的 lower/upper/step 无效或变量名
  重复（"Design variable range is invalid."）
- `OPTIMIZER_STRATEGY_INVALID` — `Optimizer Settings` 里的 `algorithm`/
  `strategy` 组合无法解析（"Optimizer strategy resolution failed."）
- `approval checklist <field> must be true` — `Approval Checklist` 四个字段
  （`metric_formulas_user_approved`、`maestro_source_user_approved`、
  `variable_bounds_user_approved`、`spectre_resource_settings_user_approved`）
  没有全部写成 `true`

按诊断码对应的 section 修正 `opt_requirement.md`，重新跑 `check-requirement`
直到看到 `requirement intake passed`，再进入 `--doctor`/`--real`。

## `maestro_point_root/netlist/input.scs is missing`

`maestro_point_root` 必须指向 Maestro/ADE 的 result point 目录，不是
`input.scs` 文件，也不是 `psf/` 目录。

期望结构：

```text
<maestro_point_root>/netlist/input.scs
```

常见的 Maestro 结果点目录形态是：

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

例如：

```text
/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_IIP3/maestro/results/maestro/Interactive.28/1/Mixer_CS_IIP3
```

如果 `opt_requirement.md` 里填到了 `.../netlist/input.scs`，就把最后的
`/netlist/input.scs` 去掉；如果填到了 `psf/`，回到同一个 run 下的 testbench
结果点目录。

Remote 模式下，这项存在性检查会通过 SSH 在 Remote Host 上执行 `test -f`，不会
查询 Controller 的本地文件系统。SSH exit status 0 表示文件存在，1 表示文件不
存在；任何其他返回值都必须按 SSH transport/probe 错误处理，不能降级成“文件缺失”，
也不能回退到 Controller 上检查同名路径。

## Remote flow 的完成标记

优化流程只有在 Remote Host 上核验全部 parent/child manifest 的 SHA-256 内容和
project-relative 引用后，才会发布 status 为 `pass` 的最终成功标记：

```text
reports/optimizer_flow_run_report.json
```

失败报告独立发布，不受成功完整性门槛阻挡。传输中断或 partial run 可以保留明确的
失败证据，但不得留下或沿用一个看似成功的 flow marker。

## 找不到 Cadence 环境

**本地模式**按下面顺序提供 Cadence setup：

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

这个脚本需要能在 `csh`/`tcsh` 中找到 `spectre`、`ocean` 和 license 工具。

**远程模式**下，上面的四级查找链不生效：`IC_OPT_CADENCE_CSHRC` 和
`~/.ic-opt/cadence_env.csh` 都不参与远程解析。远程模式只认 `--cadence-cshrc`
或远端项目根目录下的 `cadence_env.csh` 二选一。如果只在 Controller 上设置了
`IC_OPT_CADENCE_CSHRC`，远程 doctor 仍会报 `CADENCE_CSHRC_MISSING`（"Required
cadence cshrc is missing at `<path>`."）；`csh` source 之后找不到 `spectre`/
`ocean` 会报 `CADENCE_TOOL_MISSING`。

## 远程模式 doctor 失败

远程 doctor 覆盖 Controller 侧和 Remote Host 侧的多项前置检查，常见诊断码：

- `SSH_LOGIN_FAILED` — `ssh <profile> true` 探测失败（"Unable to authenticate
  or execute remote commands with ssh profile `<profile>`."）。检查 SSH
  profile 配置和网络连通性。
- `CONTROLLER_TRANSFER_TOOL_MISSING` — Controller 本机缺 `ssh`/`scp`/`tar`
  中的一个（"Controller dependency is missing: `<tool>`"）。在 Controller 上
  安装缺失的工具。
- `REMOTE_PROJECT_MISSING` — 远端项目目录不存在（"Remote project directory
  `<path>` is missing."）。先在远端创建该目录。
- `REMOTE_PROJECT_NOT_WRITABLE` — 远端项目目录不可写（"Remote project
  directory `<path>` is not writable."）。修正远端目录权限。
- `REMOTE_ATOMIC_PUBLISH_UNSUPPORTED` — 远端文件系统/coreutils 不支持
  `mkdir` + `cp -a` + `mv -T` 的原子发布探测。需要在远端提供带 `cp -a` 和
  `mv -T` 的 GNU coreutils。
- `REMOTE_DIRTY_STATE_PROBE_FAILED` — 无法通过 SSH 检查远端项目当前状态
  （"Unable to inspect Remote project state."），likely cause 是 SSH
  transport 或某个远端命令失败；恢复远端命令执行后重跑 `--doctor`。

这些检查都发生在 doctor 阶段，修好后重新跑 `--doctor` 直到 status 为 pass，
再跑 `--real`。

## 控制端 optimizer runtime 缺失

远程模式下，Spectre/OCEAN 在远端跑，但运行 `ic-opt` 的 Python workflow（包括
optimizer backend 本身）仍然在 Controller 上执行。诊断码
`CONTROLLER_OPTIMIZER_RUNTIME_UNAVAILABLE`（"Controller optimizer runtime is
unavailable."）说明这个 Controller 端 Python 进程无法 import 所选 backend 的
依赖：native TuRBO 需要 `torch`/`gpytorch`，OpenBox 需要 `openbox`。这意味着
**远程模式下 Controller 本机仍必须装齐所选 backend 的依赖**，这是远程用户
最常见的首次失败之一。

处置：在 Controller 上重新执行「从 GitHub 安装」里的
`requirements-product.txt` 安装步骤，确认对应 backend 的依赖能正常 import，
再重跑 `--doctor`。

## 远程并发锁

远程项目在 `state/remote_attempt.lock` 下维护一把并发锁，防止同一个远端项目
被多个 Controller 同时跑。运行被强制中断（例如进程被 kill）后，锁可能残留，
之后所有远程 `--real`/`--continue` 都会被拒绝，报错形如：

```text
remote project already has an active optimization attempt: <lock_dir>.
Inspect <owner_path> before manually removing a stale lock. Owner: <owner>
```

处置：先读 owner 元数据文件，确认没有其他 Controller 真的还在跑这个项目；
确认是残留的 stale lock 之后，才手工删除 `state/remote_attempt.lock`，不要
在没确认 owner 的情况下直接删锁。

## License Probe 失败

当 `require_license_check: true` 时，doctor 会运行真实 Spectre/license probe。
查看：

```text
reports/license_probe_report.json
```

常见原因：

- Cadence setup 文件不适合 `csh`/`tcsh`
- `spectre` 不在 PATH
- `lmstat` 不可用
- license server 不可达

## Spectre 子仿真失败

Spectre 本身失败（netlist 错误、不收敛等）和 OCEAN metric 提取失败是两类不同
的问题，要分开排查；netlist/收敛类失败是最常见的真实失败。先查这个
candidate/child 的 `result_manifest.json`：

```text
runs/**/result_manifest.json
```

看 `status` 字段是 `succeeded` 还是 `failed`。如果是 `failed`，`log_file`
指向 Spectre 的 stderr；Spectre 自己的运行日志固定落在：

```text
runs/**/psf/spectre.out
```

先看 `spectre.out` 里的收敛信息或语法错误，而不是直接怀疑 OCEAN 层。

## OCEAN metric 或 waveform export 失败

查看 child artifact：

```text
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
runs/**/metrics/ocean.log
```

`ocean_expression` 会被复制进 OCEAN replay script。不要把 ADE/Maestro 已验证公式
改写成另一种方言。optimizer metric path 需要标量结果；完整 waveform CSV 导出应走
fix-run 的 `Waveform Exports`。

正确的 pnoise waveform expression 形式是：

```text
getData("NF" ?result "pnoise")
```

## 并行数和线程数

优化模式下，`parallel_jobs` 是候选点级别的 Spectre process 并发。fix-run 模式下，
`parallel_jobs` 是同一个 fixed point 内 testbench/corner child 的 Spectre/OCEAN
并发。`threads_per_run` 是单个 Spectre 仿真的 `+mt` 线程数。
`optimizer_cpu_threads` 只限制 Python 优化器侧的 CPU 线程。

这些值都来自 `opt_requirement.md`。

## 多工艺角结果看起来不一致

查看 parent aggregate manifest 和 `reports/optimizer_decision_report.md`。多工艺角
候选点会先聚合所有 child 结果，再把一条 observation 交给优化器。

## 上一轮被中断

- `INCOMPLETE_REAL_RUN` — doctor 报 "Incomplete real run directory detected:
  `<name>`."，detail 说明该 candidate 目录既没有 candidate 级别的 result
  manifest（`result_manifest.json` 或 `metrics/metric_result_manifest.json`），
  也没有旧版 optimizer 级别报告；likely cause 是上一轮在这个 candidate 完成
  前就被中断了。
- `OPTIMIZER_PROGRESS_STATE_MISMATCH` — doctor 报 "Optimizer progress
  artifacts disagree."，likely cause 是 `state/optimizer_state.json` 是从
  过时来源（例如 ledger 行数）写出的，而不是从 optimizer trace artifacts
  写出的；recommended action 是重新生成 optimizer report writer，从
  `reports/optimizer_run_report.json`（或对应 backend 的运行报告）和
  `reports/optimizer_evaluations.jsonl` 重建 `state/optimizer_state.json`。

`INCOMPLETE_REAL_RUN` 通常不需要手工修复，`--continue` 会重新处理该
candidate；`OPTIMIZER_PROGRESS_STATE_MISMATCH` 需要按上面的 recommended
action 修复后才能继续。

## 想知道跑到哪了

长跑期间或运行之后，查看优化进度、best observed 结果、evaluation/status
计数和是否建议续跑：

```bash
./.venv/bin/hermes-workflow optimizer-status PROJECT_DIR
```

## 不要只看退出码

真实 workflow 验收至少看：

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.html
reports/fix_run_report.json
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

optimizer 运行报告按 backend 分列，**两者不会同时存在**，不要把另一个
backend 的文件名当成通用验收项：

- OpenBox 项目：`reports/optimizer_run_report.json`
- native TuRBO 项目：`reports/native_turbo_optimizer_report.json`

按 OpenBox 的文件名去验收一次成功的 native TuRBO 运行会看到"文件不存在"——
这不代表运行失败。先确认项目实际使用的 backend（`opt_requirement.md` 里
`Optimizer Settings.algorithm`），再查对应文件名对应的运行报告和
evaluations jsonl（`reports/optimizer_evaluations.jsonl` 对应 OpenBox，
`reports/native_turbo_optimizer_evaluations.jsonl` 对应 native TuRBO）。

如果 artifact 保留策略把 `runs/real/<run_id>` 裁剪掉了，去
`state/run_retention_evidence/<run_id>/` 和
`state/run_retention/<run_id>.json` 找裁剪前留存的证据，不要把"目录缺失"
当成"运行失败"。

fix-run 成功时，`reports/fix_run_report.json` 应显示 `workflow_mode: fix_run`。
如果请求 waveform CSV，每个成功 child 都应有 waveform export manifest 和 CSV 文件。
fix-run 不应生成 optimizer state 或 optimizer decision report。

## 诊断码索引

所有 doctor/intake 诊断都带一个稳定的 `code` 字段。下表按字母序列出当前实现的
全部诊断码，作为按症状查找之外的第二条排查路径；多数码在上面对应小节里有更完整
的报错原文和处置步骤。

| 码 | 含义 | 处理动作/对应小节 |
| --- | --- | --- |
| `CADENCE_CSHRC_MISSING` | Cadence cshrc 文件不存在 | 见「找不到 Cadence 环境」 |
| `CADENCE_TOOL_MISSING` | source cshrc 后找不到 `spectre`/`ocean` | 见「找不到 Cadence 环境」 |
| `CONSTRAINT_UNKNOWN_METRIC` | constraint 引用了未声明的 metric | 见「requirement 校验失败」 |
| `CONTROLLER_OPTIMIZER_RUNTIME_UNAVAILABLE` | Controller 端 Python 无法 import 所选 backend 依赖 | 见「控制端 optimizer runtime 缺失」 |
| `CONTROLLER_TRANSFER_TOOL_MISSING` | Controller 本机缺 `ssh`/`scp`/`tar` | 见「远程模式 doctor 失败」 |
| `INCOMPLETE_REAL_RUN` | 上一轮某个 candidate 目录未完成 | 见「上一轮被中断」 |
| `LICENSE_PROBE_FAILED` | 真实 license probe 失败 | 见「License Probe 失败」 |
| `MAESTRO_INPUT_SCS_MISSING` | `maestro_point_root` 指错了目录层级 | 见「`maestro_point_root/netlist/input.scs is missing`」 |
| `OBJECTIVE_UNKNOWN_METRIC` | objective 引用了未声明的 metric | 见「requirement 校验失败」 |
| `OBJECTIVE_UNSAFE_EXPRESSION` | objective 表达式数学上无效（除零、非有限值等） | 见「requirement 校验失败」 |
| `OBJECTIVE_UNSUPPORTED_FUNCTION` | objective 表达式用了不支持的函数/语法节点 | 见「requirement 校验失败」 |
| `OPTIMIZER_PROGRESS_ARTIFACT_INVALID` | optimizer 进度 artifact 不完整或无效 | 重新生成 optimizer report writer 后重跑 `--doctor` |
| `OPTIMIZER_PROGRESS_STATE_MISMATCH` | `state/optimizer_state.json` 与 trace artifacts 不一致 | 见「上一轮被中断」 |
| `OPTIMIZER_STRATEGY_INVALID` | `algorithm`/`strategy` 组合无法解析 | 见「requirement 校验失败」 |
| `REMOTE_ATOMIC_PUBLISH_UNSUPPORTED` | 远端 coreutils 不支持原子发布探测 | 见「远程模式 doctor 失败」 |
| `REMOTE_DIRTY_STATE_PROBE_FAILED` | 无法通过 SSH 探测远端项目状态 | 见「远程模式 doctor 失败」 |
| `REMOTE_DOCTOR_REPORT_WRITE_FAILED` | 无法把 remote doctor report 发布回远端 | 检查 SSH transport 是否中途失败，重跑 `--doctor` |
| `REMOTE_PARALLELISM_HIGH`（WARN） | 远端 `parallel_jobs` 偏高 | 非阻断性；确认远端资源是否够用 |
| `REMOTE_PROGRESS_SNAPSHOT_FAILED` | 无法通过 SSH 读取远端 optimizer 进度 | 检查 SSH 连通性后重试 |
| `REMOTE_PROJECT_MISSING` | 远端项目目录不存在 | 见「远程模式 doctor 失败」 |
| `REMOTE_PROJECT_NOT_WRITABLE` | 远端项目目录不可写 | 见「远程模式 doctor 失败」 |
| `REMOTE_RUNTIME_DEPENDENCY_MISSING` | 远端缺 GNU/POSIX 运行时依赖 | 在远端安装缺失的运行时依赖后重跑 `--doctor` |
| `REQUIREMENT_SECTION_MISSING` | 必填 section 缺失或重复出现 | 见「requirement 校验失败」 |
| `REQUIREMENT_YAML_INVALID` | section 下的 YAML block 语法错误 | 见「requirement 校验失败」 |
| `SSH_LOGIN_FAILED` | `ssh <profile> true` 探测失败 | 见「远程模式 doctor 失败」 |
| `VARIABLE_RANGE_INVALID` | design variable 的 lower/upper/step 无效或变量名重复 | 见「requirement 校验失败」 |
