# IC Auto Opt Workflow v0.1.10 使用说明

IC Auto Opt 用 `opt_requirement.md` 描述一次真实 Spectre/OCEAN 工作流。当前
release 支持两种模式：

- `optimize`：运行优化器，搜索满足约束的候选参数。
- `fix_run`：运行用户指定的固定参数点，导出指定 waveform CSV，不创建优化器状态。

两种模式都通过 `opt_requirement.md` 的 `Workflow.mode` 选择。没有单独的 fix-run
命令行开关。

## 从 GitHub 安装

默认使用 HTTPS clone：

```bash
git clone https://github.com/HAIDERZz/IC-opt-workflow.git
cd IC-opt-workflow
```

IC Auto Opt 要求创建虚拟环境所用的 Python 解释器版本为 3.11 及以上
（`pyproject.toml` 声明了 `requires-python = ">=3.11"`，源码也使用了仅 3.11
才支持的语法）。EDA 服务器上默认的 `python3` 经常版本更旧；如果是这种情况，
请改用当地环境提供的 `python3.11`（或更新版本）命令。

创建 Python 环境：

```bash
python3 -m venv .venv   # 如果当地默认 python3 版本较旧，这里改用 python3.11（或更新版本）
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -r requirements-product.txt
```

检查命令是否可用：

```bash
./.venv/bin/ic-opt --help
./.venv/bin/hermes-workflow --help
```

高级报告依赖单独安装：

```bash
./.venv/bin/python -m pip install -r requirements-advanced.txt
```

这组依赖只在需要 OpenBox advanced surrogate visualization、
hyperparameter importance、SHAP/lightgbm 相关分析时安装。它包含一些较大的包，
在 Linux 上也可能需要 Python development headers。

`requirements-product.txt` 以 editable 方式安装（`-e .`、`-e vendor/open-box`、
`-e vendor/TuRBO`），并会拉取 `torch`/`gpytorch`。首次安装体量较大；clone 得到的
仓库目录之后不能删除或移动，否则 editable 安装会失效。

不要把 `.venv` 建在用户的优化项目目录里。工具仓库和每个电路优化项目应该分开。

## 选择本地模式还是远程模式

如果同一台 Linux EDA 机器既能安装 Python 环境，又能访问 Cadence/Spectre/OCEAN、
PDK 和 license，就用本地模式。此时控制端和仿真端是同一台机器。

如果你不方便在 EDA 服务器上安装 Python 环境，且你想用个人的 macOS、Windows WSL
或普通 Linux 工作站作为控制端运行脚本，就用远程模式。此时 Python workflow 在控制端
运行，Spectre/OCEAN 通过 SSH 在远端 Linux EDA 服务器上运行。

## SSH Profile 是什么

远程模式里的 `--ssh-profile PROFILE` 指的是 OpenSSH profile，通常写在控制端的
`~/.ssh/config`。

示例：

```sshconfig
Host eda-lab
  HostName eda-server.example.com
  User username
  IdentityFile ~/.ssh/id_ed25519
```

先确认 SSH 本身可用：

```bash
ssh eda-lab 'hostname'
```

远程模式传给 `ic-opt` 的 `PROJECT_DIR` 是远端 Linux EDA 服务器上的绝对路径。这个
目录需要包含 `opt_requirement.md`，并且 requirement 里引用的 Maestro/ADE result
point 也必须是远端服务器上存在的路径。

远程运行时，IC Auto Opt 会读取远端 requirement，把 exported netlist 下载到控制端
`~/.ic-opt/remote_runs` 下的 cache；每个真实仿真 child 会上传到远端执行，再把
Spectre/OCEAN 结果下载回来，并尽量把报告同步回远端项目目录。

远程命令形态：

```bash
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --doctor
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --real
```

## Cadence 环境

**本地模式**：提供一个能在 `csh` 或 `tcsh` 中使用的 Cadence setup 文件。本地
`ic-opt` 按下面顺序查找：

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

这个脚本需要能找到 `spectre`、`ocean` 和 license 工具。不要把 `.bashrc` 或
`.zshrc` 当作 Cadence `csh` 环境脚本。

**远程模式**：上面的四级查找链不生效。`IC_OPT_CADENCE_CSHRC` 和
`~/.ic-opt/cadence_env.csh` 都不参与远程解析，远程模式只认下面两项之一：

```text
--cadence-cshrc PATH
<远端 PROJECT_DIR>/cadence_env.csh
```

