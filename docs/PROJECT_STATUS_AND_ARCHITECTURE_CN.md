# 项目当前状态与工作原理说明

日期：2026-06-07

本文只记录有代码、报告、计划或真实运行证据支撑的事实。

## 0. 结论先说清楚

当前项目已经跑通的是一个产品级 shell 自动化核心、真实 OpenBox/Spectre/OCEAN
优化流程、Claude `/ic-opt` 短入口，以及 C-64 的 Claude subprocess handoff
验收路径。[E1][E2][E3][E19][E20]

当前可用 shell 入口是 `ic-opt PROJECT_DIR --real`，它是 Python console
script。[E1][E3]

当前 C-65 产品目标已经修正为 runtime-native：用户在哪个 agent CLI 里输入
`/ic-opt PROJECT_DIR --real`，哪个 CLI 的当前会话就是 supervisor agent，
并使用同一个 CLI 的原生 subagent/task 机制执行真实优化任务。Claude 和
OpenCode 的入口资产已经加入仓库；C-64 的 `--execution-agent claude`
subprocess 方式保留为开发/验收证据，不再被描述为默认产品形态。[E2][E20]

当前 `ic-opt` shell 命令默认是 direct 自动化路径，会在同一个 Python 流程
里调用真实 OpenBox/Spectre/OCEAN 优化后端。runtime-native `/ic-opt`
adapter 则应先让 supervisor 运行 `--dry-orchestration` 生成并批准
`OPTIMIZER_EXECUTION_TASK.md`，再由同一 runtime 的 execution subagent
运行该任务，最后由 supervisor closeout 和汇报。[E3][E4][E20]

因此，如果用户说“运行 `ic-opt` 之后 agent 接入在哪里”，准确答案是：
shell `ic-opt PROJECT_DIR --real` 本身是自动化脚本入口；agent 接入发生在
runtime adapter 层，即 `/ic-opt PROJECT_DIR --real` 由当前 CLI 的 supervisor
agent 执行，并调用同 runtime 的 execution subagent。[E2][E4][E19][E20]

当前仍然不是“任意 agent runtime 都已经实测支持”的产品。C-65 增加了
Claude/OpenCode runtime adapter 资产和安装命令，但每个 runtime 仍需要在
目标环境完成一次 native-subagent drill，才能声称该 runtime 已经完全落地。
[E2][E5][E19][E20]

## 1. 项目原始目标

顶层计划定义的目标不是“写一个单纯仿真脚本”，而是构建 IC 自动优化工作
流：supervisor agent 负责规划、审批、决策和报告，Hermes workflow tooling
负责确定性文件合同、验证、打包和报告，execution agent 负责工具侧
Virtuoso/Spectre/OCEAN/OpenBox 执行。[E6]

这个角色模型仍然是目标架构，且 `AGENTS.md` 明确禁止把 Hermes 说成一个
agent；Hermes 在本项目中是 workflow tooling。[E7]

当前实现最成熟的部分是 Hermes workflow tooling、shell 自动化核心、真实
多 testbench optimizer 流程和报告链；agent 侧正在收敛到 runtime-native
adapter 形态。尚未完成的部分是 Codex/OpenClaw/HermesAgent 等 runtime 的
入口适配、公开发布级 installer，以及各 runtime 的 native-subagent 实机
drill。[E2][E3][E6][E19][E20]

## 2. 当前 `ic-opt` 到底是什么

`ic-opt` 是 `pyproject.toml` 注册的 console script，入口指向
`hermes_workflow.product_cli:app`。[E1]

`product_cli.py` 的 `main()` 负责解析 `PROJECT_DIR`、`--real`、
`--max-evals`、`--batch-size`、`--parallel-jobs` 和可选
`--cadence-cshrc`，然后调用 `optimize_project()`。[E3]

`product_cli.py` 的 `_resolve_cadence_cshrc()` 只查四类用户提供的 Cadence
环境锚点：显式 `--cadence-cshrc`、`PROJECT_DIR/cadence_env.csh`、
`IC_OPT_CADENCE_CSHRC`、`~/.ic-opt/cadence_env.csh`。[E3]

