# ic-auto-opt-workflow v0.1.10 真实工况审计与修复台账

> 本文是项目维护文档，不是上游依赖或 EDA 工具的官方说明。它合并了 Codex
> 对 `ic-auto-opt-workflow` 的严格源码审计，以及 Fable 5 对该审计的独立逐条
> 复核。本文用于保存根因、证据、修复边界和验收标准，防止问题在后续开发中
> 因上下文丢失而被弱化或遗漏。

## 1. 文档状态

- 审计基线 commit：`e75e4b18e2a445f65c9e9046ca725b90bcf4de12`
- 审计版本：`0.1.10`
- 审计分支：`plan-a-hermes-file-contract-mvp`
- 基线全量测试：`1368 passed`
- Codex 审计性质：源码、测试、图谱和真实/最小复现的只读审计
- Fable 5 复核性质：约 32 条可落地断言逐条核对，十余条通过仓库 `.venv`
  运行解析或渲染函数复现
- Fable 5 复核结论：30 条完全证实、2 条部分证实、0 条被推翻
- 审计阶段仓库修改：无
- 当前修复状态：v0.1.10 计划内的结果可信度、Remote 可靠性、CLI/能力合同、
  Requirement 科学语义和 continuation 修复均已完成。发行 checkout 软件验收通过；
  隔离 Remote Native TuRBO 已在既有 100 次结果上真实 continuation `+20` 并通过
  最终验收。最终状态和延期边界以第 21 节为准。

Fable 5 的复现脚本曾保存在其会话 scratchpad，例如
`test_b1.py`、`test_b2.py`、`test_b4.py`、`verify_assertions.py` 和
`d1~d3b_probe.py`。这些脚本不在仓库中，因此只能作为独立复核证据，不能替代
永久回归测试。正式修复必须先把关键复现转成仓库内的红色测试。

## 2. 真实使用场景和判断标准

本项目的 Remote Mode 面向以下正常工程场景：

1. 用户在 Windows/WSL、Linux 工作站或其他个人 Controller 上操作。
2. Cadence、Spectre、OCEAN 和 Maestro 数据位于实验室 Remote Host。
3. Controller 与 Remote Host 文件系统相互隔离。
4. Controller 只协调优化、保存优化器状态和接收明确传输的产物。
5. Remote Host 执行仿真并拥有 Remote-owned Path。

因此，以下情况不能作为 Remote 功能正确的依据：

- Controller 偶然可以直接访问 Remote Host 的同名绝对路径；
- Controller 与 Remote Host 通过 NFS 共享 Maestro 或运行目录；
- Controller 自己 SSH 到自己；
- 只运行一次候选点，没有验证迭代、状态恢复、结果同步和最终报告；
- FakeRunner 每次下载时临时生成“新”指标，没有模拟持久的远端目录；
- 测试只检查函数被调用，没有检查真实 backend 和真实文件内容。

本文使用以下结果可信度原则：

- 每个候选结果必须证明属于当前 attempt 和当前 candidate；
- 配置报告必须描述真实写入 netlist 的内容，不能只回显 YAML；
- 空执行、旧报告或旧指标不能形成 `pass`；
- SSH 传输、权限和命令错误必须 fail closed，不能降级为“文件不存在”；
- 不支持的模式或参数组合必须尽早明确拒绝，不能静默忽略。

## 3. 总体结论

项目的基本架构和大多数实现都是真实存在的，不是空壳工程：

- 两种一级工作流 `optimize` 和 `fix_run` 均有实际实现；
- local 与 remote 两种传输模式均有实际执行路径；
- OpenBox GP-EIC、OpenBox PRF-EIC 和 native TuRBO 都有真实优化器代码；
- 36 个 `hermes-workflow` 子命令和一个 `ic-opt` 产品入口中，没有纯 `pass`
  或空 callback。

但是，当前绿灯测试不能证明真实工程结果可信。审计发现的问题集中在五类：

1. **结果污染或假成功**：旧指标被当成新结果、空 fix-run 报告为 pass、旧成功
   marker 未失效。
2. **科学语义没有落地**：Metrics 被丢弃、constraint 单位被忽略、corner override
   没有真正改 netlist。
3. **Controller/Remote 环境差异**：登录 shell、持久远端状态、传输工具和 SSH
   返回码没有按真实环境处理。
4. **能力声明与实现漂移**：TuRBO continuation、dry orchestration 和部分 CLI
   命令的用户承诺与实际执行不同。
5. **测试假阳性**：FakeRunner、monkeypatch 和手写报告绕开了真实状态和真实
   backend。

## 4. 第一优先级：直接影响结果可信度的问题

### A1. 旧 Remote run 目录和指标可能混入新一轮优化

**真实场景**

同一个 Remote 项目完成过一次优化。用户删除或重新建立 Controller Cache，随后
对同一个 Remote 项目再次执行一个非 `--continue` 的 fresh run。

**当前行为**

- fresh Controller Cache 中没有本地 run history，因此 run 编号会重新从
  `real_001` 开始；
- Remote Host 上旧的 `runs/real/real_001` 仍然存在；
- `upload_tree()` 使用 `mkdir -p` 加 `tar -xf`，把新内容合并进旧目录，而不是
  替换整个目录；
- 如果本轮 OCEAN 返回 0，但没有生成新的 `ocean_scalars.tsv`，旧文件仍在；
- 下载和解析阶段没有证明指标属于当前 attempt，也没有新鲜度检查。

**已复现结果**

在持久 Remote 状态夹具中预放旧的
`real_001/metrics/ocean_scalars.tsv`，本轮 OCEAN 不生成新指标但返回 0，adapter
最终得到：

```text
adapter_status=succeeded stale_scalars_consumed=True
```

**后果**

旧候选的指标可能被当成本轮候选结果，直接污染优化器观测、最优点、约束判断和
最终报告。这不是普通可用性问题，而是结果数据完整性问题。

**触发条件精确化**

主要触发条件是：同一个 Remote 项目、远端旧 run 目录仍存在、Controller Cache
是 fresh 状态、再次执行非 continuation 的新优化。Doctor 对结构完整的旧 run
目录没有告警，因此不能阻止该问题。

**正确行为**

- 每次 candidate 上传必须发布到一个干净、独占的 Remote run 目录；
- 不允许 tar overlay 把当前 candidate 与旧 candidate 合并；
- 下载前后应有当前 candidate 的明确完成证据；
- 当前 candidate 没有新指标时必须失败，不能读取旧文件。

**状态**：第一批代码修复和隔离 Remote fresh-run 验收完成。

### A2. Fix-run 的 Metrics section 被静默丢弃

**真实场景**

用户在 fix-run requirement 中要求导出 scalar Metrics，或者同时要求 Metrics 和
Waveform Exports。

**当前行为**

`Metrics` 不在 fix-run 的 section 提取白名单中，因此在 requirement 提取阶段就
被整体跳过。后续虽然存在渲染 `metrics.yaml` 的代码，以及“Metrics/Waveform
二选一”的校验逻辑，但这些代码拿不到被丢弃的 Metrics。

**已复现结果**

- 只写 Metrics：被误报为 Metrics 和 Waveform 两者都没写；
- 同时写 Metrics 和 Waveform：intake 可以通过，但 Metrics 消失，不生成
  `metrics.yaml`；
- `_validate_required_fields()` 中的 `has_metrics` 分支在当前 fix-run 提取路径下
  实际不可达。

**后果**

用户要求的 scalar 数据没有执行，系统可能只运行 waveform 导出，或者在合法的
metrics-only requirement 上直接失败。

**正确行为**

Fix-run 必须提取并渲染 Metrics；metrics-only、waveform-only 和二者同时存在都要
有明确、可测试的行为。

**状态**：第一批代码修复完成；三种 requirement 组合的公共接口回归通过。

### A3. Constraint 数值单位没有与 Metric 单位核对

**真实场景**

Metric 定义为 `unit: dB`，用户误写 constraint `value: 9 Hz`。

**当前行为**

Requirement intake 只要求 value 是非空字符串。OpenBox 和 native TuRBO 都能从
`9 Hz` 中提取出数值 `9.0`，单位部分被丢弃。

**后果**

量纲错误的约束被当作合法科学条件执行。对非数字字符串，两个 backend 的失败
方式还不一致：native 可能转为 penalty，OpenBox 可能抛出异常。

**正确行为**

Constraint 单位必须与对应 Metric 单位一致，并在 requirement intake 或项目
preflight 阶段失败。

**状态**：Requirement 科学语义批次已修复。intake 与 on-disk validator 共用
`parse_constraint_threshold()`：阈值必须是有限数值、数值与单位之间必须有空格，
且单位必须与 Metric.unit 精确一致；缺单位、错单位和非有限数都在仿真前失败。

### A4. Corner override 可以静默不生效，报告却声称已应用

**真实场景**

用户在 Process Corners 中拼错变量名，例如把 `temperature` 写成
`temperatur`，或者不同 testbench 的 Maestro source corner 名称不同。

**当前行为**

- corner 参数替换没有检查实际匹配和替换次数；
- 拼错变量时 netlist 保持原值，流程仍可 `pass`；
- corner manifest 的 `corner_variables` 和 `model_section` 来自 YAML 配置回显，
  没有反向验证渲染后的 netlist；
- multi-testbench 路径把 primary testbench 的 base corner 传给所有 testbench，
  没有使用当前 named testbench 自己的 source corner。

**已复现结果**

- 拼错 `temperatur` 后，`prepare-netlist` 仍然 pass，deck 仍为原来的 27℃；
- secondary testbench 的 `tt` corner 产物与它自己的 `ss` 产物字节相同。

**后果**

用户看到的 manifest 看起来正确，但仿真实际没有运行所声明的 corner。优化结果和
PVT 结论可能错误，同时证据报告无法揭示错误。

**正确行为**

- 每个声明的 corner override 必须至少命中一个批准的 netlist 参数；
- 未命中、重复歧义或拼写错误必须 fail closed；
- 每个 testbench 必须使用自己的 source/base corner；
- manifest 必须来自实际应用结果或包含可核验的替换证据。

**状态**：第一批代码修复和 900 个真实 corner deck 核验完成。

### A5. 新 Remote fix-run 失败后可能遗留上一轮成功报告

**真实场景**

