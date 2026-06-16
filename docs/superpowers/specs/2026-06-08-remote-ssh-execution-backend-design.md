# C-69 Remote SSH Execution Backend Design

Date: 2026-06-08

## Decision

Add a remote SSH execution mode where the optimization project directory remains
on the Linux EDA server and keeps the same file structure as local mode. The
user's Mac/Windows/Linux workstation runs `ic-opt`, the agent skill, OpenBox,
and report interpretation. The remote Linux server runs only the Cadence-side
work: Spectre, OCEAN, and file access to Maestro/ADE point roots.

SSH connection setup follows the `virtuoso-bridge-lite` assumption: the user
configures passwordless SSH outside this project, normally through
`~/.ssh/config`, keys, `ProxyJump`, and the OS OpenSSH client. `ic-opt` does not
store passwords, manage private keys, or prompt for interactive passwords.

## Target User Shape

The Linux server project directory remains the source of truth:

```text
/home/user/spectre_opt_prj/Mixer_opt/
├── opt_requirement.md
├── constraints.md
├── cadence_env.csh
└── context/
```

After the run, the same remote project directory contains the normal generated
local-mode artifacts:

```text
/home/user/spectre_opt_prj/Mixer_opt/
├── config/
├── netlists/
├── runs/
├── reports/
├── ledger/
├── state/
└── execution_package/
```

The local workstation may keep a report/cache mirror:

```text
~/.ic-opt/remote_runs/<ssh_profile>/<project_hash>/
├── reports/
├── ledger/
├── state/
├── execution_package/
└── remote_execution_report.json
```

Initial user-facing command:

```bash
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --doctor
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --real
ic-opt --ssh-profile lab /home/user/spectre_opt_prj/Mixer_opt --continue 40
```

In remote mode, `PROJECT_DIR` is a remote POSIX path on the Linux server, not a
local path.

## Goals

- Preserve the existing local-mode project structure and report names.
- Let users avoid installing OpenBox, SHAP, LightGBM, or the full Python product
  environment on locked-down EDA servers.
- Keep Spectre/OCEAN execution on the Linux server where Cadence, PDKs, and
  licenses already exist.
- Keep the Mac/Windows workstation responsible for optimizer orchestration,
  agent operation, and report interpretation.
- Use the system `ssh`, `scp`, and `tar` tools first; do not add Paramiko or a
  daemon requirement for the MVP.
- Keep remote artifacts complete on the Linux server while downloading only the
  scalar/report artifacts needed locally.

## Non-Goals

- Do not operate Virtuoso GUI or Maestro GUI remotely in this feature.
- Do not require a long-running server daemon on the Linux host.
- Do not require installing the `ic-auto-opt-workflow` Python package on the
  Linux host for the MVP.
- Do not parse PSF or waveform databases locally or remotely.
- Do not rewrite approved OCEAN formulas.
- Do not flatten, merge, or synthesize multi-testbench Spectre decks.
- Do not manage SSH passwords, private keys, or credential storage.
- Do not claim support for Windows/macOS native Cadence execution. Cadence-side
  execution remains Linux remote.

## SSH Model

The MVP uses OpenSSH configuration as the user-controlled boundary:

```sshconfig
Host lab
  HostName eda-server.example.edu
  User user
  IdentityFile ~/.ssh/id_ed25519
  ProxyJump jump-host
```

`ic-opt --ssh-profile lab ...` runs noninteractive commands such as:

```bash
ssh -o BatchMode=yes lab 'test -d /home/user/spectre_opt_prj/Mixer_opt'
ssh -o BatchMode=yes lab 'csh -fc "source /path/to/cadence_env.csh; spectre -W"'
```

If passwordless SSH is not ready, `--doctor --ssh-profile lab` fails with a clear
user-side fix:

```text
SSH passwordless login failed for profile "lab".
Configure ~/.ssh/config and key-based login, then verify: ssh lab true
```

## Cadence Environment Discovery

Remote mode uses remote paths. The discovery order is:

1. explicit `--cadence-cshrc REMOTE_PATH`;
2. `PROJECT_DIR/cadence_env.csh` on the remote host;
3. `~/.ic-opt/cadence_env.csh` on the remote host.

The local workstation does not infer remote `.bashrc` or `.zshrc`, and the tool
must not hardcode a Spectre version. The remote doctor should verify:

```bash
csh -fc 'source <cadence_env.csh>; which spectre; which ocean'
```

## Architecture

Add a small remote layer beneath the existing optimizer flow:

```text
Product CLI
  -> ProjectAccessor
       LocalProjectAccessor
       RemoteSshProjectAccessor
  -> SpectreOceanAdapter
       LocalSpectreOceanAdapter
       RemoteSshSpectreOceanAdapter
  -> OpenBox controller
  -> Existing reports/decision/insight generation
```

### RemoteSshRunner

The first building block is a deterministic OpenSSH wrapper:

```text
RemoteSshRunner
- run(command, cwd=None, timeout=None) -> RemoteCommandResult
- read_text(remote_path) -> str
- write_text(remote_path, text)
- exists(remote_path) -> bool
- mkdir(remote_path)
- download(remote_path, local_path)
- upload(local_path, remote_path)
- download_tree(remote_path, local_path, include/exclude)
- upload_tree(local_path, remote_path, include/exclude)
```

Implementation rules:

- Use `ssh -o BatchMode=yes <profile> ...`.
- Use `tar` over SSH for directory sync where possible.
- Quote all remote paths and shell fragments with shell-safe quoting.
- Record every remote command in a redacted manifest.
- Never log secrets or license server values from sourced environments.

### Remote Project Cache

Remote mode needs a local cache because Python/OpenBox/report generation runs on
the workstation. The local cache is not the source of truth; it is a controller
workspace.

Suggested cache root:

```text
~/.ic-opt/remote_runs/<ssh_profile>/<project_hash>/
```

The project hash should include:

- SSH profile name;
- remote project path;
- normalized current user name when available.

Before a run:

1. Read remote `opt_requirement.md`, `constraints.md`, and `cadence_env.csh`.
2. Download only required Maestro/ADE point-root netlist bundles referenced by
   the requirement.
3. Build or refresh the local cache's `config/`, `netlists/`,
   `execution_package/`, `state/`, and `ledger/`.

During and after a run:

1. Upload candidate run packages to the remote project directory.
2. Run Spectre/OCEAN on the remote server.
3. Download scalar manifests, result manifests, and concise logs.
4. Update local optimizer state.
5. Sync `reports/`, `ledger/`, `state/`, and `execution_package/` back to the
   remote project directory.
6. Keep a local copy of the final reports.

## Data Flow

### Remote Doctor

`ic-opt --ssh-profile lab PROJECT --doctor` should:

1. verify `ssh lab true`;
2. verify remote `PROJECT` exists and is writable;
3. verify `PROJECT/opt_requirement.md` exists;
4. parse the requirement locally after reading it over SSH;
5. verify every referenced remote `maestro_point_root` exists;
6. verify each point root contains `netlist/input.scs`;
7. resolve remote Cadence cshrc;
8. verify remote `csh`, `spectre`, and `ocean`;
9. verify remote free-space and run directory permissions;
10. write `reports/ic_opt_doctor_report.json` on the remote project and mirror
    it locally.

Doctor must not launch a real Spectre simulation.

### Remote Real Run

`ic-opt --ssh-profile lab PROJECT --real` should:

1. run remote doctor gates;
2. prepare the local controller cache;
3. generate the optimizer task package locally;
4. sync generated config/package artifacts to remote;
5. run OpenBox locally;
6. for each suggested candidate, upload the candidate run package to remote;
7. run Spectre and OCEAN remotely;
8. download scalar metric/result artifacts;
9. update optimizer ledger/state locally;
10. sync ledger/state/reports back to remote;
11. write the usual decision and insight reports in both places.

The remote project directory must remain readable as a complete run artifact
even if the local workstation cache is deleted.

### Remote Continuation

`ic-opt --ssh-profile lab PROJECT --continue M` should:

1. sync current remote `ledger/`, `state/`, and `reports/` to local cache;
2. validate the remote history and resource settings;
3. continue local OpenBox from the synced history;
4. run only the additional M remote candidate evaluations;
5. refresh both remote and local reports.

Continuation must inherit existing resource settings unless the user explicitly
asks to change them.

## Artifact Policy

Remote Linux project keeps full artifacts:

```text
runs/real/<run_id>/
├── child testbench run directories
├── netlist bundles
├── psf/
├── result_manifest.json
├── metric_result_manifest.json
└── logs
```

