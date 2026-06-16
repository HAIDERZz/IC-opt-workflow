# 排障指南

先运行 doctor：

```bash
ic-opt PROJECT_DIR --doctor
```

如果是远程项目：

```bash
ic-opt --ssh-profile PROFILE PROJECT_DIR --doctor
```

doctor 会把问题写入 `reports/project_doctor_report.json`。如果启用了 license 检查，
还会写 `reports/license_probe_report.json`。

## 常见问题

| 现象 | 可能原因 | 处理方式 |
| --- | --- | --- |
| 找不到 `opt_requirement.md` | 项目目录不对 | 确认命令里的 `PROJECT_DIR` 是优化项目目录，不是 release 根目录。 |
| 找不到 `netlist/input.scs` | Maestro/ADE point root 写错 | 在 Maestro/ADE 先跑通一个点，把包含 `netlist/input.scs` 的 point root 写进 requirement。 |
| `cadence_env.csh` source 失败 | Cadence setup 路径或 shell 环境不对 | 把 setup 文件放到 `PROJECT_DIR/cadence_env.csh`，或用 `--cadence-cshrc PATH` 指定。 |
| `spectre` 或 `ocean` 不在 PATH | Cadence setup 没有加载对应工具 | 先用同一个 csh setup 手动检查 `which spectre` 和 `which ocean`。 |
| license probe 失败 | license server 不可见，或 `lmstat` 不可用 | 查看 `reports/license_probe_report.json` 的 `issues`、`raw_stderr`、`spectre_path` 和 `license_features`。 |
| objective 或 metric 检查失败 | metric 名称、公式或 testbench route 不匹配 | 检查 `opt_requirement.md` 的 Metrics、Constraints、Objective，以及生成的 `config/metrics.yaml`。 |
| OCEAN metric 失败 | OCEAN 脚本、结果路径或 PSF 输出不匹配 | 查看 `runs/**/metrics/metric_result_manifest.json`、`ocean.stdout` 和 `ocean.stderr`。 |
| Spectre 仿真失败 | netlist、model section、corner 变量或 license 问题 | 查看 `runs/**/result_manifest.json`、`spectre.stdout` 和 `spectre.stderr`。 |
| remote reports 没同步回来 | SSH、tar/scp 或本机 cache 目录失败 | 先看远程 `PROJECT_DIR/reports/`，再看本机 `~/.ic-opt/remote_runs/`。 |
| 续跑结果被拒绝 | 当前 run 与已有 config 合同不一致 | 续跑只使用 `ic-opt PROJECT_DIR --real --continue N`，其它设置从已有项目 config 继承。 |

## 并行和线程

`parallel_jobs` 是候选点级别并发。`threads_per_run` 是单个 Spectre 仿真的线程数。
`optimizer_cpu_threads` 限制 Python 优化器侧的 CPU 线程。

真实 run 后，检查：

```text
reports/optimizer_run_report.json
reports/optimizer_decision_report.md
```

确认 `runtime_thread_limits` 记录了 requested/effective 线程信息。

## command trace

真实 Spectre/OCEAN run 应在 manifest 中写入 sanitized command trace：

```text
runs/**/result_manifest.json
runs/**/metric_result_manifest.json
```

trace 应包含 Spectre/OCEAN argv 摘要，不应包含 cshrc 内容、SSH wrapper 或 secret。

## 多工艺角

如果多工艺角结果看起来不对，检查 parent aggregate manifest：

- 是否包含所有 expected corners；
- 每个 child manifest 是否存在；
- `objective_policy` 和 `constraint_policy` 是否和 requirement 一致；
- selected corner、worst corner 和报告说明是否一致。