即：显式传了 `--cadence-cshrc` 就用它（按远端 Linux EDA 服务器上的路径理解），
否则回退到远端项目根目录下的 `cadence_env.csh`。如果只在控制端设置了
`IC_OPT_CADENCE_CSHRC` 或 `~/.ic-opt/cadence_env.csh`，远程 doctor 仍会报
`CADENCE_CSHRC_MISSING`。

## 常用命令

本地 doctor：

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
```

本地真实运行：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
```

本地 optimize-only dry orchestration gate：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration
```

这个命令会跑完真实优化器启动前的离线编排检查，并在真实 backend 开始执行
Spectre/OCEAN candidate 之前停住。当前 release 中只把它作为本地 optimize 初次运行的
高级 gate 使用；它不是 continuation，不是 fix-run，也不是远程模式入口。

继续已有优化：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

远程：

```bash
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --doctor
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --real
./.venv/bin/ic-opt --ssh-profile eda-lab /remote/absolute/project --real --continue N
```

`--continue N` 只用于已经存在的优化项目追加预算。Continuation 会重新校验当前
requirement，但不会把 requirement 的改动重新物化为本轮执行配置；续跑仍使用
已有配置、快照和优化历史——初次运行的预算、batch size、并行数、Spectre 线程数、
优化器 CPU 限制、算法、策略、初始化、工艺角、输出格式、metric 公式、固定点和
waveform export 都来自 `opt_requirement.md`，一旦首次运行时物化成配置，续跑
期间不会因为用户改写 `opt_requirement.md` 而变化。

续跑沿用已经生成的项目 backend。OpenBox 历史只能由 OpenBox 续跑，native TuRBO
历史只能由 native TuRBO 续跑。Native TuRBO 会从累计 trace 重建活动 trust region，
不会重新执行初始设计；旧 artifact 没有保存底层 RNG 状态，因此不承诺与一个从未
中断的进程逐 bit 相同。每次 Remote continuation 都会先在当前远端主机上重新执行
Doctor；只有环境、工具、Requirement 和 dirty-state 检查通过，才会恢复 frozen
snapshot、同步历史并启动后端。

### Flag 互斥规则

| 组合 | 是否允许 |
| --- | --- |
| `--doctor` 同时带 `--real` / `--continue` / `--dry-orchestration` | 不允许，`--doctor` 只能单独使用 |
| `--continue N` 不带 `--real` | 不允许，`--continue` 必须和 `--real` 一起用 |
| 远程模式下的 `--doctor` / `--real` / `--real --continue N` | 三选一，必须选其中一种 |

### 状态查询与预检

真实运行前，先离线校验 requirement（不跑仿真、不需要 Cadence 环境）：

```bash
./.venv/bin/hermes-workflow check-requirement PROJECT_DIR
```

长跑期间或结束后，查看优化进度、best observed 结果、evaluation/status 计数
和是否建议续跑：

```bash
./.venv/bin/hermes-workflow optimizer-status PROJECT_DIR
```

## 项目目录

推荐结构：

```text
PROJECT_DIR/
├── opt_requirement.md
├── constraints.md
└── context/
```

只需要手写 `opt_requirement.md`。`constraints.md` 用来放人工偏好和说明，不会生成
真实执行合同。`config/`、`netlists/`、`runs/`、`reports/`、`ledger/`、`state/`、
`execution_package/`（含 `execution_manifest.json`）和项目根目录下的
`supervisor_instruction.json` 都由工具生成，不要手写或误删。

每个 testbench 先在 Maestro/ADE 中跑一个已知可用点，然后把 point root 写入
`opt_requirement.md`。point root 必须包含：

```text
<maestro_point_root>/netlist/input.scs
```

这里的 `maestro_point_root` 填 Maestro/ADE 结果点目录本身，不是
`netlist/input.scs` 文件，也不是 `psf/` 目录。常见目录形态是：

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

例如：

```text
/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_IIP3/maestro/results/maestro/Interactive.28/1/Mixer_CS_IIP3
```

`Interactive.N` 用你自己的 Maestro run 实际生成的编号，最后一级目录用对应的
testbench 名称。

## Requirement 模板

```text
examples/spectre_maestro_project/opt_requirement.md
examples/spectre_maestro_project/opt_requirement.openbox_gp_eic.md
examples/spectre_maestro_project/opt_requirement.turbo.md
examples/spectre_maestro_project/opt_requirement.multi_corner.md
examples/spectre_maestro_project/opt_requirement.multi_testbench.md
examples/spectre_maestro_project/opt_requirement.multi_tb_corner.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.md
examples/spectre_maestro_project/opt_requirement.history_warm_start.multi_corner.md
examples/spectre_maestro_project/opt_requirement.fix_run.md
examples/spectre_maestro_project/opt_requirement.fix_run.metrics_only.md
examples/spectre_maestro_project/opt_requirement.fix_run.multi_testbench.metrics_waveform.md
```

显式 GP-EIC/TuRBO 模板用于锁定 optimizer；multi-testbench 模板展示完整 measurement
route；history 模板覆盖 source-point 和 multi-corner OpenBox warm start；三份 fix-run
模板分别覆盖 waveform-only、metrics-only 和 multi-testbench Metrics+Waveform。

使用时，把模板复制为项目根目录的 `opt_requirement.md`，替换 Maestro point root、
旧项目路径、固定参数点、corner 变量、waveform export 和电路相关公式。

## Optimize 模式

优化 requirement 可以省略 `Workflow` section；省略时默认 `mode: optimize`。

优化 requirement 写：

- `Project`：`project_name`、`backend`
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
- `Approval Checklist`：`metric_formulas_user_approved`、
  `maestro_source_user_approved`、`variable_bounds_user_approved`、
  `spectre_resource_settings_user_approved` 四个字段必须全部为 `true`，
  否则 requirement 校验会拒绝并报 `approval checklist <field> must be true`

生产使用时，把下面几种策略看成并列选择：

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: turbo`, `strategy: turbo_trust_region`
- `algorithm: openbox`，省略 `strategy` 时默认解析为 `openbox_auto`

