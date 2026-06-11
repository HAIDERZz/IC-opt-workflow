# IC Auto Opt 常见报错与处理

这份文档用于用户和 agent 快速定位问题。原则是：先分清是用户项目文件、
Cadence/OCEAN 公式、SSH/远程环境，还是 optimizer 本身的问题。

## 推荐排查顺序

1. 先跑 doctor：

   ```bash
   ic-opt PROJECT --doctor
   ic-opt --ssh-profile PROFILE REMOTE_PROJECT --doctor
   ```

2. doctor 不通过时，不要继续 `--real`。先修 `opt_requirement.md`、路径、SSH 或
   Cadence 环境。
3. doctor 通过但真实优化失败时，再看 `reports/`、`runs/real_*/` 和
   `metrics/` 里的 manifest 与日志。
4. 远程模式下，同时看远程项目 `REMOTE_PROJECT/reports/` 和本机镜像：

   ```text
   ~/.ic-opt/remote_runs/<ssh-profile>/<project-hash>/reports/
   ```

## 常见报错表

| 报错或现象 | 常见原因 | 处理方式 |
| --- | --- | --- |
| `opt_requirement.md` 解析失败、缺少字段、格式不符合预期 | 需求文件是机器读取的严格结构，章节名、列表缩进、字段名或 YAML block 写错 | 先跑 `ic-opt PROJECT --doctor`，按 doctor 指出的文件和字段修。不要在聊天里补公式，要改文件。 |
| 本地 `ic-opt PROJECT --doctor` 输出 `optimize requires --real` | 旧版本本地 doctor 没有正确接入产品级 doctor 路由，误走了 optimizer 入口 | 更新到 v0.1.6 或更新版本。本地 doctor 应直接写 `reports/ic_opt_doctor_report.json`，不会启动 optimizer。 |
| objective 里使用 `eval(...)`、未知函数等，同时又报 unknown metric | 旧版本会把不支持的函数名重复当作 metric 名检查 | 更新到 v0.1.6 或更新版本。当前应只报 `OBJECTIVE_UNSUPPORTED_FUNCTION`。 |
| 找不到 `opt_requirement.md` | 项目路径给错，或文件名写成了其他名字 | 项目根目录必须有 `opt_requirement.md`。如果是远程模式，确认远程路径下存在这个文件。 |
| `maestro_point_root` 找不到 `netlist/input.scs` | 填错了 Maestro/ADE 结果目录层级 | `maestro_point_root` 必须是 leaf run 目录，里面应该有 `netlist/` 和 `psf/`，并且 `netlist/input.scs` 存在。不要填 `Interactive.N`、`Interactive.N/1`、`netlist/` 或 `psf/`。 |
| `cadence_env.csh` 不存在或 source 失败 | Cadence 环境文件路径不对，或者环境脚本依赖当前 shell/机器 | 本地模式把 `cadence_env.csh` 放到项目目录或用 `--cadence-cshrc` 指定。远程模式传远程服务器上的路径。不要硬编码 Spectre 版本到项目代码里。 |
| `Badly placed ()'s.` | 在 `csh/tcsh` 里执行了 bash/zsh 的 venv activate 脚本 | csh/tcsh 用 `source .venv/bin/activate.csh`。bash/zsh 才用 `source .venv/bin/activate`。 |
| `command 'swig' failed: No such file or directory` | 可选高级依赖 `pyrfr` 编译需要 SWIG，但当前环境没有可执行的 `swig` | 基础优化不需要 `pyrfr`。如果确实要高级 OpenBox surrogate 视图，先安装 SWIG，并确认 `swig -version` 可运行。 |
| `ModuleNotFoundError: No module named 'swig'` 出现在 `.venv/bin/swig` | pip 安装的 swig wrapper 没在当前 build 环境里正确解析 | 先激活 `.venv`，确认 `swig -version`，必要时用 `python -m pip install --no-build-isolation pyrfr==0.9.0`。 |
| `fatal error: Python.h: No such file or directory` | 编译可选依赖时缺少当前 Python 对应的开发头文件 | 请管理员安装 `python3-dev`、`python3-devel`、`python3.11-dev` 或匹配当前 Python 的 dev package。基础优化可以不装高级依赖。 |
| OCEAN metric `non_scalar`、`value_text is not a finite scalar` | OCEAN 表达式返回 waveform/list/空值/NaN，而不是单个数；也可能这个候选点下公式无定义 | 这是 metric 定义或该候选点的仿真结果问题。用 OCEAN scalar 表达式包起来，例如 `value(...)`、`ymax(...)`、`cross(...)` 后再取数。 |
| `metric_check_failed` 很多 | metric 公式在大量候选点上不能得到合法标量，或 testbench/信号名/结果名不稳定 | 先用一个已知好点手工验证每个 OCEAN 公式。必要时放宽 metric 检查或修公式，不要让 optimizer 继续白跑。 |
| `constraint_failed` 很多、feasible 很少 | 约束太严格，搜索范围不覆盖可行区域，或 FoM/约束方向写反 | 查看 decision report 的失败分类和单点 metrics。先判断是某个指标卡死，还是多个指标整体达不到。 |
| `No feasible observations` | 当前已跑点没有一个满足全部约束 | 放宽明显不合理的约束、修 metric 公式、扩大搜索空间，或者先跑更粗的探索。 |
| `No complete BW/MAX_GAIN/NF_3G/IIP3/P1DB score points` | FoM/瓶颈图需要的 metric 名在已完成点里不完整，或对应 metric 非标量/缺失 | 检查 `opt_requirement.md` 里的 metric 名是否和 FoM 完全一致，例如 `P1DB` 与 `P1dB`。确认这些 metric 都能在同一 candidate 上得到标量。 |
| FoM 瓶颈图所有点贴底边 | 归一化阈值太严格，某个瓶颈 score 长期为 0，或者大量点缺失关键 metric | 逐项计算每个 score。把硬阈值和归一化宽度设置到样本分布能区分优劣的位置，不要让某个指标永远为 0。 |
| `Host key verification failed` | 本机还没有信任远程服务器 host key | 手动运行 `ssh PROFILE true`，确认服务器地址正确后输入 `yes`。之后再跑 `ssh -o BatchMode=yes PROFILE true`。 |
| `Permission denied (publickey)` 或 BatchMode SSH 失败 | 免密 SSH 没配置好，公钥没有放到远程 `authorized_keys`，或 SSH profile 写错 | 修 `~/.ssh/config`、`IdentityFile`、远程 `~/.ssh/authorized_keys`。不要让 `ic-opt` 等待密码输入。 |
| `kex_exchange_identification: Connection closed by remote host`、`Connection reset by peer` | 远程 SSH 服务端连接数限制、`MaxStartups`、防护策略或瞬时并发过高 | 降低 `--parallel-jobs`。远程多 testbench 正常建议 4-8。24/36 更像压力测试，容易触发 SSH 传输失败。 |
| 高并发远程 run 后曾出现 `result_manifest.json missing` | 旧版本在某些 SSH/upload/download 异常路径没有写失败 manifest | 更新到 v0.1.5 或更新版本。当前版本应把 SSH/tool 异常记录为 `real_check_failed`，并保留 manifest 供验收。 |
| `real_check_failed` | Spectre/OCEAN/SSH/license/文件拷贝等真实工具链失败 | 看对应 `runs/real_xxx/` 下 `result_manifest.json`、`spectre.stderr`、`metrics/ocean.stderr`、`metrics/metric_result_manifest.json`。这不是电路性能失败。 |
| 远程 reports 没同步到本机 | SSH 下载/打包失败，或者本机镜像目录不可写 | 先看远程 `REMOTE_PROJECT/reports/`。再检查本机 `~/.ic-opt/remote_runs/...` 权限和 SSH/tar/scp 是否可用。 |

