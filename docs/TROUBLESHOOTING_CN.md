# 排障指南

先运行 doctor：

```bash
ic-opt PROJECT_DIR --doctor
```

## 找不到 `opt_requirement.md`

检查传入的 `PROJECT_DIR`。`opt_requirement.md` 必须在项目根目录。

## `maestro_point_root/netlist/input.scs is missing`

`maestro_point_root` 必须指向 Maestro/ADE 的 result point 目录，不是
`input.scs` 文件，也不是 `psf/` 目录。

期望结构：

```text
<maestro_point_root>/netlist/input.scs
```

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

`parallel_jobs` 是候选点级别的 Spectre process 并发。`threads_per_run` 是单个
Spectre 仿真的 `+mt` 线程数。`optimizer_cpu_threads` 限制 Python 优化器侧的 CPU
线程。

这些值都来自 `opt_requirement.md`。

## 多工艺角结果看起来不一致

查看 parent aggregate manifest 和 `reports/optimizer_decision_report.md`。多工艺角
候选点会先聚合所有 child 结果，再把一条 observation 交给优化器。

## 不要只看退出码

真实 workflow 验收至少看：

```text
reports/project_doctor_report.json
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
