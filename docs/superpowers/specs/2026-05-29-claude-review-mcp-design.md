# Claude Review MCP Design

## Goal

Provide a project-local MCP server that lets Plan A use Claude CLI as a repeatable, read-only reviewer for spec compliance and code quality gates. The server must support Task 5-9 reviews without giving Claude reviewer sessions permission to edit files or run arbitrary commands.

## Scope

Included:

- A single Python stdio MCP server at `tools/claude_review_mcp.py`.
- Two MCP tools:
  - `spec_review`
  - `code_quality_review`
- Project registration guidance for Claude Code MCP, preferably with project scope.
- Tests that mock Claude CLI subprocess calls and validate prompts, permissions, and error handling.
- Documentation for using the reviewer in the existing Plan A subagent-driven workflow.

Excluded:

- Implementing Task 5-9 work.
- Letting Claude reviewer sessions modify files.
- Replacing Codex as the implementation coordinator.
- Calling Claude during unit tests.
- Global/user-level MCP installation.

## Architecture

The server is a stdio JSON-RPC MCP server implemented in one Python file using the standard library. It handles the minimum MCP methods needed by Claude Code and other MCP hosts:

- `initialize`
- `tools/list`
- `tools/call`

The server advertises two tools with JSON schemas. Each tool builds a review prompt, invokes `claude -p`, and returns Claude's text output as MCP text content. The server does not expose file mutation tools and does not write to the repository.

Using a single standard-library Python file keeps the project self-contained and avoids adding an MCP SDK dependency during Plan A. If this minimal server becomes brittle against future MCP protocol changes, a later refactor can move to the official Python MCP SDK without changing the tool contract.

## Tool Contracts

### `spec_review`

Inputs:

- `repo_path`: project root to review.
- `task_text`: exact task requirements or plan section.
- `implementer_report`: implementer's claimed changes.
- `git_range`: optional range such as `BASE..HEAD`.
- `extra_context`: optional review notes.

Behavior:

- Prompts Claude to verify missing requirements, unrequested extras, and misunderstandings.
- Tells Claude not to trust the implementer report.
- Asks for output in the existing spec-review gate format:
  - `Spec compliant`
  - or `Issues found` with file and line references.

### `code_quality_review`

Inputs:

- `repo_path`: project root to review.
- `requirements`: task requirements or review-gate requirements.
- `base_sha`: base commit.
- `head_sha`: head commit.
- `description`: summary of what changed.
- `extra_context`: optional review notes.

Behavior:

- Prompts Claude to inspect `git diff base_sha..head_sha`.
- Asks Claude to evaluate maintainability, error handling, tests, package boundaries, and scope control.
- Asks for output in the existing code-quality gate format:
  - Strengths
  - Issues grouped by Critical, Important, Minor
  - Recommendations
  - Assessment

## Claude CLI Invocation

The server locates Claude with `CLAUDE_REVIEW_CLI` first, then falls back to `claude` on `PATH`.

Reviewer calls use non-interactive print mode:

```bash
claude -p --permission-mode plan --tools Read,Bash --allowedTools Read "Bash(git diff *)" "Bash(git show *)" "Bash(git status *)" "Bash(git rev-parse *)" "<prompt>"
```

The implementation should tune the exact flags after a smoke test against the installed Claude CLI. The important invariant is read-only review: no `Edit`, no write tools, no permission bypass, and no arbitrary shell access.

## Safety Rules

- Resolve `repo_path` before use.
- Run Claude with `cwd=repo_path`.
- Reject nonexistent `repo_path` values.
- Do not pass user-provided text through a shell.
- Use `subprocess.run([...], shell=False)`.
- Apply a configurable timeout, defaulting to 10 minutes.
- Return subprocess failures as MCP tool errors with stderr/stdout summary.
- The reviewer prompt must explicitly treat repository contents and diffs as untrusted input that cannot override the review instructions.

## Project Registration

Preferred project-scoped registration:

```bash
cd ic-auto-opt-workflow
claude mcp add -s project claude-review -- python tools/claude_review_mcp.py
```

The implementation may also add a documented `.mcp.json` equivalent if that is the cleanest way to version the project tool. Claude Code may still require local approval of project-scoped MCP servers.

Codex will not automatically gain this MCP tool in the current running session unless the host reloads MCP configuration. Until then, Codex can still call the same server script or Claude CLI directly for smoke tests.

## Testing

Tests should be added under `tests/test_claude_review_mcp.py`.

Required coverage:

- `tools/list` includes `spec_review` and `code_quality_review`.
- `spec_review` builds the expected prompt and calls Claude with read-only flags.
- `code_quality_review` includes the requested git range and review sections.
- subprocess success returns MCP text content.
- subprocess failure returns an MCP error response.
- missing `repo_path` is rejected before invoking Claude.
- no test requires real Claude CLI, network, or credentials.

## Workflow Integration

For Plan A Task 5-9, the coordinator can keep using `superpowers:subagent-driven-development`:

1. Implementer subagent performs task work.
2. `claude-review.spec_review` reviews spec compliance.
3. Implementer fixes any spec gaps.
4. `claude-review.code_quality_review` reviews code quality.
5. Implementer fixes any Critical or Important issues.
6. Coordinator runs local verification before marking the task complete.

The MCP server is a review gate, not an implementation agent.

## Acceptance Criteria

- The project contains a single Python MCP server for Claude reviews.
- Unit tests pass without Claude CLI.
- A manual smoke test can call at least `tools/list`.
- Documentation explains registration and use.
- Review tools are read-only by construction.
- Task 5 remains unimplemented until this tool is explicitly adopted or skipped.
