# 排障指南

先运行 doctor：

```bash
ic-opt PROJECT_DIR --doctor
```

Remote 模式默认 Controller 与 Remote Host 的文件系统完全隔离。远端路径只能通过
配置的 SSH transport 检查，或先明确下载到 Controller cache 后再由本地代码读取；
Controller 上偶然存在同名路径不能作为远端文件存在的依据。

## 找不到 `opt_requirement.md`

检查传入的 `PROJECT_DIR`。`opt_requirement.md` 必须在项目根目录。

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

按下面顺序提供 Cadence setup：

```text
--cadence-cshrc PATH
PROJECT_DIR/cadence_env.csh
IC_OPT_CADENCE_CSHRC
~/.ic-opt/cadence_env.csh
```

这个脚本需要能在 `csh`/`tcsh` 中找到 `spectre`、`ocean` 和 license 工具。

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

## 不要只看退出码

真实 workflow 验收至少看：

```text
reports/ic_opt_doctor_report.json
reports/license_probe_report.json
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
reports/fix_run_report.json
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
runs/**/waveform_export_manifest.json
```

fix-run 成功时，`reports/fix_run_report.json` 应显示 `workflow_mode: fix_run`。
如果请求 waveform CSV，每个成功 child 都应有 waveform export manifest 和 CSV 文件。
fix-run 不应生成 optimizer state 或 optimizer decision report。