Local workstation mirror downloads by default:

```text
reports/
ledger/
state/
execution_package/
runs/real/<run_id>/result_manifest.json
runs/real/<run_id>/metric_result_manifest.json
runs/real/<run_id>/*summary*.log
```

Local mirror should not download PSF/raw waveform databases by default.

## Failure Model

Remote failures must map to existing product concepts where possible:

- `remote_connection_failed`: SSH cannot connect noninteractively.
- `remote_project_failed`: project path missing or not writable.
- `remote_tool_env_failed`: cshrc, `spectre`, or `ocean` not available.
- `real_check_failed`: Spectre/OCEAN ran but produced invalid structural
  artifacts.
- `metric_check_failed`: OCEAN metric extraction produced missing, invalid, or
  non-scalar metrics.
- `constraint_failed`: valid scalar metrics did not meet user constraints.

The report should distinguish SSH/environment failures from circuit/metric
failures so users know whether to fix infrastructure or design requirements.

## Security And Privacy

- Do not store SSH passwords.
- Do not copy private keys.
- Do not log full sourced Cadence environments.
- Do not download raw PSF unless the user explicitly requests debug artifact
  collection.
- Do not commit remote project artifacts.
- Redact or summarize remote command logs where they contain license or PDK
  paths.

## Compatibility Notes

Mac/Linux local hosts can use system OpenSSH directly. Windows local hosts
should use the Windows OpenSSH client or Git Bash/MSYS2 OpenSSH. Remote paths
remain Linux POSIX paths. Local cache paths are platform-specific and should be
resolved with Python's user cache/home directory APIs.

## Implementation Phases

### Task 1: Remote SSH Runner And Doctor MVP

- Add `RemoteSshRunner`.
- Add remote project path abstraction.
- Add `ic-opt --ssh-profile PROFILE PROJECT --doctor`.
- Verify SSH, remote project, cshrc, Spectre/OCEAN availability, and point-root
  structure.
- No real Spectre simulation.

### Task 2: Remote Single-Candidate Spectre/OCEAN Smoke

- Reuse one approved candidate package.
- Upload it to the remote project run directory.
- Run remote Spectre/OCEAN.
- Download scalar manifests.
- Preserve remote run artifacts.

### Task 3: Remote OpenBox Real Run

- Run local OpenBox with remote candidate evaluation.
- Sync local cache and remote project reports.
- Pass acceptance on a small real project.

### Task 4: Remote Continuation

- Sync remote state/ledger to local cache.
- Continue M evaluations.
- Enforce resource inheritance.

### Task 5: User And Agent Documentation

- Add remote-mode sections to README and Chinese user guide.
- Update `skills/ic-opt/SKILL.md` so agents can map short requests to remote
  commands.
- Keep development specs out of the release package.

## Acceptance Criteria

- A user can verify remote readiness with one command:

  ```bash
  ic-opt --ssh-profile lab /remote/project --doctor
  ```

- A remote real run leaves the standard report files on the Linux server:

  ```text
  /remote/project/reports/optimizer_decision_report.md
  /remote/project/reports/optimizer_insight_report.md
  ```

- The local workstation also has a copied report mirror.
- The remote Linux server does not need OpenBox or advanced Python report
  dependencies installed.
- No approved OCEAN formula is rewritten.
- No PSF parsing is introduced.
- No Spectre version is hardcoded.
- Continuation preserves existing resource settings by default.
- SSH failures produce actionable doctor output before any optimizer run starts.

## Open Questions For Implementation

1. Should remote mode be expressed as `--ssh-profile PROFILE PROJECT` or as a
   URI such as `ssh://PROFILE/remote/project`? The MVP should implement only one
   to avoid CLI ambiguity.
2. Should local report mirror path be configurable in v1, or always default to
   `~/.ic-opt/remote_runs/...`?
3. How much of each candidate log should be downloaded by default?
4. Should `--doctor` optionally run a tiny remote Spectre version smoke, or
   should real simulator launch remain only in an explicit smoke/real command?

The current recommendation is:

- CLI form: `--ssh-profile PROFILE PROJECT`;
- local mirror: default path first, configurable later;
- logs: summary/manifests by default, full logs only on explicit debug request;
- doctor: no real simulation.
