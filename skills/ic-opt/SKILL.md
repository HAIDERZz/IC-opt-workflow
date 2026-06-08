# ic-opt Skill

## Remote SSH Mode

When a user asks to optimize a project on a remote Linux EDA server, use the
`--ssh-profile` flag:

```bash
ic-opt --ssh-profile PROFILE /remote/project/path --doctor
ic-opt --ssh-profile PROFILE /remote/project/path --real
ic-opt --ssh-profile PROFILE /remote/project/path --continue N
```

Replace `PROFILE` with the SSH profile name from `~/.ssh/config`.

### Doctor First

Always run `--doctor` before `--real` to verify:
- SSH passwordless login works
- Remote project directory exists and is writable
- Cadence environment (spectre, ocean) is available
- Requirement file is valid

### If Doctor Reports SSH Failure

Tell the user to verify passwordless SSH:

```bash
ssh PROFILE true
```

Do not ask for passwords. The user must configure SSH keys themselves.

### Remote Project Path

The project path in remote mode is a Linux server path, not a local path.
Example: `/home/user/spectre_opt_prj/Mixer_opt`

### Reports

Reports are written on the remote server under `PROJECT/reports/` and mirrored
locally under `~/.ic-opt/remote_runs/`.