`random_baseline` 用于诊断，不作为生产优化策略。

## History Warm Start

`History Warm Start` 用于新建一个 optimize 项目，同时参考同一电路之前跑过的优化
历史。典型流程是：用户看完上一轮报告后，新建项目目录，复制并修改新的
`opt_requirement.md`，然后在新 requirement 里加入 `History Warm Start` section：

```yaml
enabled: true
sources:
  - path: /path/to/previous_same_circuit_project
    label: round1
max_observations: 200
warm_start_strategy: topk
```

这个 section 会渲染为 `config/history_warm_start.yaml`。它和 `--continue N` 不是
同一个用途。History warm-start 只支持 optimize，不支持 fix-run，也不能和
`--continue` 一起使用。

启用的 History Warm Start 只支持 OpenBox。若项目选择 native TuRBO，requirement
intake 和项目校验会明确拒绝该组合，而不是运行时静默忽略。Native TuRBO 的同项目
追加预算使用 `--continue N`。

第一版规则是严格的：新旧项目变量名必须完全一致，不做变量名映射，也不接受旧项目
多出来的变量。变量范围可以变化；旧点如果超出当前变量空间，会在 audit 里统计为
`out_of_current_space`。系统不复用旧的 objective 或 constraint 结果，只读取旧 run 的
raw metrics，并按当前项目的 objective 和 constraints 重新计算。当前项目需要的 metric
定义必须和旧项目一致，否则旧历史不会进入 warm-start。

有约束的 IC 优化场景使用 OpenBox 的 `initial_configurations_from_history` 路径，把
可用历史转换为初始候选配置；无约束单目标场景才可能使用 OpenBox 原生
`transfer_learning_history`。运行后检查
`reports/history_warm_start_audit.json`、`reports/history_warm_start_audit.md`，以及
`reports/optimizer_run_report.json` 里的 `openbox.history_warm_start`。

History warm-start 的实际应用只支持 OpenBox backend。native TuRBO 不会把旧项目历史
传入候选建议流程；如果需要让历史影响下一轮搜索，应使用 OpenBox。TuRBO 项目中相关
报告内容可能不存在，或显示为 `not_available`。

## Fix-Run 模式

fix-run requirement 必须写：

```yaml
schema_version: "1.0"
mode: fix_run
starting_run_id: real_001
```

必须包含以下 section，缺一个都会被 requirement 校验拒绝：

- `Workflow`（`mode: fix_run`）
- `Project`
- `Maestro Source`
- `Design Variables`
- `Spectre Settings`
- `Fixed Points`：用户指定的一个或多个候选点
- `Approval Checklist`

以下 section 是可选的：

- `Process Corners`
- `Metrics`
- `Waveform Exports`：需要导出的 waveform CSV，例如
  `getData("NF" ?result "pnoise")`

metrics-only 模板（`opt_requirement.fix_run.metrics_only.md`）可以不写
`Waveform Exports`；waveform-only 场景同样可以不写 `Process Corners`。两者都是
合法的 fix-run 项目。

fix-run 不运行优化器，不生成 `state/optimizer_state.json`，也不生成
`reports/optimizer_decision_report.md`。

