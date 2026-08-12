# IC Auto Opt Agent 使用速查

agent 操作当前版本的 IC Auto Opt 时，不只是替用户运行命令。agent 的身份是电路优化
协助者：读取用户的 requirement 和电路背景资料，调用产品 CLI，检查报告与 raw 数据，
再把结果翻译成对电路调参有用的反馈。

`opt_requirement.md` 是初次运行的唯一配置入口。它通过 `Workflow.mode` 选择
优化或 fix-run。预算、并行数、Spectre 线程数、优化器 CPU 限制、算法、策略、
初始化、工艺角、输出格式、metric 公式、固定点和 waveform export 都在这个文件里。

## 文档怎么用

- `README.md`：安装、local/remote 模式、命令形态和产品能力总览。
- `docs/USER_GUIDE_CN.md`：面向人的完整中文使用说明。
- `docs/AGENT_USER_QUICKSTART_CN.md`：agent 快速操作清单。
- `docs/AGENT_OPTIMIZER_USAGE_MANUAL.md`：agent 的详细行为边界和 artifact checklist。
- `docs/OPTIMIZER_PRODUCTION_QUICKSTART.md`：生产运行流程。
- `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`：CLI、Cadence 环境和证据文件。
- `docs/OPTIMIZER_ALGORITHM_MODES.md`：OpenBox / TuRBO 策略选择。
- `docs/PROCESS_CORNER_OPTIMIZATION_FLOW_CN.md`：multi-corner 聚合逻辑。
- `docs/TROUBLESHOOTING_CN.md`：失败排查。
- `docs/ROLE_MODEL_AND_TERMINOLOGY.md`：产品角色定位和术语。
- `examples/spectre_maestro_project/OPT_REQUIREMENT_README.md`：requirement section 合同。
- `examples/spectre_maestro_project/*.md`：真实跑通过后脱敏的 requirement 模板。

## 模式选择

| 目标 | 模板 | 模式 |
| --- | --- | --- |
| 单 testbench、source-point corner 优化 | `opt_requirement.md` | `optimize` |
| 显式 OpenBox GP-EIC 优化 | `opt_requirement.openbox_gp_eic.md` | `optimize` |
| 显式 native TuRBO 优化 | `opt_requirement.turbo.md` | `optimize` |
| 单 testbench、多 process corner 优化 | `opt_requirement.multi_corner.md` | `optimize` |
| 多 testbench、source-point corner 优化 | `opt_requirement.multi_testbench.md` | `optimize` |
| 多 testbench、多 process corner 优化 | `opt_requirement.multi_tb_corner.md` | `optimize` |
| 新项目引用同电路旧项目历史 | `opt_requirement.history_warm_start.md` | `optimize` + History Warm Start |
| 多 process corner 项目引用同电路旧项目历史 | `opt_requirement.history_warm_start.multi_corner.md` | `optimize` + History Warm Start |
| 固定参数点和 waveform CSV 导出 | `opt_requirement.fix_run.md` | `fix_run` |
| 固定参数点、只提取 scalar Metrics | `opt_requirement.fix_run.metrics_only.md` | `fix_run` |
| 多 testbench 固定点、同时提取 Metrics 与 Waveform | `opt_requirement.fix_run.multi_testbench.metrics_waveform.md` | `fix_run` |

## 命令

`ic-opt` 不在 PATH 上。前置要求 Python 3.11+；在工具仓库根执行
`./.venv/bin/ic-opt`（或先 `source .venv/bin/activate` 再省略前缀），与
`docs/USER_GUIDE_CN.md` 一致。

Local:

```bash
./.venv/bin/ic-opt PROJECT_DIR --doctor
./.venv/bin/ic-opt PROJECT_DIR --real
./.venv/bin/ic-opt PROJECT_DIR --real --continue N
```

Remote:

```bash
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real --continue N
```