## 远程并发怎么理解

`parallel_jobs` 是 candidate 级别并发，不是每个 testbench 的并发数。

例如一个 Mixer candidate 有 CG/NF、IIP3、P1dB 三个 testbench：

```text
parallel_jobs = 8
```

表示最多同时评估 8 个 candidate。每个 candidate 内部会按项目定义跑它需要的
testbench。实际远程压力包括 SSH 连接、Spectre/OCEAN 进程、license、磁盘 IO 和
testbench 数量。

正常远程多 testbench 建议从 4 到 8 开始。只有在你确认 SSH 服务端、license 和
服务器资源都允许时，再提高并发。

`optimizer_cpu_threads` 只限制本机 optimizer/OpenBox 侧的 CPU 线程，不限制远程
Spectre/OCEAN 进程数量，也不限制 SSH 连接数。

## Agent 操作原则

给 agent 使用时，应要求 agent：

1. 先运行 `ic-opt PROJECT --doctor` 或
   `ic-opt --ssh-profile PROFILE REMOTE_PROJECT --doctor`。
2. doctor 失败就停止，汇报具体文件、字段或路径。
3. doctor 通过后才运行 `--real` 或 `--continue`。
4. 不手改 OCEAN 公式、不手选候选点、不直接解析 PSF。
5. 遇到本表中的报错时，先按原因分类，再给用户一个具体修复建议。