`ic-opt` 不自动推断 `.bashrc` 或 `.zshrc`，也不应该硬编码 Spectre 版本。
[E3][E7]

所以 `ic-opt` 是一个产品 shell CLI 自动化入口；它可以被 agent 调用，但它
本身不是 agent，也不是 slash command。[E1][E2]

## 3. `ic-opt` 自动化了什么

`ic-opt PROJECT_DIR --real` 会调用 `optimize_project()`，该函数把整个流程串
成 16 个固定步骤。[E4][E8]

第一步 `check-requirement` 会读取 `PROJECT_DIR/opt_requirement.md`，检查必
需章节是否存在，并把检查报告写到 `reports/requirement_intake_report.json`。
[E9][E10]

`opt_requirement.md` 不是自由聊天文本；它必须包含固定的二级标题章节，且每
个章节必须有且只有一个 fenced `yaml` 代码块。[E9]

当前必需章节包括 `Project`、`Maestro Source`、`Design Variables`、
`Metrics`、`Constraints`、`Objective`、`Spectre Settings`、
`Optimizer Settings` 和 `Approval Checklist`。[E9]

`Approval Checklist` 必须显式确认公式、Maestro source、变量范围和 Spectre
资源设置已经由用户批准，否则 intake 会失败。[E9]

第二步 `prepare-from-requirement` 会把 markdown 中的结构化 YAML 渲染成
`config/project_config.yaml`、`config/variables.yaml`、
`config/metrics.yaml`、`config/spectre.yaml`、`config/optimizer.yaml`，
并在多 testbench 情况下额外生成 `config/testbenches.yaml`。[E9]

所以 shell 自动化核心确实可以完成 `opt_requirement.md` 到标准 YAML 配置
的转换；这个能力不是靠用户预先手动生成 `config/*.yaml`。[E9][E10]

`prepare-from-requirement` 还会根据 markdown 里的 `maestro_point_root`
导入 Maestro/ADE point-root 下的 `netlist/input.scs` 和相关 sidecar 文件。
[E9]

单 testbench 项目会导入到 `netlists/exported/`；多 testbench 项目会按
testbench id 导入到 `netlists/testbenches/<id>/exported/`，并额外保留一个
primary legacy `netlists/exported/` 路径。[E9]

导入时会检查 `maestro_point_root/netlist/input.scs` 是否存在，并会对 symlink
做安全检查，避免复制逃逸 Maestro point root 的文件。[E9]

导入完成后，`prepare-from-requirement` 会调用 `prepare_netlist()`，根据
导入的 `input.scs` 生成可替换设计变量的 `template.scs`。[E9][E11]

后续 `validate` 会验证配置和合同，`check-project-ready` 会检查 requirement、
config、netlist/template 和最终报告状态。[E4][E12]

`package` 会生成普通 execution package；`package-optimizer-task` 会生成
optimizer 执行任务包和 `OPTIMIZER_EXECUTION_TASK.md`。[E4][E13]

`dry-run` 会在不调用真实工具的情况下渲染候选点的 `input.scs`，用于检查模板
替换和合同路径。[E4][E11]

`preflight-health` 和 `approve` 会做真实运行前健康检查和第一轮真实运行批准。
[E4]

`run-openbox-real` 会进入真实 OpenBox 优化流程，并根据 `batch_size` 和
`parallel_jobs` 控制候选生成批次和同时发起的 Spectre run 数量。[E4][E14]

真实运行过程中，OpenBox 负责生成候选点；项目要求不能手选点来冒充 optimizer
流程。[E7][E14]

每个 candidate 会被渲染进 Spectre netlist，调用 Spectre 产生结果，再调用
OCEAN 计算用户批准的 metric 公式。[E4][E8]

多 testbench 情况下，一个 candidate 会同步渲染到多个 preserved Maestro/ADE
netlist bundle，并在 candidate 层聚合各 child testbench 的 scalar metric。
[E6][E11]

`check-optimizer-run` 会验收 optimizer artifacts；`summarize-optimizer-run`
会生成 completion 报告；`finalize-optimizer-run` 会整理 best observed；
`visualize-optimizer-run` 会生成 insight/visualization 报告；`decide-optimizer-run`
会生成主管 agent 可读的 decision report。[E4][E8]