同一个 Remote 项目曾成功完成 fix-run。下一次 fix-run 在 preflight、传输或正式
结束前失败。

**当前行为**

Remote attempt 开始时只归档 `optimizer_flow_run_report.json`。Fix-run 的权威
marker 是 `fix_run_report.json`，但没有在 attempt 开始时归档或失效，只在正常
结束时重新写入和同步。

**后果**

新 attempt 已失败，旧的 `status: pass` 仍可能留在远端或同步缓存中，被用户或
自动化流程误认为当前运行成功。

**正确行为**

新 attempt 开始时必须同时使与该 workflow 对应的旧权威 marker 失效；失败时只
能留下当前 attempt 的失败证据，不能保留可被误读的旧 pass。

**状态**：第一批代码修复完成；隔离验收中的旧 optimize/fix-run pass marker 均已
归档，active marker 与当前 attempt 一致。

### A6. Fix-run 不加 `--real` 会生成空成功报告

**当前行为**

`ic-opt PROJECT` 在 fix-run 模式下会调用 `run_fix_run_project(real=False)`。流程
跳过所有点和仿真，`all_issues=[]`，最后写出：

```json
{
  "status": "pass",
  "points": [],
  "optimizer_state_created": false
}
```

Optimize 模式对缺少 `--real` 有明确保护，fix-run 没有同等保护。

**状态**：第三批已修复。产品 CLI 及 local/remote public flow 双层要求
`--real`，不会再写空成功报告。

### A7. `--dry-orchestration` 在多条真实执行路径上被静默忽略

该标志只接入本地首次 optimize。Remote real、local/remote continuation 和
fix-run 会忽略它并进入真实服务；remote optimizer flow 还显式写死
`dry_orchestration=False`。

**状态**：第三批已修复。唯一合法组合是 local first-run optimize + `--real`；
remote、continuation、fix-run、doctor 组合均在任何真实服务前 fail early。

## 5. Remote 环境与可靠性问题

### B1. Remote 命令错误地依赖用户登录 shell

`RemoteSshRunner.run()` 把命令字符串直接交给 SSH。Remote prepare、retention
和 optimizer flow 使用 POSIX `if ...; then ...; fi`、shell function、`case`、
`$()` 和 `while read`，但实验室账号可能使用 csh/tcsh。

真实 tcsh 探针：

```text
tcsh -c 'if test -f /etc/passwd; then echo yes; fi'
if: Expression Syntax.
then: Command not found.
fi: Command not found.
```

项目并非完全没有考虑 csh：`license_probe.py` 和部分 doctor 探测已经显式使用
`csh -fc`。问题是其他 Remote 命令没有统一复用明确 shell 的模式。

### B2. Remote attempt 没有互斥锁

两个 Controller 可以同时准备同一个稳定 cache、读取同一份 history、分配相同
run ID，并写入相同远端目录。最小复现显示两个 attempt 都能被接受。

### B3. Remote doctor 的 Spectre/OCEAN 检查可能假通过

Doctor 把 `which spectre; which ocean` 放在一条命令中，只判断整条命令最终返回
码。若 Spectre 缺失但 OCEAN 存在，最后一条命令返回 0；关闭 license probe 时，
Doctor 可以报告两者都存在。

### B4. Run retention 把所有非零返回码都当成“目录不存在”

`test -d` 的 1 表示不存在，但 SSH 255、命令 126/127 和权限错误不是“不存在”。
当前 retention 把它们全部转换为 `remote_action=missing, issues=[]`。项目其他位置
已经存在只接受 0/1、其他返回码报错的正确模式，但这里没有复用。

### B5. Tree transfer 无超时、非原子，并有管道死锁风险

树上传和下载直接写最终目录，没有 staging/rename，也没有 timeout。进程等待与
stderr 管道读取顺序可能在大量 stderr 时阻塞；8 MiB stderr 探针曾被外层 3 秒
超时杀死。单文件 scp 已经使用原子发布，说明树传输可以复用项目已有设计思想。

### B6. Doctor 没有覆盖真实 Remote flow 使用的工具

当前 Doctor 没有完整检查 Controller 的 `scp`/`tar`，也没有检查 Remote 的
`tar`、`readlink -e`、`stat -Lc`、`sha256sum` 和 GNU `mv -T`。这些工具和参数在
真实 Remote flow 中被直接使用。

### B7. Remote preparation snapshot 没有回收策略

每次 fresh run 创建 hash+UUID 的完整 snapshot，只切换 canonical symlink，不
清理旧 snapshot。长期使用会无界增长。

### B8. Native TuRBO batch remote 审计报告错误写成 local

准确根因在 `NativeTurboBatchRunner.run()`：调用
`optimizer_cpu_thread_limits()` 时没有传
`transport_mode=self.transport_mode`，落回默认 `local`。Remote 仿真仍通过 SSH
执行，错误的是 effectiveness audit 的来源证明。

现有 `test_remote_optimizer_audit_records_remote_transport_mode` stub 掉真实 runner
并手写 `"remote"`，属于假阳性测试。

### B9. 其他已确认的 Remote 风险

- Remote doctor 的部分 dirty-state helper 会把异常降级成“不存在”（已在第 17 节
  修复）；
- Remote continuation 不重新运行 doctor，环境变化只能在后续步骤暴露（已在第 17 节
  修复）；
- local/remote fix flow 有硬编码 2026 时间戳，影响审计 provenance（已在第 17 节
  修复，并同时清理 optimizer aggregate 的同类问题）；
- Slurm/LSF job ID、scheduler submission 与 detach/reattach 属于未来可选的集群调度
  扩展，明确不在当前 direct-SSH 产品主体、修复范围或 release 完成门槛内；
- 官方 Controller 边界是 Linux/WSL，不应把本审计解释为承诺 native Windows。

## 6. Requirement 语义与模板审计

### 6.1 一级模式和组合场景

项目只有两个一级 workflow mode：

- `optimize`
- `fix_run`

传输模式有两个：

- local
- remote/SSH

因此首次执行有四个主要组合，但不能把它们误称为四个 workflow。除此之外还有：

- single/multi testbench；
- source/nominal/multi process corner；
- initial、continuation、new-project history warm start；
- doctor、real 和本地 optimize dry intent。

生产优化策略是 OpenBox GP-EIC、OpenBox PRF-EIC 和 native TuRBO；OpenBox auto 和
random baseline 属于隐式或诊断路径。

### 6.2 当前 11 个官方 requirement 模板

当前 packaged templates 与 `examples/` 中的 11 个 requirement 模板逐字一致，且
全部通过真实 `parse_requirement_text()` 和 `render_config_payloads()`：

| 模板 | Workflow | Testbench/Corner | 策略或用途 |
|---|---|---|---|
| `opt_requirement.md` | optimize | 1 TB，source/nominal | OpenBox PRF-EIC |
| `opt_requirement.openbox_gp_eic.md` | optimize | 1 TB，source/nominal | OpenBox GP-EIC |
| `opt_requirement.turbo.md` | optimize | 1 TB，source/nominal | native TuRBO |
| `opt_requirement.multi_corner.md` | optimize | 1 TB，3 corners | OpenBox PRF-EIC |
| `opt_requirement.multi_testbench.md` | optimize | 3 TB，source | 显式 OpenBox auto |
| `opt_requirement.multi_tb_corner.md` | optimize | 3 TB，3 corners | OpenBox PRF-EIC |
| `opt_requirement.history_warm_start.md` | optimize | 3 TB，source | OpenBox history warm start |
| `opt_requirement.history_warm_start.multi_corner.md` | optimize | 1 TB，multi-corner | OpenBox history warm start |
| `opt_requirement.fix_run.md` | fix_run | 1 TB×15 corners×1 point | waveform-only |
| `opt_requirement.fix_run.metrics_only.md` | fix_run | 1 TB×multiple points | metrics-only |
| `opt_requirement.fix_run.multi_testbench.metrics_waveform.md` | fix_run | multi-TB×multiple points | Metrics+Waveform |

模板矩阵补齐了原审计确认缺失的 GP-EIC、TuRBO、single-TB multi-corner warm start、
metrics-only、Metrics+Waveform、multi-testbench 和多 fixed-point 组合。模板不是所有
组合的笛卡尔积；它们是覆盖每一种有独立语义的能力边界的最小官方示例集。

### 6.3 Requirement 缺口的当前处理状态

1. `WorkflowSettings` 已接入 intake/doctor 与 on-disk validator；未知 mode 和非法
   `starting_run_id` 在仿真前失败。
2. section 现在按 workflow 严格适用：optimize 禁止 Fixed Points/Waveform Exports，
   fix-run 禁止 Objective/Constraints/Optimizer/History Warm Start；不再解析后忽略。
3. single-TB 的 Metric/Waveform route 必须省略；multi-TB 必须提供并命中 Maestro
   testbench ID。
4. 每个 fixed point 在仿真前检查完整参数集合、bounds、step grid、unit、candidate ID
   唯一性和 `real_NNN` 范围。
5. Objective intake 与 runtime 共用同一实现，支持算术（含 `%`）、`min`、`max` 和
   `ln`；未实现的 `sqrt/log/log10/exp/pow/abs` 不再被 intake 虚假接受。
6. 已选 section 的未知字段、拼写错误和未知 H2 section 全部 fail closed；重新生成
   config 时还会删除本次 requirement 未声明的旧 managed config，避免旧模式残留。
7. optimize 明确禁止无效的 `Workflow.starting_run_id`；fix-run 则用它生成连续 run ID，
   并预检点数是否会越过 `real_999`。
8. Constraint 阈值必须为有限数值并携带与 Metric 精确一致的单位；两个 backend
   不再把 `9 Hz` 对 `dB` Metric 解析成无量纲 `9.0`。
9. `Metric.result` 在 preflight 校验为安全 OCEAN selector；waveform name 唯一、
   expression 非空，当前唯一真实支持的 nil policy 是 `fail`。
10. `ProcessCorner.model_file` 必须精确命中一个 include；0 次或多次匹配均失败。
    每个 testbench 使用自己的 source corner，nominal 聚合必须有 `id: nominal`。
11. `required_signals` 的真实边界明确为 provenance 和 History Warm Start 兼容性元数据，
    不是仿真前 PSF 信号存在性探针；文档不再把它描述成尚未实现的运行时保证。