`--continue N` 是追加仿真入口。`--ssh-profile PROFILE` 只选择远端执行 profile，
不是资源或优化器覆盖。续跑沿用项目已经生成的 backend：OpenBox 续跑 OpenBox，
native TuRBO 续跑 native TuRBO，不允许静默换 backend 或重新走初始化点。每个 Remote
续跑 attempt 都会先对当前远端环境重新执行一次 Doctor，然后才允许恢复 snapshot、同步
历史和启动优化器。

Remote 续跑除了重跑 Doctor 之外，还有三个已实现的中止门，任意一个都会在追加预算之前
让 `--continue N` 失败：

- **Remote attempt 独占锁**：`state/remote_attempt.lock`。锁不会被自动抢占
  （`RemoteAttemptLockedError`）；必须先看锁的 owner 元数据，再手动删除锁目录。
- **无优化器历史**：`cannot continue without optimizer history: <path> is
  missing or empty` —— 对应 backend 的 evaluations 历史文件缺失或为空。
- **旧历史验收被拒**：续跑前会先对已有历史重新跑一次验收，验收状态不是
  `accepted` 时报错 `prior optimizer history acceptance rejected: ...`。

Cadence 环境查找顺序：显式传入 `--cadence-cshrc PATH` 时用它；否则用
`<REMOTE_PROJECT_DIR>/cadence_env.csh`（远端项目目录下）。

`./.venv/bin/ic-opt PROJECT_DIR --real --dry-orchestration` 是仅限本地首轮
optimize 的离线编排检查入口：跑完编排检查后停在真实 Spectre/OCEAN 候选执行之前，
`reports/optimizer_flow_run_report.json` 里的 `stopped_before` 字段会写明停在
`run-openbox-real` 还是 `run-native-turbo-real`。不支持续跑、fix-run 或 remote。

长跑期间没有产品级进度子命令；可以直接读 `state/optimizer_state.json` /
`state/best_candidate.json`，或例外使用开发 CLI 的
`hermes-workflow optimizer-status`（只读状态查询，不算低层开发命令禁令覆盖的
写操作）。

## History Warm Start

`History Warm Start` 是新建 optimize 项目时引用同一电路旧项目历史的入口，不是
`--continue N`。这两条限制强度不同：`history_warm_start.enabled: true` 出现在
fix-run 项目里，是 requirement/project 校验阶段的硬失败（"only supported for
optimize workflow"），不是建议；而"不能和 `--continue` 一起跑"是产品语义上的约定——
`--continue N` 只给同一个项目追加预算。Continuation 会重新校验当前
requirement，但不会把 requirement 的改动重新物化为本轮执行配置——续跑仍使用
已有配置、快照和优化历史，其中就包括不会读取/应用 History Warm Start 段，
所以两者组合不会报错，只是 warm-start 段不会生效。
启用的 History Warm Start 只支持 OpenBox；与任何非 OpenBox 解析后端组合都会在
requirement/project 校验阶段明确失败，不只是 native TuRBO——`random_baseline`
同样会被拒。Native TuRBO 或 random_baseline 项目追加预算应使用 `--continue N`。

最小 section：

```yaml
enabled: true
sources:
  - path: /path/to/previous_same_circuit_project
    label: round1
max_observations: 200
warm_start_strategy: topk
```

它会生成 `config/history_warm_start.yaml`。第一版要求新旧项目变量名完全一致，metric
定义一致；旧点超出当前空间会记为 `out_of_current_space`。运行后必须检查
`reports/history_warm_start_audit.json`、`reports/history_warm_start_audit.md`，以及
`reports/optimizer_run_report.json` 里的 `openbox.history_warm_start`。有约束项目通常显示
`initial_configurations_from_history`；无约束单目标项目才可能显示
`transfer_learning_history`。

History warm-start 的实际应用只支持 OpenBox backend。native TuRBO 不会消费这些历史
点来影响新 candidate；如果用户希望旧项目历史真正参与下一轮建议，应选择 OpenBox。
TuRBO 报告里 history 相关内容可能不存在，或显示为 `not_available`。

## Optimizer Insight Report

