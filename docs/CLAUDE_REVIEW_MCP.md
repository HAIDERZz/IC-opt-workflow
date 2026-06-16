# Claude Review MCP

This project includes a local MCP server that lets review gates call Claude CLI as a read-only reviewer.

## Server

- Name: `claude-review`
- Script: `tools/claude_review_mcp.py`
- Transport: stdio
- Tools:
  - `spec_review`
  - `code_quality_review`

## Registration

Claude Code can load the project-scoped `.mcp.json` after local approval. To register manually:

```bash
cd ic-auto-opt-workflow
claude mcp add -s project claude-review -- python tools/claude_review_mcp.py
```

## Safety Boundary

Reviewer sessions are read-only. The MCP server invokes `claude -p` with read-oriented tool permissions and does not expose any file-editing tool.

## Plan A Review Flow

Use this server only after an implementer finishes a task:

1. Call `claude-review.spec_review`.
2. Fix any spec gaps.
3. Call `claude-review.code_quality_review`.
4. Fix Critical and Important issues.
5. Run local verification before marking the task complete.

The MCP server is a review gate, not an implementation agent.