12. fix-run 的 `keep_successful_runs`/`keep_failed_runs` 现在对每个 fixed point 真正执行；
    Remote 同时保留 Remote 与 Controller snapshot 的 retention evidence。

## 7. TuRBO continuation 能力缺口（原审计，第三批已修复）

Native TuRBO 的首次 local/remote real run 有真实实现。问题在 continuation：

- native 初跑写 `reports/native_turbo_optimizer_evaluations.jsonl`；
- local continuation 固定调用 OpenBox；
- remote continuation 固定要求 `reports/optimizer_evaluations.jsonl` 并调用 OpenBox；
- native runner 没有 additional-evals、恢复 TuRBO state 或 prior traces 的接口；
- History Warm Start 只被 OpenBox 消费，与 TuRBO 组合时会被静默忽略。

该缺口不能只靠兼容历史文件名修复。第三批最终选择实现真实 native continuation：
local/Remote 按 backend 分派，从累计 trace 重建 active trust region，校验历史和
编号，并只追加用户请求的 evaluations；详细实现和验收边界见第 15 节。

## 8. CLI 完整核对

项目有两个 console entrypoint：

- `hermes-workflow`：36 个子命令；
- `ic-opt`：一个产品级单命令入口。

总计 37 条可达 CLI route。原审计中的 33 条完整、3 条部分有效、1 条必然失败已
在第三批收敛为 37 条均有真实作用、0 条必然失败、0 条纯 stub；显式 fake/mock
命令属于诊断能力，不是空实现。

| # | 命令 | 判定 | 实际作用或问题 |
|---:|---|---|---|
| 1 | `check-toolchain-env` | 有效 | 生成环境报告，默认使用当前执行环境，可显式覆盖 venv |
| 2 | `init` | 有效 | 创建项目模板 |
| 3 | `validate` | 有效 | 校验配置合同 |
| 4 | `prepare-netlist` | 有效 | 生成 netlist 模板与报告 |
| 5 | `check-requirement` | 有效 | requirement intake/report |
| 6 | `prepare-from-requirement` | 有效 | 生成配置并导入 Maestro netlist |
| 7 | `check-project-ready` | 有效 | readiness gate |
| 8 | `dry-run` | 有效 | 生成 dry candidate/report |
| 9 | `preflight-health` | 有效 | 生成健康状态 |
| 10 | `package` | 有效 | 生成 execution package |
| 11 | `package-optimizer-task` | 有效 | 生成可搬运任务包，支持 OpenBox/Native continuation |
| 12 | `approve` | 有效 | 写审批状态 |
| 13 | `prepare-real-run` | 有效 | 生成首次 real run package |
| 14 | `prepare-next-real-run` | 有效 | 生成下一候选 |
| 15 | `prepare-candidate-real-run` | 有效 | 生成显式候选 |
| 16 | `suggest-candidate` | 有效 | 根据状态/ledger 建议候选 |
| 17 | `assess-real-run-recovery` | 有效 | 分类恢复动作 |
| 18 | `prepare-real-run-retry` | 有效 | 生成重试 package |
| 19 | `resolve-real-run-failure` | 有效 | 决定故障恢复 |
| 20 | `check-real-run` | 有效 | 检查 result manifest |
| 21 | `check-metric-results` | 有效 | 检查 OCEAN metrics |
| 22 | `check-optimizer-run` | 有效 | 运行验收检查 |
| 23 | `summarize-optimizer-run` | 有效 | 完成总结 |
| 24 | `visualize-optimizer-run` | 有效 | 生成图和报告 |
| 25 | `decide-optimizer-run` | 有效 | 生成推荐 |
| 26 | `record-optimizer-decision` | 有效 | 保存 supervisor decision |
| 27 | `write-optimizer-final-summary` | 有效 | 生成最终 JSON/Markdown |
| 28 | `finalize-optimizer-run` | 有效但重复 | 聚合前述步骤，部分步骤被外层 flow 再调用 |
| 29 | `optimizer-status` | 有效 | 读取状态报告 |
| 30 | `optimize` | 有效 | 完整 local orchestration |
| 31 | `run-openbox-fake` | 有效诊断命令 | 显式 fake，不是 stub |
| 32 | `run-openbox-real` | 有效 | OpenBox real |
| 33 | `continue-openbox-real` | 有效 | 要求并转发 `--additional-evals N` |
| 34 | `record-real-result` | 有效 | 写 ledger/state |
| 35 | `mock-run` | 有效诊断命令 | 显式 mock，不是 stub |
| 36 | `run-native-turbo` | 有效 | Native TuRBO 初始运行 |
| 37 | `ic-opt` | 有效 | 产品级 local/Remote、optimize/fix-run 与 backend 分派入口 |

原 CLI 问题已按第三批契约修复：冲突 flags 先于 I/O fail early，fix-run 无
`--real` 不再空 pass，continuation 不再固定 OpenBox，任务包不再嵌入开发机 `/tmp`
路径。低层命令的完整参考见 `docs/TOOLCHAIN_EXECUTION_REFERENCE.md`；产品用户仍应
优先使用 `ic-opt`，避免把低层原语误认为独立产品流程。

## 9. 为什么 1368 个测试没有发现这些问题

绿灯测试覆盖的是现有测试合同，不是所有真实工程状态。已确认的盲区包括：

1. Remote adapter 的 FakeRunner 只记录 upload；download 时总能临时生成新指标，
   不模拟持久远端旧目录。
2. Run retention 测试只覆盖返回码 0 和 1，没有 255、126、127 或权限错误。
3. Tree transfer 的 FakePipe 不产生大 stderr，不会阻塞。
4. Remote native audit 测试 stub 掉真实 runner，再手写期待的 `remote` JSON。
5. CLI continuation 测试 monkeypatch 掉 backend，甚至固定断言
   `additional_evals is None`。
6. 没有“native 初跑完成后再 native continuation”的端到端测试。
7. 既有 100 次 Remote 验收使用 bash 账号，且没有构造 Controller Cache fresh、
   Remote run persistent 的第二轮非 continuation 场景。
8. 既有 symlink 验收覆盖了普通文件 symlink，但当时没有目录 symlink；同理，单一
   fixture 不能证明所有合法 Maestro 结构。

## 10. Fable 5 对原审计的修正和增强

以下内容作为最终口径覆盖原审计中不够精确的表述：

1. Native remote audit 的根因定位到 `NativeTurboBatchRunner.run()` 遗漏参数，而
   不是构造器没有保存参数。
2. `/tmp` 泄漏的直接影响范围限定为 `check-toolchain-env` 默认行为和
   `package-optimizer-task` 输出；`ic-opt` 产品 doctor 使用 `sys.prefix`。
3. “模板逐字一致”限定为三个位置共有的 9 个文件；`examples/` 不是完整脚手架。
4. tcsh 是局部没有复用正确 shell 模式，不是项目完全没有 csh 意识。
5. 旧指标污染的主要触发条件是同一 Remote 项目上的第二次 fresh、非 continuation
   运行，而不是所有 Remote 运行无条件发生。
6. Metrics、dry flag、corner manifest 和 dead continuation 的实际影响比原报告
   更严重，按本台账中的复现结果执行。

## 11. 修复批次

### 11.0 原待修清单与当前状态对比

本表以第 2～9 节的原始审计结论为基准。它不是只列“本轮想改什么”，而是明确
区分已经有代码与验收证据的项目、本轮正在处理的项目，以及仍不得遗忘的后续项。

| 原待修问题组 | 当前状态 | 后续 TODO |
| --- | --- | --- |
| Remote fresh run 复用旧目录/旧指标 | 已修复并完成隔离文件系统 100 次验收 | 保留回归 |
| Fix-run `Metrics` 被丢弃 | 已修复，metrics-only/waveform-only/组合均有契约 | 保留回归 |
| Corner override 无命中仍 pass、multi-TB 误用主 TB corner | 已修复并完成 900 个 child 真实验收 | 保留回归 |
| Remote optimize/fix-run 旧成功报告继续生效 | 已修复，attempt 开始即归档 | 保留回归 |
| Remote shell、SSH 返回码、并发、传输、doctor、snapshot | 已完成第二批修复与真实 Remote 验收 | 保留回归 |
| `--dry-orchestration` 在不支持路径被静默忽略 | 已修：仅 local first-run optimize + `--real` 可用，其余组合 fail early | 保留 CLI 组合回归 |
| Fix-run 不带 `--real` 写空 `pass` | 已修：产品 CLI 和 public flow 双层拒绝，不再写空成功报告 | 保留 local/remote 回归 |
| `continue-openbox-real` 永远缺少 `additional_evals` | 已修：`--additional-evals N` 必填且最小为 1 | 保留低层 CLI/任务包回归 |
| Native TuRBO 初跑后 local/remote continuation 不可用 | 已修：按 backend 分派、严格恢复 trace、只追加请求次数 | 完成 Native Remote 真实 EDA continuation 验收 |
| History Warm Start 与 TuRBO 组合被静默忽略 | 已修：enabled warm-start 仅允许 optimize+OpenBox，fix-run/native/continuation fail early | 保留 intake/project/package 三入口回归 |
| `check-toolchain-env`/任务包硬编码开发机 `/tmp` venv | 已修：运行时默认 `sys.prefix`，portable package 默认不烘焙打包机路径 | 保留显式 venv override 回归 |
| Native remote effectiveness audit 把 transport 写成 local | 已修：真实 batch runner 传递 `transport_mode` | 完成 Native Remote 真实报告核验 |
| Constraint 单位未与 metric 单位比对 | 已修：finite threshold + Metric.unit 精确匹配 | 保留 intake/on-disk/backend 回归 |
| Workflow/unknown key/fixed-point/objective validator 等 intake 缺口 | 已完成 Requirement 科学语义批次 | 保留 parse/render/validate/real-run 同源契约回归 |
| Requirement 模板组合缺失 | 已由 6 个扩展为 11 个，覆盖所有独立能力边界 | 新能力加入时同步矩阵 |
| 文档版本与部分能力说明漂移 | 已同步 0.1.10、CLI、continuation、toolchain 与 Requirement 语义 | 保持源码/模板/说明三者同步 |

第三批完成后必须回填本表和下面复选框；“写了实现”不等于完成，只有公共入口红绿
测试、local/remote 能力矩阵和全量回归均通过后才允许标记 `[x]`。