优化或 finalize 后，agent 应优先查看：

```text
reports/optimizer_insight_report.html
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
```

HTML 是给用户阅读的主报告；JSON 是机器可读合同；Markdown 是文本备份。
HTML 适合快速定位问题，但不能替代底层事实。判断 trade-off、history 是否真正生效、
或者下一轮变量范围时，还要查看 `reports/optimizer_insight_report.json`、
`reports/optimizer_run_report.json` / `reports/native_turbo_optimizer_report.json`、
`reports/history_warm_start_audit.json`、
`reports/optimizer_evaluations.jsonl` / `reports/native_turbo_optimizer_evaluations.jsonl`、
`ledger/experiment_ledger.jsonl` 和 `runs/**/metric_result_manifest.json` 中实际存在的文件。

Pareto/trade-off 分析只基于已有 raw metrics 做报告层 trade-off 总结，不表示
OpenBox 已启用 multi-objective optimizer mode，也不改变 candidate 选择或 objective。
Space Compression Advisory 使用 OpenBox compressor dry-run，只给出人工复盘建议，
不会自动应用到 optimizer。用户认可后，可以把建议范围写进新的
`opt_requirement.md` 再开下一轮。

如果 backend 是 native TuRBO，HTML/JSON 报告仍可保留 backend-neutral 内容，例如 best
point、实际测量 metric、evaluation/status counts、plots、raw-metric trade-off summary，
以及仅用于建议的 space-compression dry-run。OpenBox 专属内容不应期待存在，包括
history warm-start application、advanced surrogate visualization、parameter importance；
这些 section 可能缺失或显示 `not_available`。

如果 objective 直接对 dB、dBm 这类带符号或对数域 metric 做乘除，尤其数值可能跨过
0 时，排序会很难解释。workflow 会保留用户写的 objective；需要重新设计 objective
时，应在下一版 requirement 中明确改成线性域或归一化后的表达。

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
- `Approval Checklist`（optimize 和 fix-run 都是必需 section，不只是 fix-run）

Maestro/ADE point root 是结果点目录本身，不是 `input.scs` 文件，也不是 `psf/`
目录。它必须包含 `netlist/input.scs`。常见目录形态：

```text
/home/username/simulation/<virtuoso_library>/<cellview_name>/maestro/results/maestro/Interactive.N/1/<test_name>
```

例如：

```text
/home/username/simulation/Virtuoso_Bridge_test/MixerCS_PSS_IIP3/maestro/results/maestro/Interactive.28/1/Mixer_CS_IIP3
```

fix-run requirement 还包含：

- `Workflow.mode: fix_run`
- `Fixed Points`
- `Waveform Exports`
- `Approval Checklist`（必需 section）

fix-run 不创建 optimizer state，也不写 optimizer decision report。

fix-run 中 `parallel_jobs` 是同一个 fixed point 内 testbench/corner child 的并发数；
`threads_per_run` 是每个 Spectre 子进程的线程数。fixed points 仍串行执行，agent
不能添加 CLI 参数来覆盖这个值。

## 优化策略

生产使用时，把下面四种策略看成并列选择：