fix-run 模式下，`Spectre Settings.parallel_jobs` 控制同一个 fixed point 内最多
同时运行多少个 testbench/corner child Spectre/OCEAN 仿真；`threads_per_run` 仍然是
每个 Spectre 进程的 `+mt` 线程数。当前 release 中多个 fixed point 仍按顺序执行。

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

优化报告（backend-neutral，两种 backend 都会写）：

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_flow_run_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/optimizer_insight_report.html
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

`reports/optimizer_flow_run_report.json` 是顶层流程标记，CLI 成功或失败都会
打印它的路径；先看它的 `status` 字段判断整条流程是 pass 还是 fail。

运行报告和 evaluations jsonl 按 backend 分组，两组文件名不同、不会同时都写：

- OpenBox：`reports/optimizer_run_report.json` +
  `reports/optimizer_evaluations.jsonl`
- native TuRBO：`reports/native_turbo_optimizer_report.json` +
  `reports/native_turbo_optimizer_evaluations.jsonl`

用 native TuRBO 跑的项目按 OpenBox 的文件名去验收会看到"文件不存在"——这不代表
运行失败，先确认项目实际使用的 backend 再查对应文件。

History warm start（只用于 OpenBox）：

```text
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
```

`reports/optimizer_insight_report.html` 是优化结束后优先阅读的报告。HTML 适合快速
阅读和定位问题；JSON/JSONL 是更底层的事实来源。判断 trade-off、history 是否有效、
或者下一轮变量范围时，应同时查看本轮实际存在的 JSON/JSONL 和 child manifest。

Pareto/trade-off 分析只使用本轮已有 raw metrics 做报告层总结；它不会把 OpenBox
切换成 multi-objective optimizer mode，也不会改变 candidate 选择或改写 objective。

Space Compression Advisory 使用 OpenBox compressor dry-run，在当前变量合同和已观测
run 上生成搜索空间收窄建议。建议只用于人工复盘，不会自动应用到 optimizer 执行。
用户确认后，可以把建议范围手动写入新的 `opt_requirement.md` 再启动下一轮优化。

如果 backend 是 native TuRBO，报告仍可保留 backend-neutral 内容，例如 best point、
实际测量 metric、evaluation/status counts、plots、raw-metric trade-off summary，
以及仅用于建议的 space-compression dry-run。OpenBox 专属内容不应期待存在，包括
history warm-start application、advanced surrogate visualization、parameter importance；
这些 section 可能缺失或显示 `not_available`。

如果 objective 直接对 dB、dBm 这类带符号或对数域 metric 做乘除，尤其数值可能跨过
0 时，排序会很难解释。workflow 会保留用户写的 objective；需要调整时，建议在下一轮
requirement 中改成线性域或归一化后的表达。

fix-run 报告：

```text
reports/fix_run_report.json
```

`reports/fix_run_report.json` 的 `points[]` 数组里每个固定点都带 `run_id` 和
三组权威路径字段：`scalar_metric_manifest_paths`、`waveform_export_manifest_paths`、
`csv_artifact_paths`；实际目录形态因项目而异，不要假设固定布局，要读这些路径
字段而不是自己拼路径：

```text
# testbench × corner
runs/real/real_001/testbenches/<tb>/corners/<corner>/result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/metric_result_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveform_export_manifest.json
runs/real/real_001/testbenches/<tb>/corners/<corner>/metrics/waveforms/<name>.csv

# 只有 testbench，无 corner
runs/real/real_001/testbenches/<tb>/result_manifest.json

# 只有 corner，无 testbench
runs/real/real_001/corners/<corner>/result_manifest.json

# 既无 testbench 也无 corner
runs/real/real_001/result_manifest.json
```

`<run_id>` 从 `real_001` 起随固定点递增（`real_002`、`real_003`...），不要只查
`real_001` 就下结论。

### run 保留策略裁剪后如何取证

如果 artifact 保留策略里 `keep_successful_runs`/`keep_failed_runs` 为 `false`，
工具会在归档完成后删除 `runs/real/<run_id>` 目录本身。这不代表运行失败——报告
里记录的 pass/fail 判断仍然有效。裁剪前的证据会分别保存到：

```text
state/run_retention_evidence/<run_id>/
state/run_retention/<run_id>.json
```

如果按上面的清单去查 `runs/**/result_manifest.json` 却发现目录已经不存在，去
这两个路径找裁剪前留存的证据，不要把"目录缺失"当成"运行失败"。

验收时不要只看退出码。必须检查报告和 child artifacts。

## Agent 使用

让 agent 操作时，把下面两个东西给它：

```text
skills/ic-opt/SKILL.md
PROJECT_DIR
```

agent 应调用同一个产品 CLI，并检查上述过程文件后再汇报。