### 第一批：结果可信度

- [x] Remote candidate run 目录隔离与结果新鲜度
- [x] Fix-run Metrics 提取、渲染与三种组合行为
- [x] Corner override 命中验证和 per-testbench base corner
- [x] 新 Remote optimize/fix-run attempt 使旧成功报告失效
- [x] 把 Fable scratchpad 的关键症状转成仓库内回归测试
- [x] Constraint 单位验证——第一批暂缓，后续 Requirement 科学语义批次完成

### 第二批：Remote 环境兼容与可靠性

- [x] 明确 Remote command shell
- [x] attempt lock
- [x] Doctor 分离检查 Spectre/OCEAN
- [x] Retention 严格区分 0/1 与 transport/command failure
- [x] Tree transfer timeout、管道安全和 staging/atomic replace
- [x] Doctor 覆盖真实工具依赖
- [x] Snapshot retention/GC
- [x] Native remote effectiveness audit 正确记录 transport

### 第三批：CLI 和能力声明

- [x] Fix-run 无 `--real` 不得空 pass
- [x] `--dry-orchestration` 只在支持路径执行，其他组合 fail early
- [x] CLI 互斥参数组合明确拒绝
- [x] 修复 `continue-openbox-real` 死命令并要求明确追加预算
- [x] 实现 local/remote native TuRBO continuation
- [x] History Warm Start 对 native/fix-run/continuation fail early
- [x] 移除开发机 `/tmp` venv 默认值
- [x] 同步本轮 CLI、continuation、toolchain 和 0.1.10 说明
- [x] Requirement 语义和模板能力漂移由后续独立批次修复

### Requirement 科学语义批次

- [x] WorkflowSettings 接入 intake/doctor/on-disk validator，未知 mode fail early
- [x] workflow/section applicability，禁止解析后静默忽略
- [x] unknown section/field/spelling fail closed，生成配置收敛并清除 stale managed config
- [x] Metric/Waveform testbench route 与 Maestro IDs 交叉校验
- [x] Fixed-point bounds、step、unit、完整参数、ID 和 run range 预检
- [x] Objective intake/runtime 共用同一函数与运算符白名单
- [x] Constraint finite threshold 和 Metric.unit 精确匹配
- [x] Corner replacement/model include/per-testbench base corner/nominal policy 校验
- [x] Metric.result、required_signals、nil-policy 与真实实现边界写入文档
- [x] Fix-run retention 字段接入真实 local/Remote flow
- [x] 官方 requirement 模板由 6 个补齐为 11 个并逐一 parse/render

### 第四批：真实工程验收

- [x] Controller 无法直接访问本次验收的 Remote-owned project/Maestro Path
- [x] Remote Host 预置旧 run，Controller Cache fresh 后再次运行
- [ ] bash 和 tcsh Remote 账号
- [ ] 缺少单个 EDA/tool/transfer dependency
- [ ] SSH 255、权限错误、命令不存在和传输中断
- [x] 两个 Controller 竞争同一 Remote 项目
- [ ] single/multi testbench × source/multi corner
- [ ] optimize 与 fix-run，Metrics 与 Waveform
- [ ] OpenBox GP-EIC、PRF-EIC 和 native TuRBO
- [x] 至少 100 次真实优化评估，并核验 parent/child manifests、指标、新鲜度、
  optimizer state、best candidate 或 none-feasible 结论、最终报告和
  Remote/Controller checksum

## 12. 第一批完成标准

第一批不能以“相关单元测试通过”作为完成标准，必须同时满足：

1. 每个缺陷都有先红后绿的公共接口回归测试；
2. Remote 持久状态测试证明旧 run 文件不能进入新 candidate；
3. metrics-only、waveform-only、Metrics+Waveform 三种 fix-run requirement 都有明确
   行为；
4. corner 拼写错误 fail closed，multi-testbench 使用各自 base corner；
5. 新 optimize/fix-run attempt 开始后，旧 pass marker 不再代表当前 attempt；
6. 定向测试、全量 `pytest`、`ruff check src tests` 和 `git diff --check` 全部通过；
7. 版本号保持不变，除非维护者另行决定；
8. 不修改本批明确暂缓的 constraint 单位逻辑。

## 13. 第一批实施记录

实施日期：2026-08-10。

### 13.1 红色证据

1. 持久 Remote 目录预放旧 `ocean_scalars.tsv`，本轮不产 scalar：修复前
   adapter 返回 `succeeded`，测试期望 `failed`。
2. Fix-run metrics-only requirement：修复前返回
   `fix_run mode requires at least one of Metrics or Waveform Exports`。
3. Corner 变量拼写为 `temperatur`：修复前 `prepare_netlist` 返回 `pass`。
4. Remote attempt 开始：修复前只发出一条 optimize marker 归档命令，测试要求
   optimize 与 fix-run 两条。
5. 直接调用 Remote fix-run 且 doctor 立即失败：修复前没有先发出 fix marker
   归档命令。

### 13.2 实施结果

- Candidate run 的 Remote tree 上传使用显式 `replace=True`，只清理精确的
  candidate/testbench/corner 目录；snapshot、reports 等其他 tree upload 保持原
  overlay 行为。
- Remote tree replacement 拒绝根目录、相对路径和包含 `..` 的目标。
- Fix-run 将 `Metrics` 作为 mode-specific optional section 提取；objective 在
  fix-run 可缺省，但 optimize 项目验证仍强制要求 objective。
- Corner `model_section`、`model_file` 和 variables 都检查真实替换次数；未命中
  fail closed。
- Multi-testbench corner 渲染读取当前 named testbench 的 source corner，不再
  统一使用 primary testbench corner。
- Product Remote attempt 在 doctor 之前归档 optimize/fix-run 两种 active marker；
  直接调用 Remote fix-run API 也有相同保护。
- Constraint 数值单位逻辑没有修改。

### 13.3 本地验证

```text
关联测试：311 passed
全量测试：1376 passed, 13 warnings
Ruff：No issues found
git diff --check：pass
```

13 条 warning 均为既有 matplotlib/pyparsing deprecation warning。全量测试相对
审计基线增加 8 条回归测试。

### 13.4 隔离 Remote 真实工程验收

验收日期：2026-08-10。

#### 验收环境

- 验收输入来自维护者指定的
  `/home/zzchen/remote_opt/Mixer_CS_validation_b09_remote10_20260614_050335`；
- 使用真实 OpenSSH、Spectre X、OCEAN、OpenBox PRF-EIC；
- 3 个 testbench × 3 个 process corner × 100 个候选，共 900 个真实子仿真；
- 候选并行度 10、batch size 10、每个 Spectre run 10 threads；
- Remote project 和 Maestro point 位于独立 mount namespace 的 32 GiB tmpfs；
- Controller 对 Remote `opt_requirement.md` 执行存在性检查为 false，Remote 通过
  SSH 对同一路径检查为 true；没有用共享路径冒充隔离 Remote；
- 临时 OpenSSH profile 只通过进程级 `-F` 配置注入，主机密钥记录位于临时目录，
  没有修改或弱化用户永久 `~/.ssh/config`。

#### 失败工况也按真实结果保留

第一次 100 次运行使用已替代原 `Interactive.12` 的当前 P1dB
`Interactive.21`。该点的 `ade_e.scs` 在当前 Spectre 下报加密数据无法解密；流程
完整跑到 100 条 history 后以
`optimizer report completed but no result manifests succeeded` fail closed。该轮只
证明失败证据可信，不能作为优化功能通过。

随后改用指定旧验证包中保存、且曾成功运行的三套 exported netlist。一次 8 GiB
隔离 tmpfs 试跑在产物写满后由 scp/tar 明确报 `No space left on device` 并退出 1，
没有被当成成功。该次不计入最终验收。

最终重新建立 32 GiB Remote-only mount，从空 Controller Cache 开始，并在 Remote
预置：

- `real_001` 到 `real_100`；
- 每个 run 的 9 个 testbench/corner 子目录，共 900 个
  `stale_overlay_sentinel` 和旧 `ocean_scalars.tsv`；
- 旧 `optimizer_flow_run_report.json` 和 `fix_run_report.json`，内容带
  `STALE_DO_NOT_PUBLISH` 标记且状态为 pass。

Doctor 对 100 个预置父目录均给出 `INCOMPLETE_REAL_RUN` warning，但 requirement、
EDA 环境和 Remote 模式通过。随后 production `ic-opt --ssh-profile ... --real`
完成并退出 0。

#### 最终交叉审计结果

```text
候选 history                          100
唯一 run_id                           100（real_001..real_100）
唯一候选参数                          100
父 result_manifest                    100/100 succeeded
子 result_manifest                    900/900 succeeded
子 metric_result_manifest             900/900 exists
corner input.scs                      900/900 exists
section/temperature 错误              0
每个 run/testbench 的三 corner 异 hash 300/300
Controller/Remote 关键 artifact        2200/2200，SHA-256 mismatch=0
本地 stale child sentinel             0
Remote stale child sentinel           0
flow status                           pass
optimizer status                      completed
acceptance status                     accepted
旧 optimize pass marker               已归档到 previous
旧 fix-run pass marker                已归档到 previous
active fix-run marker                 不存在
active optimizer marker 含旧标记       false
```

100 个父仿真结果全部成功。Optimizer history 中 48 个候选得到完整聚合 metrics 后因
工程约束失败，52 个因 metric check 失败；原指定验证包的 10 次历史分布为 7 个
constraint failure、3 个 metric-check failure，失败类型一致。最终报告没有把这些
候选伪装为 feasible best point，但 OpenBox 完成 100 个 observation 的模型与报告
流程，`optimizer_run_acceptance_report.status=accepted`。

以上验收直接证明本批修复的 Remote 子 run 替换、新鲜度、corner 渲染、旧 marker
失效、结果同步与 checksum 行为。它不代表第四批所有矩阵已经完成；tcsh、依赖
缺失、SSH 255、双 Controller 竞争、fix-run waveform 真实 E2E、GP-EIC 和 native
TuRBO 等仍按第 11 节保留为后续验收项。

## 14. 第二批实施记录：Remote 环境兼容与可靠性

实施与验收日期：2026-08-10。

