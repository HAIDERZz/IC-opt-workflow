# Claude Skill Adapter

Install from the repository root:

```bash
./.venv/bin/hermes-workflow install-runtime-adapter claude
```

Then a Claude session can use:

```text
/ic-opt PROJECT_DIR --doctor
/ic-opt PROJECT_DIR --real
/ic-opt PROJECT_DIR --continue 40
```

The default behavior is single-agent operation: Claude runs the deterministic
`ic-opt` CLI, waits for completion, reads the reports, and explains the result.
Native Claude subagent/task execution is optional and should be used only when
the user explicitly asks for it and the runtime provides that capability.