`optimize_project()` 最后会把总流程状态写到
`reports/optimizer_flow_run_report.json`，并把 `user_decision_required` 置为
true，让用户或 supervisor agent 决定接受当前 best observed 还是继续优化。
[E4][E8]

## 4. C-60 真实证据说明了什么

C-60 的真实证据项目是
`/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb`。[E8]

C-60 记录显示，该项目从 fresh data-only start 开始，只复制了
`opt_requirement.md` 和项目本地 `cadence_env.csh`，没有复制旧的 `runs/`、
`reports/`、`ledger/` 或 `state/`。[E15]

当前该目录已经包含 `config/`、`execution_package/`、`netlists/`、`reports/`、
`runs/` 和 `state/`，这些是运行 `ic-opt` 后生成的 artifacts。[E16]

C-60 的 `optimizer_flow_run_report.json` 明确记录 16 个步骤全部 pass，包括
`check-requirement`、`prepare-from-requirement`、`run-openbox-real`、
`visualize-optimizer-run` 和 `decide-optimizer-run`。[E8]

C-60 的 `requirement_intake_report.json` 状态为 pass，且记录识别了 9 个必需
sections。[E10]

C-60 的 `optimizer_decision_report.md` 记录完成 100 次真实 evaluations，
其中 `68 constraint_failed`、`16 feasible`、`16 metric_check_failed`，推荐
feasible candidate `real_051`，并且声明 `Global optimum claim: false`。[E17]

因此，C-60 证明的是：从 `opt_requirement.md` 加 Cadence env anchor 出发，
shell 自动化核心可以生成配置、导入 netlist、准备合同、跑真实 OpenBox/Spectre/OCEAN
优化，并生成报告。[E8][E10][E15][E17]

C-60 没有证明的是：用户在 agent chat 里输入 `/ic-opt PROJECT --real` 后，
supervisor agent 会自动调用独立 execution agent 完成任务。[E2][E4]

## 5. 当前 agent 接入到底做到哪里

项目已经定义并记录了 supervisor agent、Hermes workflow tooling、execution
agent 三个角色。[E6][E7]

项目已经能生成 execution package 和 optimizer execution task package，文件中
包含执行命令、审计命令和要求返回的 artifacts。[E13]

这些任务包可以作为未来 execution agent 的工作输入，但当前 `ic-opt` 没有
调用 Claude/Codex/local subagent 去读取并执行该任务包。[E4][E13]

当前 `optimize_project()` 在生成 `package-optimizer-task` 之后，直接调用
`run_openbox_real_optimization()`，所以真实执行发生在 CLI 进程里，而不是由
独立 execution agent 完成。[E4]

这意味着当前落地形态更接近“主管 agent 操作一个强自动化 CLI”，而不是
“主管 agent 自动派发执行 agent”。[E2][E4]

用户指出“如果我自己运行这个，那 agent 接入呢”是正确问题，因为当前实现还
没有把 agent runtime 层做出来。[E2]

## 6. 当前项目不是在糊弄的部分

当前项目不是只跑了一个已经生成好的项目，因为 `prepare-from-requirement`
确实会从 `opt_requirement.md` 生成配置并导入 Maestro point-root netlist。
[E9]

C-60 不是只读取旧 reports，因为 flow report 显示真实经过了
`run-openbox-real`，且 optimizer decision report 显示 100 次 evaluations。
[E8][E17]

当前项目不是 Python 重写 OCEAN metric，因为 metric payload 保存的是用户批准
的 `ocean_expression`，并把 `expected_value_type` 设为 `real_scalar`；项目边界
仍禁止 Python 解析 PSF 或重写 OCEAN 公式。[E7][E9]

当前项目不是声称全局最优，因为 decision report 明确写出
`Global optimum claim: false`，且推荐语义是 best observed/configured candidate。
[E17]

当前项目不是 per-project venv，因为 release checklist 和 AGENTS 都要求一个
repo/product-level `.venv`，用户项目目录只是数据和 artifacts 目录。[E7][E18]