本批严格限于维护者指定的六类 Remote 兼容问题：明确 shell、SSH 返回码分类、
attempt lock、传输超时与完整树发布、doctor 依赖、snapshot 清理。Native TuRBO
continuation、native effectiveness audit、CLI 能力声明和 constraint 单位仍保留在后续
批次，没有借本批扩展修改。

### 14.1 Shell 与返回码

- `RemoteSshRunner` 不再把工作流 POSIX 脚本裸交给 Remote 账号的登录 shell，而是
  生成 `exec /bin/sh -c <quoted-command>`。只有 doctor 建立 SSH 与 `/bin/sh`
  可用性的两条 bootstrap probe 使用简单登录-shell 命令。真实 `csh -fc` 回归证明包含
  `if ...; then ...; fi` 的 payload 可以在 tcsh/csh 登录账号下进入 `/bin/sh` 执行。
- 路径 probe 只接受 `0=存在`、`1=不存在`。`255` 抛出 transport error，
  `126/127` 抛出 command unavailable，其他返回码是 remote command error。
- Requirement、history、doctor dirty-state、progress 和 run retention 的路径检查复用
  同一分类，不再把 SSH 255 写成 `missing`。

### 14.2 Attempt lock

- Product `--ssh-profile ... --real` 和 `--continue` 在 doctor/归档之前用 Remote
  `mkdir` 原子获取 `state/remote_attempt.lock`，整个 attempt 完成或异常后才释放。
- 锁保存随机 token、Controller hostname/PID、profile、Remote project 和 UTC 时间；
  第二个 Controller fail fast，并显示 `owner.json`。
- 释放前核对 token，不允许一个 Controller 删除另一个 Controller 的锁；不自动偷取
  陈旧锁，避免把仍在工作的真实仿真误杀。

### 14.3 传输超时与完整树发布

- File/tree transfer 默认超时 1800 秒，超时统一报
  `RemoteCommandTimeoutError`。
- 删除原先两个 `Popen` 管道互相等待的实现；tree transfer 先在与 Controller
  source/target 相同文件系统创建临时 tar，再执行有 deadline 的 Remote 或 local
  步骤，stderr 不再可能填满管道造成永久等待。
- 下载先解到 Controller staging；上传先解到 Remote sibling staging。完整 staging
  通过 rename 发布，旧目标先移到唯一 backup，发布失败时恢复旧目标。
- `replace=True` 仍只用于 candidate/child run 这类必须清空旧文件的目标；普通 overlay
  先 `cp -a` 旧树到 staging 再叠加新内容。任何路径都不会边传边暴露半棵新树。
- 单文件下载先写同目录临时文件再 `replace`；单文件上传继续使用 Remote 临时文件再
  `mv`。临时 staging/backup 有明确清理。

### 14.4 Doctor 真实依赖

Doctor 新增并持久化以下独立检查：

- Controller：`ssh`、`scp`、`tar`；
- Remote：可执行 `/bin/sh`、`tar`、`readlink -e`、`stat -Lc`、`sha256sum`；
- Remote staged publication：真实执行 `mkdir`、`cp -a`、`mv -T`、`rm` 并核对文件；
- Cadence：`spectre` 与 `ocean` 分成两条 csh 检查，不再由最后一条 `which` 的返回码
  代表两个工具。

### 14.5 Snapshot retention

- Snapshot ID 增加 UTC 可排序前缀。
- canonical symlink 成功切换后才执行 GC。
- `state/remote_preparation_snapshots` 最多保留 3 个目录；当前 canonical target 永不
  删除，旧的 legacy/random ID 也会被纳入数量上限。
- GC 失败会使 prepare fail closed，不能在宣称成功时继续无限增长。

### 14.6 红色与本地回归证据

修复前或旧测试契约的关键红色表现包括：

1. raw Remote 命令与 cwd 断言没有 `/bin/sh` 包装；真实 csh 无法解析 POSIX 脚本；
2. retention 的 SSH 255 被写成 `remote_action=missing`；
3. 第二个 Controller 可进入同一 Remote project；
4. tree transfer 依赖互锁管道、没有 deadline，并直接覆盖 active target；
5. doctor 不检查 Controller transfer 工具和 Remote coreutils，Spectre/OCEAN 合并
   检查；
6. 连续 snapshot 永不删除。

最终本地证据：

```text
第二批 Remote 定向测试：234 passed, 13 warnings
全量测试：1382 passed, 13 warnings
Ruff：No issues found
git diff --check：pass
```

13 条 warning 仍为既有 matplotlib/pyparsing deprecation warning。版本保持
`0.1.10`。

### 14.7 真实 Remote 100-candidate 工程验收

维护者指定的原始项目
`/home/zzchen/remote_opt/Mixer_CS_validation_b09_remote10_20260614_050335`
首先按原样运行 doctor。新增的 Controller/Remote dependencies、Spectre 和 OCEAN
全部通过，但 requirement 因其记录的旧 `Interactive.12/.../Mixer_CS_P1dB` 已被清理
而正确 fail closed。没有篡改这一历史证据包。

随后创建独立 Remote 验收副本：

```text
/home/zzchen/remote_opt/Mixer_CS_validation_second_batch_20260810
```

副本沿用指定包保存且上一轮已完成真实验证的三套 exported netlist，构造成三个
Remote-owned Maestro source root；优化规模改为 100 candidates，保持
3 testbenches × 3 corners、batch 10、candidate parallelism 10。Remote 账号实际
登录 shell 为 bash；tcsh/csh 兼容由前述真实解释器回归覆盖。第一批隔离 mount
namespace 的 100-candidate 验收继续作为 Controller/Remote 文件系统隔离证据，本轮
重点验证新 transport、lock、doctor 和 snapshot 行为。

真实行为证据：

- doctor：新增的 11 项 Controller/Remote/Cadence 能力全部 pass；
- 双 Controller：先持有真实 Remote lock，再启动第二个 `ic-opt --real`，第二个进程
  exit 1，并打印第一持有者的 hostname、PID、UTC 时间和 token；释放后正式流程可
  正常启动；
- snapshot：正式运行前预置 5 个旧 snapshot，运行发布 1 个新 snapshot 后目录总数
  为 3，canonical 指向本次新 snapshot；
- 正式 `--real`：退出 0，最终 active flow report 为 pass，attempt lock 已释放；
- transfer：项目中遗留 `.upload-*`、`.backup-*`、`.download-*` 目录为 0。

终态数据：

```text
Optimizer history rows                 100
唯一 run_id                            100
唯一候选参数                           100
父 result_manifest                     100
子 result_manifest                     900
父+子 metric_result_manifest           1000
history status                         52 metric_check_failed
                                       48 constraint_failed
optimizer_flow_run_report              pass
optimizer_run_report                   completed
optimizer_run_acceptance_report        accepted
optimizer_completion_report            pass
Remote snapshot directories            3
Remote attempt lock                     absent
Remote transfer staging leftovers       0
Controller/Remote artifact inventory    2000 lines each
两侧 inventory 文件 SHA-256             b3ade550fa793eb9f4d9aad9b8fc34a6
                                       28553931e98206ad08ca48893e3b460a
Controller sha256sum -c                  pass
Remote sha256sum -c                      pass
```

这轮 100-candidate 验收没有把“无 feasible candidate”误写成优化失败：100 个 parent
与 900 个 child 仿真均完成，52/48 的失败分类与第一批同输入验收完全一致；最终
acceptance 为 accepted。它证明本批 transport/lock/snapshot/doctor 修改在真实
Spectre/OCEAN/OpenBox 工程负载下没有降低结果可信度。

## 15. 第三批实施记录：CLI 与优化器能力契约

实施完成日期：2026-08-11。版本保持 `0.1.10`。

### 15.1 CLI 行为边界

- `--dry-orchestration` 的唯一合法产品路径是 local、首次 optimize、同时给出
  `--real`。Remote、continuation、fix-run、缺少 `--real` 或与 doctor 组合都会在
  real backend、SSH、Cadence 环境解析或 flow 调用之前拒绝。
- fix-run 必须给出 `--real`。产品 CLI、local public flow 和 Remote public flow 都有
  防线，不再允许 `points: []` 的空成功报告。
- fix-run 与 `--continue` 明确报
  `--continue requires an optimize workflow`，不再误入 OpenBox history 检查。
- 低层 `continue-openbox-real` 要求 `--additional-evals N` 且 `N >= 1`，不再把
  `None` 传给必然拒绝它的 backend，也不再用 CLI 默认值覆盖项目 strategy。
- `package-optimizer-task` 同时支持 OpenBox 和 Native continuation。Native 任务调用
  产品入口 `ic-opt PROJECT --real --continue N`，由项目配置完成 backend 分派；四条
  后续审计命令显式携带 `--expected-backend`，避免旧 backend artifact 污染结论。
- standalone task package 在未写 `--backend` 时通过统一 strategy resolver 从项目
  algorithm/config 解析 backend；显式 `--backend` 是一致性断言，若与项目最终
  backend 不同则在写盘前拒绝，不能生成已知必失败的跨后端任务。
- optimizer task package 只适用于 optimize workflow；fix-run 在写入 task/manifest
  前明确拒绝。

### 15.2 Native TuRBO continuation

- local 与 Remote continuation 都从项目 optimizer config 解析 backend。OpenBox 仍走
  OpenBox continuation；Native 走 Native TuRBO，不允许隐式切换。
- Native continuation 加载 completed native report 和累计 JSONL，要求 evaluation
  index、run ID、参数、raw vector、phase 和 batch 结构一致。旧 sequential artifact
  若三个 batch 字段全部缺失，则按单点 batch 兼容；只缺一部分、batch phase 混合、
  slot 不完整或 batch ID 回退/复现都会 fail closed。
- continuation 从历史 trace 重建当前 trust-region 数据、length、success/failure
  counters，并从 trust-region 继续，而不是重新执行 Sobol/initial design。没有保存的
  NumPy/Torch/library RNG state 不会被虚假声称可恢复，报告明确记录
  `restore_mode: trace_reconstructed`。
- run、candidate 和 batch 编号同时考虑 accepted history、Controller 本地 orphan 和
  Remote inventory floor，失败 attempt 遗留的 `real_NNN` 不会造成下一轮 ID 重复。
- Native evaluations、effectiveness audit 和 run report 先完整 staging；发布中任一步
  失败会恢复三份旧文件，避免“新 JSONL + 旧 report”的跨代组合。