- `algorithm: openbox`, `strategy: openbox_gp_eic`
- `algorithm: openbox`, `strategy: openbox_prf_eic`
- `algorithm: openbox`, `strategy: openbox_auto` —— 这是 OpenBox 项目省略
  `strategy` 时自动解析出的默认值，`opt_requirement.multi_testbench.md` 和
  `opt_requirement.history_warm_start.md` 两个脱敏模板都显式写了它。看到
  requirement 里是 `openbox_auto` 时不要当成非法值。
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
examples/spectre_maestro_project/opt_requirement.history_warm_start.multi_corner.md
```

agent 需要报告 objective policy、constraint policy、被选中的 run、各 corner
聚合结果，以及 worst-case 或 all-corners 约束判断。

multi-testbench 示例必须保留真实跑通过的 Mixer 路由结构：
`opt_requirement.multi_testbench.md` 和 `opt_requirement.multi_tb_corner.md`
中，metric 名字是 `BW`/`MAX_GAIN`/`NF_3G`（路由到 testbench `cg_nf`）、`IIP3`
（路由到 testbench `iip3`）、`P1DB`（路由到 testbench `p1db`）——按 "CG" 去 grep
模板会落空，metric 名字实际是 `MAX_GAIN`。history 场景使用
`examples/spectre_maestro_project/opt_requirement.history_warm_start.md`，这是
第二轮同电路 history 验证 requirement 的脱敏版本。

## Fix-Run

fix-run 使用同一个产品命令：

```bash
./.venv/bin/ic-opt PROJECT_DIR --real
./.venv/bin/ic-opt --ssh-profile PROFILE PROJECT_DIR --real
```

使用模板：

```text
examples/spectre_maestro_project/opt_requirement.fix_run.md
examples/spectre_maestro_project/opt_requirement.fix_run.metrics_only.md
examples/spectre_maestro_project/opt_requirement.fix_run.multi_testbench.metrics_waveform.md
```

正确的 pnoise waveform expression 形式是：

```text
getData("NF" ?result "pnoise")
```

fix-run 项目里的 `Process Corners` 不接受 `objective_policy` / `constraint_policy`
字段——写了就会在 requirement intake 阶段直接报错（"aggregation policies are not
supported for fix_run workflow"）；fix-run 总是执行每一个声明的 corner，intake 内部
会把这两个字段的记账值强制补成 `nominal`/`nominal`，不代表可以聚合或挑选。

## 必查过程文件

不要只看退出码。`reports/optimizer_flow_run_report.json` 是 optimizer workflow
的最终成功标记——只有在 Remote Host/本地验证完所有 parent/child manifest 之后，
pass 状态才会写入这个文件。真实 workflow 验收至少看：

```text
reports/optimizer_flow_run_report.json
reports/optimizer_run_acceptance_report.json
reports/optimizer_completion_report.json
reports/optimizer_finalize_report.json
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/native_turbo_optimizer_report.json
reports/optimizer_decision_report.json
reports/optimizer_decision_report.md
reports/optimizer_insight_report.html
reports/optimizer_insight_report.json
reports/optimizer_insight_report.md
reports/history_warm_start_audit.json
reports/history_warm_start_audit.md
reports/optimizer_evaluations.jsonl
reports/native_turbo_optimizer_evaluations.jsonl
ledger/experiment_ledger.jsonl
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

项目根的 `supervisor_instruction.json` 是审批门的记录（`decision` 和 `reason`
字段），由 approve 步骤在真实 backend 启动前写入；如果一次运行卡在 `approve`
这一步，先看这个文件。

multi-testbench / multi-corner 项目还要看 parent aggregate manifest。

Remote 模式下，权威产物在远端 `PROJECT_DIR/reports/...`；本地还会有一份缓存在
`~/.ic-opt/remote_runs/<ssh_profile>/<profile+远端路径 sha256 前16位>/` 下，与
`docs/USER_GUIDE_CN.md` 描述的 cache 是同一个。CLI 每次远程运行/doctor 后都会打印
`local report: ...` 和 `remote report: ...` 两行，直接读这两行路径即可，不用自己
拼 digest。

fix-run 项目必须先看 `reports/fix_run_report.json`。它的 `points[]` 数组里每个
固定点都带 `run_id` 和三组权威路径字段：`scalar_metric_manifest_paths`、
`waveform_export_manifest_paths`、`csv_artifact_paths`——目录形态因项目而异
（testbench×corner、只有 testbench、只有 corner、或都没有），`<run_id>` 从
`real_001` 起随固定点递增（`real_002`、`real_003`...），不要只查
`real_001` 就下结论。

重点核对 requirement 变量是否传递并生效：算法、策略、初始化、随机种子、budget、
batch size、并行数、Spectre 线程数、optimizer CPU cap、process corners、
`output_format: psfxl`、license probe 和 `command_trace`。
