# C-69 Remote SSH Acceptance Evidence

Date: 2026-06-08

## Implementation Status

Tasks 1-9 are implemented and tested. All unit tests pass.

## Real Remote Acceptance

BLOCKED: Real remote acceptance requires a user-provided SSH profile and remote
project path with a working Cadence environment. These were not available during
implementation.

To complete real acceptance, the user must provide:
1. An SSH profile name configured in `~/.ssh/config`
2. A remote project directory with `opt_requirement.md` and `cadence_env.csh`
3. Working Spectre and OCEAN installations on the remote server

Then run:
```bash
ic-opt --ssh-profile PROFILE /remote/project --doctor
ic-opt --ssh-profile PROFILE /remote/project --real --max-evals 10 --batch-size 2
ic-opt --ssh-profile PROFILE /remote/project --continue 4 --batch-size 2
```

## Local Test Coverage

- `test_remote_ssh.py` - SSH runner, command construction, tree transfer
- `test_remote_project.py` - Project reference, cache path derivation
- `test_remote_doctor.py` - Doctor checks, SSH failure handling
- `test_remote_prepare.py` - Cache preparation, netlist download
- `test_remote_spectre_ocean.py` - Remote adapter, spectre/ocean commands
- `test_remote_optimizer_flow.py` - Optimizer flow, continuation
- `test_product_cli_remote.py` - CLI routing for --doctor, --real, --continue

## Design Compliance

- Passwordless SSH: User configures outside product (no password management)
- Remote project is source of truth: Reports written on server first
- Local mirror: `~/.ic-opt/remote_runs/<profile>/<hash>/`
- No PSF parsing, no OCEAN formula rewrite, no Spectre version hardcode
- Local mode behavior unchanged
- No remote Python product package required