- Native batch runner 把真实 `transport_mode` 写入 CPU/thread effectiveness audit，
  Remote 不再被记录成 local。

### 15.3 后端产物选择与能力冲突

- acceptance、completion、finalize、insight、decision 和 progress-state 同步都能接收
  `expected_backend`。Native closeout 不再无条件优先读取遗留的 neutral OpenBox
  artifact；有 artifact 但没有任何一套匹配 backend 时明确 fail closed。
- fresh optimize 与 continuation 的五段 closeout 都传递本轮 execution backend；
  修复不只覆盖 `--continue`，首次/再次 fresh Native 运行也不会审到旧 OpenBox。
- legacy native-specific report 缺少新 `backend` 字段仍兼容；显式写成其他 backend
  则拒绝。
- enabled History Warm Start 只允许 optimize + OpenBox。Native、fix-run 以及和
  continuation 同时使用时，分别在 requirement intake、on-disk validation 或 task
  package 写盘前拒绝，不再静默忽略。
- `check-toolchain-env` 不再默认指向开发机
  `/tmp/ic_auto_opt_openbox_spike/.venv`，而是使用当前 `hermes-workflow` 所在的
  `sys.prefix`。portable task package 默认不记录打包机 venv；只有显式
  `--openbox-venv PATH` 才写入路径，且 Native backend 会拒绝该 OpenBox 专用参数。

### 15.4 红色证据

本批没有先放宽断言再改实现。关键红测包括：

1. dry flag 在 Remote/continuation/fix-run 路径仍调用 real service；fix-run 无
   `--real` 返回 `status: pass, points: []`。
2. `continue-openbox-real` 把 `additional_evals=None` 传入 backend，命令 100% 失败。
3. local/Remote continuation 固定走 OpenBox，只存在 native history 时查错文件。
4. Native task package直接拒绝 continuation；OpenBox warm-start + continuation 却能
   生成运行时必失败的任务。
5. fix-run 的非法 flag 在 Cadence 路径解析之后才判断；on-disk fix-run + enabled
   History Warm Start 被 project validator 假通过。
6. stale neutral OpenBox artifact 与有效 legacy native artifact 同时存在时，closeout
   读取 `real_099` 的旧 OpenBox 记录。
7. 旧 sequential native trace 因没有 batch metadata 被拒；损坏历史的 mixed phase、
   重复 slot 和回退 batch ID 未被检查。
8. orphan 只抬高 run ID，candidate/batch 仍复用旧编号；Native 三件套在第二或第三次
   replace 失败时形成混合代际。
9. 默认执行 `check-toolchain-env` 查找开发机 `/tmp` venv 并退出 1。
10. continuation 已传 backend，但 fresh optimize 的五段 closeout 未传；consumer 要求
    `expected_backend` 的红测在第一段 check 即失败。
11. standalone task package 对 implicit OpenBox 和 random 配置仍生成 Native manifest；
    显式选择与项目冲突的 backend 还能生成运行时必失败的 continuation task。

对应 TDD 运行分别观察到 CLI/flow、任务包、Native history 和 artifact selection 的
真实失败；修复后全部转绿。具体分组红测包含 `3 failed`（Native task package/
warm-start）、`4 failed`（fix-run validation/提前拒绝）、`7 failed, 1 passed`
（Native 历史完整性）以及 `4 failed`（backend artifact 选择/透传）。这些分组是不同
测试集合，不能简单相加成唯一缺陷数。最终补漏另观察到 `1 failed`（fresh closeout
backend）、`3 failed`（implicit OpenBox/random task package）和 `3 failed`（显式
backend mismatch）；全部已转绿。

### 15.5 本地与运行环境验证

```text
CLI/任务包/validation 定向矩阵        83 passed
Native TuRBO 完整测试文件             68 passed
artifact/closeout/任务包/Remote 矩阵  133 passed
默认 TuRBO 恢复与 Remote backend 链    5 passed
全量测试                              1442 passed, 13 warnings
Ruff                                  No issues found
git diff --check                      pass
check-toolchain-env 默认环境           pass
版本                                  0.1.10（未变）
```

默认 TuRBO 恢复测试真实构造历史 trust-region，首个追加 batch 直接进入
`turbo_trust_region`，并验证 success counter 回放后 length 从 `0.8` 增长到 `1.6`。
13 条 warning 仍为既有 matplotlib/pyparsing deprecation warning。

### 15.6 本批验收边界与剩余 TODO

本批没有启动新的 100-candidate Native Remote Spectre/OCEAN 工程运行，因此不能把
local default-TuRBO、持久 artifact 和 Remote adapter 测试写成“Native Remote 真实
EDA 已验收”。前两批已完成的 100-candidate OpenBox Remote 验收继续证明本批没有
破坏共有的 Remote transport/lock/snapshot 基础；以下项目仍属于第四批：

- Native TuRBO 在隔离文件系统上的真实 Remote 初跑 + continuation；
- OpenBox GP-EIC、PRF-EIC 与 Native TuRBO 的完整真实 backend 矩阵；
- Native Remote effectiveness audit 的真实报告字段核验；
- 第四批中尚未完成的 tcsh 账号、依赖缺失、SSH/传输故障和模式拓扑矩阵。

Constraint 单位和其他 Requirement 科学语义在第三批之后作为独立批次实现，详见
第 16 节；它们不属于第三批的原始完成范围，也没有被第三批的测试结果提前宣称
为已修复。

## 16. Requirement 科学语义与模板契约实施记录

实施完成日期：2026-08-11。版本保持 `0.1.10`。

### 16.1 单一真实合同

- Requirement raw section、渲染后的 config 与 real-run 不再维护三套互相漂移的
  规则。Workflow、变量网格、fixed point、measurement route、Objective 和
  Constraint 的公共 helper 被 intake 与 on-disk validator 共同调用。
- `write_config_payloads()` 采用收敛式 managed-config 发布：当前 Requirement 没有
  声明的旧 `optimizer.yaml`、`testbenches.yaml`、`history_warm_start.yaml`、Metrics、
  Waveform、Workflow 或 Fixed Points 配置会被移除，不能跨模式继续生效。
- 未知 H2 section、未知字段、拼写错误、无效 workflow/section 组合均在仿真前
  fail closed；renderer 不再通过 `.get(..., default)` 把错误拼写伪装成默认值。

### 16.2 科学语义

- Objective 的静态解析和运行时求值共用 `objective_contract.py`：支持算术运算
  （含 `%`）、`min`、`max`、`ln`，同时校验函数参数数量、未知符号和有限常数；
  metric-dependent domain/除零/非有限错误会把当前候选归类为失败并使用 failure penalty，
  不会中断整轮优化。
- Constraint threshold 必须是有限数值、空格和单位；单位与对应 Metric 精确一致。
- Fixed point 对每个 Design Variable 做完整覆盖、unit suffix、bounds、step grid 校验；
  candidate ID 唯一，起始 run ID 与点数不能越过 `real_999`。
- Metric/Waveform route 在 single/multi-testbench 场景下有相反且明确的合同；
  waveform name 唯一、expression 非空，并且 multi-TB 中每个声明的 testbench 都必须
  至少拥有一个 Metric 或 Waveform extraction；未实现的 `nil_policy: skip` 被拒绝而
  不是假装生效。
- `Metric.result` 使用安全 OCEAN selector；`required_signals` 明确只服务 provenance
  与 History Warm Start 兼容性，不冒充真实 PSF 探针。

### 16.3 Corner、优化器与 retention

- corner variable/model section 必须真实命中；`model_file` 必须是安全的绝对 POSIX
  路径且精确命中一个 include。Local 在 Controller、Remote 在 Remote host 以
  `test -f && test -r` 验证真实文件，SSH 传输错误不会被当成“不存在”；multi-TB
  使用各自 source corner，optimize nominal policy 要求 `id: nominal`。
- 固定 GP-EIC/PRF-EIC preset 与 nested advanced setting 冲突时失败；batch size 不得
  大于 parallel jobs，TuRBO 初始预算不得低于两倍维度。
- fix-run 的 corner aggregation policy 不再作为无消费者指令暴露；共享内部 config
  使用固定 nominal/nominal，但 fix-run 不据此宣称进行优化聚合。
- fix-run retention 对每个 fixed point 执行。Remote 先处理 Remote run，再处理已下载
  Controller snapshot，并在权威 completion marker 前同步 retention evidence。
- Remote optimize 的 retention 由 `record_real_result` 后的最终 observation 决定；
  record 失败时 Remote 与 Controller 都使用 failed policy，不能提前按 adapter success
  删除唯一远端证据。Fresh run 与 continuation、OpenBox 与 native TuRBO 使用同一回调。
- `history_warm_start.yaml` 已进入 execution package 与 immutable hash；批准后修改 warm
  start 来源或设置会使包校验失效。本地公开 optimize/optimizer 入口会在 doctor、
  prepare 或写报告前拒绝 fix-run 项目；Remote continuation 必须先恢复并验证 frozen
  snapshot 才能得知 mode，但会在启动 optimizer backend 前拒绝。

### 16.4 模板与红绿证据

官方模板由 6 个扩展为第 6.2 节列出的 11 个。自动测试固定完整的 11 文件集合，要求
两份模板目录逐字一致，并逐个执行真实 parse 与 mode-aware render；不能通过同时删除
同名模板来绕过集合检查。当前 11/11 通过，独立矩阵审计为 0 issue。

本批红测曾真实暴露以下失败：Workflow/FixedPoints 没进入 on-disk bundle、未知字段
被丢弃、single/multi-TB route 无效、fixed point 越界或错 unit 晚失败、Constraint
指数被正则错误回溯、Metric.result 不安全、corner include 多匹配、OpenBox preset
被 nested setting 改写、fix-run retention 字段没有消费者。修复后相关 Requirement、
flow、corner 和 optimizer 套件全部转绿。

### 16.5 验收边界与剩余 TODO

最终本地验证：

```text
Requirement/docs/coupling 定向测试   115 passed, 13 warnings
本批相关 Requirement/flow 矩阵       540 passed, 13 warnings
全量测试                              1568 passed, 13 warnings
Ruff                                  No issues found
git diff --check                      pass
版本                                  0.1.10（未变）
```