## 7. 当前项目确实缺失的部分

Claude CLI 的 `/ic-opt` slash skill wrapper 已经完成并真实跑通；Codex 或其它
agent runtime 的对应入口还没有实现。[E19]

Claude runtime 的自动 supervisor-agent -> independent execution-agent
dispatch 已经完成一次真实 drill。[E20]

项目已经把 Claude CLI 的“agent 产品入口”推进到类似 veriflow-cc 的短命令
体验，并且 C-64 已经证明这个短命令会派发独立 execution-agent；但还缺少
clean-machine 安装验证和非 Claude runtime 入口适配。[E19][E20]

项目仍缺少决定：首个公开版本是否只承诺 Claude runtime，还是继续实现
Codex/其它 agent runtime 的等价入口。[E2][E20]

## 8. 和顶层 plan 的对应关系

顶层 plan 的角色模型仍然成立：supervisor agent 做规划与决策，Hermes tooling
做确定性合同和报告，execution agent 做真实工具执行。[E6]

C-57 到 C-61 把 Hermes tooling 的 shell 自动化链条做到了可真实运行程度：
`hermes-workflow optimize`、`ic-opt`、product `.venv`、Cadence env anchor、
真实 C-60 acceptance 和 release docs。[E5][E15]

C-62 修正的是计划叙述偏差：不能因为 shell 自动化链条跑通，就把它说成
两-agent产品已经落地。[E2][E5]

C-63 完成了第一个 Claude CLI `/ic-opt` slash skill 入口，并用 fresh
multi-testbench Mixer 项目真实跑完 100 evaluations。[E19]

C-64 完成了 Claude runtime 的 observable supervisor -> independent
execution-agent handoff，并用 fresh multi-testbench Mixer 项目真实跑完
100 evaluations。[E20]

当前实现与顶层 plan 的剩余偏差点不是 optimizer 内核，也不是 Claude CLI
短入口，也不是 Claude 的 execution-agent handoff，而是非 Claude runtime
覆盖和 clean-machine 安装验证。[E2][E6][E19][E20]

## 9. 现在用户实际该怎么理解这个项目

如果用户现在直接使用本 repo，它能作为一个自动化优化工具运行：

```bash
cd /home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow
./.venv/bin/ic-opt /path/to/project --real
```

这个命令会自动做 markdown intake、config 生成、Maestro netlist 导入、模板
准备、合同验证、package/preflight/approval、OpenBox/Spectre/OCEAN 真实优化、
artifact 验收、可视化和 decision report。[E3][E4][E9]

如果用户现在让 Claude CLI 使用它，安装 `claude_skills/ic-opt` 后可以直接
输入：

```text
/ic-opt /path/to/project --real
```

Claude 会触发该 skill，并由 skill 调用 shell 自动化核心；默认情况下它会
追加 `--execution-agent claude`，在 `package-optimizer-task` 后派发独立
Claude CLI execution-agent process。[E19][E20]

如果最终产品要满足“The less user needs to talk to agent, the better”，那么
Claude CLI 路径已经达到短命令入口，并且已经完成独立 execution-agent
handoff；下一步应收窄到 release/install/readiness，或在明确选择其它 runtime
后实现对应 adapter。[E2][E7][E19][E20]

## 10. 下一步必须怎么做

下一步不应该继续添加 optimizer 新功能，除非它是阻塞产品入口的 bug。[E2]

下一步不应该再定义新的 optimizer 功能路线，而应该围绕产品落地收窄：
可以做 fresh real Claude handoff 复验、clean-machine Claude skill/install
check、release/readiness pass，或在用户明确选择 Codex/其它 runtime 时实现
对应 adapter。[E2][E19][E20]

后续 product-landing 工作不应改变 optimizer math、OCEAN formulas、Spectre
version、OpenBox route、multi-testbench aggregation 或 per-project venv
policy，除非真实产品运行暴露具体问题。[E7]

## Evidence Index

E1. `pyproject.toml` `[project.scripts]` registers `ic-opt =
"hermes_workflow.product_cli:app"` and `hermes-workflow =
"hermes_workflow.cli:app"`.