本批验证的是 Requirement → config → preflight/flow 的代码合同，没有启动新的
Spectre/OCEAN 真实工程运行。仍需按第 11 节第四批矩阵完成：

- Native TuRBO 隔离文件系统 Remote 初跑 + continuation；
- bash/tcsh 真实账号、缺依赖、SSH 255、权限错误和传输中断；
- single/multi-TB × source/multi-corner × optimize/fix-run × 三种 optimizer backend
  的真实工程组合验收。

## 17. Remote 剩余可靠性实施记录

实施完成日期：2026-08-11。版本保持 `0.1.10`。

### 17.1 Doctor dirty-state 返回码

- `test -f`/`test -d` 继续使用严格布尔语义：返回码 0 表示存在、1 表示不存在，
  126/127/255 等异常返回码必须失败。
- 已确认的遗漏位于 `runs/real` 枚举：旧实现只处理 `ls -1` 的返回码 0，把其他所有
  返回码静默当成“没有 incomplete run”，还用 `2>/dev/null` 丢弃诊断。
- 现在枚举命令也复用统一 Remote result classifier；任何非零返回码都 fail closed，
  命令、返回码和 stderr 中的真实诊断被保留。

### 17.2 Remote continuation 重新执行 Doctor

- 每个 Remote continuation attempt 都使用本次 attempt 的同一 SSH runner、profile、
  Cadence cshrc 和 cache root 执行一次 Doctor。
- 产品 CLI 的顺序固定为 attempt lock/archive → Doctor → frozen prepare → history sync
  → backend；direct API 自己调用时从 archive → Doctor 开始。Doctor fail、异常或
  workflow 非 `optimize` 时，后续三步都不会启动。
- 产品 CLI 已执行 Doctor 时，把同一个 report 传给 public continuation flow；direct API
  没有 report 时自行执行，因此一个 attempt 恰好检查一次，不会重复归档或重复 Doctor。
- Doctor 失败仍通过 `finally` 释放 token-owned attempt lock。

### 17.3 审计时间 provenance

- local/Remote fix-run 不再给 execution package 和 approval 写固定的
  `2026-06-01` 时间；它们复用现有 UTC clock，在真实调用窗口内生成 RFC3339 `Z`
  时间。
- 同类审查还发现 multi-testbench aggregate result manifest 固定写
  `2026-06-06T00:40:00Z`。该路径属于 local/Remote optimizer 聚合，不属于 fix-run，
  但同样会破坏 provenance，因此一并修复：聚合入口和 artifact 完成前分别采样当前
  UTC，真实写入 `started_at_utc` 与 `completed_at_utc`。
- 生产源码中已不存在硬编码 RFC3339 2026 时间戳。

### 17.4 红绿证据与能力边界

本批保留的红色证据包括：dirty-state listing 的 1/126/127/255 四种错误被假通过；
continuation 完全没有 Doctor、Doctor fail 后仍进入 frozen prepare、CLI 没有复用
Doctor report；local/Remote fix-run 和 aggregate manifest 的时间不在真实执行窗口。
修复后八个相关公开入口测试文件的合并定向矩阵为 `202 passed, 13 warnings`，
其中包含旧 Remote product CLI 和 local continuation 入口，确保测试不会绕开 Doctor、
误查 Controller 文件系统或意外发起真实 SSH。终审另补普通异常返回码 `rc=2` 和真实
UTC clock 时间窗回归。

最终全量测试为 `1590 passed, 13 warnings`；Ruff 为 `No issues found`，排除生成目录
后的 `git diff --check` 通过。`pyproject.toml`、`VERSION` 与 package
`__version__` 均仍为 `0.1.10`。

Slurm/LSF job ID、scheduler submission，以及 detach/reattach 后由新 Controller 进程接管
任务，统一归入未来可选的集群调度扩展，不属于当前核心产品的待修任务或发布阻断项。
当前 Remote 产品范围是 Controller 进程保持连接的 direct SSH execution；文档和验收
不得把 attempt lock 或 continuation 恢复误写成 scheduler job reattachment。

本批没有启动新的 Spectre/OCEAN 工程运行。Native TuRBO Remote continuation、tcsh
账号、依赖缺失、SSH 255、权限错误和传输中断的真实环境矩阵仍按第 11、15、16 节
保留为工程验收 TODO。

## 18. 核心 release 收尾状态

收尾日期：2026-08-11。Slurm/LSF submission、scheduler job ID 和
detach/reattach 已从当前 release 完成门槛中移除，统一作为未来可选集群扩展。

### 18.1 开发包与发行 checkout 同步

- 权威开发包：`/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow`
- 拥有 `origin/main` 的发行 checkout：
  `/home/zzchen/Agent_virtuoso/EDA_AI_AGENT/ic-auto-opt-workflow-v0.1`
- 同步前 checksum 审计确认发行 checkout 有 112 个功能文件陈旧或缺失：root 3、
  docs 6、examples 13、skills 1、src 55、tests 34。
- 已按白名单同步源码、测试、11 个 requirement 模板、用户文档、skill、README、
  v0.1.10 release notes 和本维护台账。排除 `.git`、vendor、build、dist、graphify、
  `.remember`、egg-info、Python/test/lint cache；同步后功能文件 checksum 差异为 0。
- 发行 checkout 中历史遗留的空误名目录 `"vendor/` 以及本次验证产生的 build、
  egg-info 和 cache 已清理；真实 `vendor/` 依赖快照未修改。

### 18.2 发行 checkout 独立验证

- 从发行目录固定导入其自身 `src/hermes_workflow`，全量测试：
  `1590 passed, 13 warnings`。
- Release checklist 的 requirement/docs/coupling 矩阵：
  `82 passed, 13 warnings`。
- Ruff：pass；`git diff --check`：pass；三个版本源均为 `0.1.10`。
- 离线 wheel 构建成功：`ic_auto_opt_workflow-0.1.10-py3-none-any.whl`；从 wheel
  导入路径、版本、11 个 packaged requirement templates 和 `ic-opt --help` smoke
  均通过。临时验证目录随后删除。

### 18.3 尚未闭合的核心发布项

1. Native TuRBO Remote continuation 已作为正式功能写入 README/Release Notes，仍需
   一轮真实隔离文件系统 EDA 初跑与 continuation 验收；否则必须降低该功能声明。
2. 发行 checkout 当前只是已同步、已验收的工作树，尚未 commit/push；GitHub main
   因此仍不包含本轮修复。
3. 现有 `v0.1.10` tag/Release 指向更旧提交；在版本号保持不变的前提下，最终发布
   需要维护者明确授权重建 tag 和 Release artifact。仅更新 main 不会改变旧 Release。

非阻断 P2 记账：Remote Doctor 的 runtime dependency probes 已经对所有非零返回码
fail closed，不会形成安全假通过；但 `_record_command_check()` 当前把 `rc=1/127`
（能力缺失）与 `rc=126/255`（命令执行或 SSH transport 异常）统一写成
`REMOTE_RUNTIME_DEPENDENCY_MISSING`，且 message 没有稳定携带 return code。这样会让
故障处置文案误导为“安装依赖”，而不是先恢复 SSH/远端命令执行。后续应复用统一
Remote return-code classifier，在不改变 fail-closed 结论的前提下区分 capability
missing 与 transport/execution failure，并在 structured diagnostic 中保留 rc/stderr。
该项是诊断准确性问题，不属于本轮 Native history/Doctor P1 修复范围。

收尾独立复核随后发现的两个代码 P1 记录在第 19 节；因此“未发现新的 P0/P1”只
适用于第 18 节当时的检查点，不再作为当前结论。未完成的 tcsh、依赖缺失、
SSH/权限/传输故障与完整模式笛卡尔矩阵继续作为非阻断工程验收，不得对外宣称已
全部覆盖。

## 19. 收尾独立复核追加 P1：backend artifact 与 Native history Doctor 合同

实施日期：2026-08-11。当前只在权威开发包完成 TDD 修复；为避免影响正在运行的
发行 Python，尚未同步发行 checkout、commit 或发布，版本仍为 `0.1.10`。

### 19.1 Random baseline 的实际 artifact backend

Requirement strategy resolver 对 `random_baseline` 返回 resolved backend
`random_baseline`，但实际执行复用 OpenBox backend，并写出
`backend: openbox` 的 backend-neutral report。旧 artifact selector 把前者当成未知
backend，导致 local/Remote Doctor 在已有合法 random baseline history 时错误失败。

修复在单一 artifact backend normalization seam 中把 `random_baseline` 映射为
OpenBox artifact contract；local Product Doctor 与 Remote Doctor 都通过公共 selector
生效，没有为 Doctor 单独增加特例。

### 19.2 Native Doctor 必须与 continuation loader 共用关键合同

旧 Doctor 只验证 report/JSONL 能读取和数量大致一致。一个 Native report 即使
`status` 不是 completed、`evaluations` 指向非 canonical 路径、
`evaluation_count` 不是严格整数，或者每行 trace 缺少 `run_id/raw_x/parameters/
objective` 等必要字段，也可能 Doctor pass，随后 continuation loader 立即失败。

修复把 Native report path、trace dataclass 和 artifact-level continuation validator
抽到无 workflow 依赖的 `native_turbo_history.py`。Native runtime loader 与 local/
Remote Doctor 现在共用同一份校验：schema version、completed status、backend、
canonical evaluations path、非空且无空行的 JSONL、每行必要字段和类型、连续
evaluation index、合法且唯一的 run ID、selection phase、raw vector、parameters、
finite objective、完整 batch metadata/分组，以及严格整数且与 JSONL 行数相等的
evaluation count。二次复核又发现 Doctor 没有把当前 Requirement 构造出的
`VariablesConfig` 传入 validator，因此变量维度、参数名集合和 raw vector 的 step
quantization 仍可能 Doctor pass、runtime fail。现在 local/Remote Doctor 与 runtime
loader 都调用同一个必传 `VariablesConfig` 的 history 入口；候选量化函数下沉到
共享 candidate contract，不再分别实现或在 Doctor 中复制近似检查。

Native 的 continuation canonical artifact 仍是
`reports/native_turbo_optimizer_report.json` 与
`reports/native_turbo_optimizer_evaluations.jsonl`。只把 Native payload 放进 OpenBox
使用的 neutral 路径不能通过 Doctor，避免 Doctor 选择一套 runtime 随后不会加载的
文件。完全 fresh、没有任何 history 的 Native 项目仍保持 pass 且不产生噪声。

### 19.3 红绿证据与当前边界

- Random baseline 的 Remote public-seam 红测先得到 `doctor.status == fail`，修复后
  local/Remote 两条回归均转绿。
- Native history 的首批 5 个 public Remote Doctor 红测（未完成 report、错误
  evaluations path、非整数 count、缺必要字段、非连续 index）修复前全部错误 pass；
  修复后扩展到 schema/backend、bool count、phase/type、raw_x、parameters、objective、
  batch 和 duplicate ID 共 17 个坏例，全部 fail closed。
- 二次复核新增 raw_x 维度、参数名集合和 raw_x/量化参数不一致三类语义坏例；修复前
  Remote 与 local Product Doctor 共 6 个用例全部未产生相应 artifact diagnostic，
  修复后六个均 fail closed。两侧合法 history fixture 也改为与真实 Requirement 一致
  的四变量 `FN/WN/FP/WP` trace，不再用单变量假正向掩盖问题。
- local Product Doctor 同时覆盖合法 Native continuation history pass 和损坏 trace
  schema fail；Native runtime 增加同三类语义漂移回归，73 条 continuation/runner
  测试保持通过。

最终开发包验证：相关 backend/Doctor/continuation/closeout 矩阵 `518 passed`；全量
`1630 passed, 13 warnings`；Ruff 和 `git diff --check` 均通过。13 条 warning 仍为
既有 matplotlib/pyparsing deprecation warning。本节修复在发行 checkout 同步和真实
Native Remote EDA continuation 验收完成前，不得对 GitHub Release 宣称已交付。

## 20. 收尾独立复核追加 P1：Doctor 必须检查实际 optimizer runtime

实施日期：2026-08-11。当前只修改权威开发包；没有同步发行 checkout、没有提交，
也没有读取或轮询正在运行的 Remote 验收工程。

### 20.1 根因与真实风险

旧 local Product Doctor 固定调用低层 `check_toolchain_environment()`，无论 Requirement
实际解析成 OpenBox、Native TuRBO 还是 fix-run，都只在另一个 Python executable 中
检查 `openbox` 和 `hermes_workflow.openbox_backend`。这同时有三个问题：

1. Native TuRBO 可以在缺少 `Turbo1`、PyTorch/GPyTorch 或线程控制依赖时 Doctor pass，
   直到真实 optimizer 启动才失败；Sobol 初始化所需的 SciPy 也没有被检查。
2. fix-run 根本不运行 optimizer，却被无条件要求安装 OpenBox。
3. Remote Doctor 只检查 Controller 的 `ssh/scp/tar` 和 Remote Host 的 shell/Coreutils/
   Cadence 工具，完全没有检查实际在 Controller 进程中运行的 optimizer Python runtime。

此外，旧低层探针通过指定 venv 的子 Python 导入 Hermes。在验收使用“dev venv Python +
发行 checkout `src`”的情况下，这可能检查到另一个 checkout，不能证明当前 `ic-opt`
进程随后真正 import 的代码和依赖可用。

### 20.2 修复合同

新增共享的 Controller optimizer runtime probe，并由 Requirement 的同一真实 strategy
resolver 得到 `resolved_backend`，不再依据原始字符串自行猜测：

- `native_turbo`：复用 runtime 的 `DEFAULT_TURBO_PATH`，因此同样遵循
  `TURBO_HOME` 或源码 `vendor/TuRBO` fallback；检查 `turbo.Turbo1`、实际使用的
  `turbo.utils` symbols、NumPy、PyTorch、GPyTorch 与 `threadpoolctl.threadpool_info`；
  当 `initialization: sobol` 时额外检查 `scipy.stats.qmc.Sobol`。
- `openbox`：检查 Hermes 的真实 OpenBox backend seam，以及 `_load_openbox()` 实际
  使用的 `Advisor`、`Observation`、space、`InitialConfigProvider` 与 `History` API。
- `random_baseline`：不虚假要求 OpenBox 第三方算法包，只检查它真实复用的 Hermes
  random-baseline backend seam。
- `fix_run`：明确写入 `skipped`，说明该 workflow 不使用 optimizer runtime。

探针只使用当前 Controller Python 进程的 import 和 `sys.path`，不会启动子 Python；
Native 的 TuRBO 路径只在探测期间按真实 runtime 规则临时加入，并在结束后恢复原
`sys.path`。local Product Doctor 和 Remote Doctor 都写入
`controller_optimizer_runtime` check；依赖缺失统一 fail closed，并写入
`CONTROLLER_OPTIMIZER_RUNTIME_UNAVAILABLE` structured diagnostic。Remote 接入点不会
通过 SSH 在 Remote Host 查询 Python，测试显式断言所有 FakeRunner 命令不含 Python。

原低层 `hermes-workflow check-toolchain-env` 命令、参数、JSON report 和独立测试保持
不变；它仍可用于显式诊断某个 venv/Cadence path，但不再冒充 backend-aware Product
Doctor gate。`run_product_doctor(openbox_venv=...)` 与旧 services 字段保留源码兼容，
真实 Product Doctor gate 则以当前执行进程为准。

### 20.3 红绿证据与当前状态

- 第一条 Native Sobol tracer test 在实现前 collection 失败：
  `ModuleNotFoundError: hermes_workflow.optimizer_runtime`；最小共享 probe 后转绿。
- OpenBox API、random baseline 与 fix-run 三条矩阵红测在首版 Native-only probe 下分别
  表现为零 dependency call、零 dependency call 和错误 `fail`；补齐 backend 分支后
  六条共享 probe 测试转绿。
- local/Remote 两条 pass 和两条 dependency-fail 公开 Doctor seam 在接入前均因缺少
  service/函数参数失败；接入后四条转绿，并验证同一 Requirement sections/workflow
  mode 被传给 Controller probe、Remote SSH 无 Python 命令。
- fix-run 的 local/Remote public Doctor 回归均为 `skipped` 且整体 Doctor pass。
- optimizer-runtime、local Product Doctor、Remote Doctor 和低层 toolchain CLI 的
  直接矩阵为 `105 passed, 15 warnings`；扩展到 strategy resolver、Native/OpenBox
  runner、local/Remote optimizer flow、两套 product CLI 和 Requirement intake 后为
  `467 passed, 15 warnings`。
- 最终开发包全量为 `1643 passed, 13 warnings`；`ruff check src tests` 与
  `git diff --check` 均通过。低层 `check-toolchain-env` 独立回归为
  `5 passed, 13 warnings`。版本号仍为 `0.1.10`。

## 21. v0.1.10 最终落地状态

收口日期：2026-08-12。本节是本台账的最终状态摘要；前文中的“尚未同步”、
“尚未真实验收”等表述保留为各检查点的历史记录，不再代表最终状态。

### 21.1 已修 bug 清单

- 结果可信度：Remote run 隔离和新鲜度、fix-run Metrics、corner 替换与多
  testbench corner、旧成功报告、manifest/trace/metric scientific binding、
  retention evidence，以及 completion 的有效唯一覆盖数均已闭合。
- Remote 可靠性：显式 `/bin/sh`、SSH 返回码分类、attempt lock、传输超时与原子
  发布、Doctor 工具与 optimizer runtime 检查、snapshot 清理、continuation 重跑
  Doctor、真实 UTC provenance 和历史 manifest 恢复均已落地。
- CLI 与能力合同：dry 参数边界、fix-run 空成功、OpenBox continuation delta、
  Native TuRBO local/Remote continuation、portable toolchain path、backend artifact
  选择和 task-package backend 分派均已修复。
- Requirement 科学语义：Workflow/mode/section、未知字段、measurement route、
  fixed-point、constraint 单位、objective 合同、model/corner、history warm-start 和
  11 个模板组合均已进入 fail-closed 校验或真实执行合同。
- Remote continuation 最终 blocker：frozen Controller cache 不包含
  `supervisor_instruction.json`。continuation 现在依据 execution manifest 和当前配置
  重新生成 fail-closed 审批指令，再进入真实 optimizer gate。

### 21.2 软件与真实流程验收

- 发行 checkout 软件验收：`1757 passed, 13 warnings`；Ruff 和
  `git diff --check` 通过；版本源均为 `0.1.10`；11 个 requirement 模板的固定集合、
  镜像、parse/render 和 mode/section 合同通过。
- Wheel 构建、metadata、两个 CLI entry point、11 个 packaged requirement 模板和
  隔离安装 smoke 通过；wheel 不含 tests、build、vendor、cache 或 egg-info。
- 隔离 Remote Native TuRBO 沿用已完成的 100 次结果执行 `--continue 20`；没有重跑
  初始 100 次。最终为 120 个 parent、1080 个 child、1200 个 metric manifest 和
  2400 条 checksum；Remote `sha256sum -c` 为 2400/2400，通过且无未登记产物。
- History 前 100 行逐字节不变，旧 2000 条 artifact checksum 全部不变，只追加
  20 条 evaluation 和 400 条 inventory。新点均为 `turbo_trust_region`，恢复模式为
  `trace_reconstructed`，没有重新初始化。
- 最终 optimizer flow 为 `pass`，acceptance 为 `accepted`，finalization 为 `pass`，
  backend 为 `native_turbo`，transport 为 `remote`，无残留 active attempt lock。
- continuation blocker 的最小四文件修复定向回归为 `87 passed`；四文件 Ruff 和
  `git diff --check` 通过，未因此重复运行全量测试。

### 21.3 明确延期清单

以下项目不属于 v0.1.10 发布阻断项，后续如有明确产品需求再独立立项：

- Slurm/LSF job ID、scheduler submission、detach/reattach 等集群调度能力。
- 日志可读性、reject 原因透传、更多诊断字段和 optimizer state 字段命名澄清。
- 极端并发/TOCTOU 加固，以及与本次真实 direct-SSH 流程无关的故障笛卡尔矩阵。
- local continuation 在审批文件被外部删除后的自动重建；当前问题会 fail closed，
  不影响已验收的 Remote continuation。
- continuation 审批 wiring 测试使用更完整的 packaged fixture；真实生产 gate 和本次
  Remote 验收已通过，该测试增强不再延长本次发布。

除上述延期项外，v0.1.10 本轮维护停止继续开发；发布后新增需求进入后续版本。