E2. `docs/AGENT_INTEGRATION_STATUS.md` states the implemented shell CLI,
implemented Claude CLI `/ic-opt` skill route, implemented Claude execution-agent
handoff, missing non-Claude runtime adapters, and clean-machine installer gap.

E3. `src/hermes_workflow/product_cli.py` defines `ic-opt` behavior:
Cadence cshrc discovery and call into `optimize_project()`.

E4. `src/hermes_workflow/optimizer_flow.py` defines `optimize_project()` and
its ordered steps. Direct mode runs `run-openbox-real`; Claude mode replaces
that step with `execution-agent-handoff`, then resumes supervisor-side closeout.

E5. `docs/superpowers/plans/2026-06-07-agent-integration-reality-audit.md`
records the C-62 correction.

E6. `docs/superpowers/plans/2026-05-28-ic-auto-opt-workflow-execution-plan.md`
defines the supervisor/Hermes/execution-agent architecture and current node.

E7. `AGENTS.md` records the locked role model, product environment rule,
Cadence env rule, no-PSF/no-formula-rewrite boundary, and C-62 agent boundary.

E8. `/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb/reports/optimizer_flow_run_report.json`
records 16 passed flow steps and recommended `real_051`.

E9. `src/hermes_workflow/requirement_intake.py` implements
`check_requirement()`, `prepare_from_requirement()`, `render_config_payloads()`,
`write_config_payloads()`, `import_maestro_point_netlist()`, and markdown
section/YAML parsing.

E10. `/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb/reports/requirement_intake_report.json`
records status pass and 9 parsed sections.

E11. `src/hermes_workflow/netlists.py` and `src/hermes_workflow/dry_run.py`
implement netlist/template preparation and dry-run rendering paths.

E12. `src/hermes_workflow/project_readiness.py` implements project readiness
checks for requirement, configs, contract validation, netlists, and final
reports.

E13. `src/hermes_workflow/optimizer_task_package.py` implements optimizer task
package generation and command/audit artifact fields.

E14. `src/hermes_workflow/openbox_backend.py` implements OpenBox real
optimization settings such as `batch_size` and `parallel_jobs`.

E15. `docs/NEXT_DEVELOPMENT_LOG_2026-05-31.md` C-60 section records the fresh
data-only start and real one-line command evidence.

E16. The current C-60 evidence directory contains generated `config/`,
`execution_package/`, `netlists/`, `reports/`, `runs/`, and `state/` alongside
the original `opt_requirement.md` and `cadence_env.csh`.

E17. `/tmp/ic_auto_opt_c60_one_line_real_PpguO7/Mixer_opt_muti_tb/reports/optimizer_decision_report.md`
records 100 evaluations, status counts, feasible recommendation `real_051`,
and `Global optimum claim: false`.

E18. `docs/PRODUCT_RELEASE_CHECKLIST.md` records the product `.venv` setup and
states it validates the shell automation core, not the completed two-agent
product.

E19. `docs/CLAUDE_IC_OPT_REAL_LANDING_2026-06-07.md` records the C-63 Claude
CLI slash-skill landing. The fresh project
`/tmp/ic_auto_opt_claude_landing_JjIiNj/Mixer_opt_muti_tb` started with only
`opt_requirement.md` and `cadence_env.csh`; after installing
`claude_skills/ic-opt`, `claude -p --dangerously-skip-permissions "/ic-opt
PROJECT --real"` completed 100 real evaluations and recommended feasible
`real_051`.

E20. `docs/CLAUDE_EXECUTION_AGENT_HANDOFF_2026-06-07.md` records the C-64
Claude execution-agent handoff drill. The fresh project
`/tmp/ic_auto_opt_c64_handoff_zX9JrO/Mixer_opt_muti_tb` started with only
`opt_requirement.md` and `cadence_env.csh`; `claude -p
--dangerously-skip-permissions "/ic-opt PROJECT --real"` wrote
`reports/execution_agent_handoff_report.json` with `status=pass`,
`execution_agent=claude`, `returncode=0`, completed 100 real evaluations, and
recommended feasible `real_051`.
