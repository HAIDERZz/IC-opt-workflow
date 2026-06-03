#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_KEYS = set(
    "schema_version current_scope current_status review_status subagent_dispatch "
    "active_spec active_plan top_level_plan progress_files next_allowed_action "
    "forbidden_actions required_pre_commit_checks review_evidence".split()
)
ALLOWED_REVIEW_STATUSES = {"verified-only", "reviewed", "blocked-no-subagent"}
ALLOWED_SUBAGENT_STATES = {"available", "not_available"}
REVIEW_EVIDENCE_KEYS = ("spec_review", "code_quality_review")
FORBIDDEN_STAGED_PREFIXES = ("docs/OCEAN_DOC_", "docs/toolchain_evidence/")
REQUIRED_FORBIDDEN_ACTIONS = {
    "run Virtuoso", "run Spectre", "run OCEAN", "run SSH", "run Claude CLI",
    "run virtuoso-bridge-lite", "use network", "run subprocess-backed C-7 adapter",
    "parse PSF", "rewrite OCEAN formulas",
}
CURRENT_STATUS_RE = re.compile(r"^\s*-?\s*current status\s*:", re.IGNORECASE)


def check_project(root: str | Path) -> list[str]:
    project_root = Path(root)
    errors: list[str] = []
    state = _load_state(project_root, errors)
    _check_line_budget(errors)
    if state is None:
        return errors

    missing = sorted(REQUIRED_KEYS - state.keys())
    if missing:
        errors.append(f"CURRENT_TASK_STATE missing required keys: {', '.join(missing)}")
    _check_review_status(state, errors)
    _check_forbidden_actions(state, errors)
    _check_pre_commit_checks(state, errors)
    _check_referenced_files(project_root, state, errors)
    _check_forbidden_staged_paths(project_root, errors)
    return errors


def _load_state(root: Path, errors: list[str]) -> dict[str, Any] | None:
    state_path = root / "docs/CURRENT_TASK_STATE.json"
    if not state_path.exists():
        errors.append("docs/CURRENT_TASK_STATE.json is missing")
        return None
    try:
        state = json.loads(state_path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"docs/CURRENT_TASK_STATE.json is invalid JSON: {exc}")
        return None
    if not isinstance(state, dict):
        errors.append("docs/CURRENT_TASK_STATE.json must contain a JSON object")
        return None
    return state


def _check_review_status(state: dict[str, Any], errors: list[str]) -> None:
    review_status = state.get("review_status")
    if review_status not in ALLOWED_REVIEW_STATUSES:
        errors.append(f"review_status must be one of {sorted(ALLOWED_REVIEW_STATUSES)}")
        return
    if state.get("subagent_dispatch") not in ALLOWED_SUBAGENT_STATES:
        errors.append(f"subagent_dispatch must be one of {sorted(ALLOWED_SUBAGENT_STATES)}")
    current_status = str(state.get("current_status", ""))
    if review_status != "reviewed" and _mentions_reviewed(current_status):
        errors.append(f"current_status says reviewed while review_status is {review_status}")
    if review_status == "reviewed":
        evidence = state.get("review_evidence")
        if not isinstance(evidence, dict):
            errors.append("reviewed status requires review evidence")
            return
        missing = [key for key in REVIEW_EVIDENCE_KEYS if not evidence.get(key)]
        if missing:
            errors.append(f"reviewed status requires review evidence: {', '.join(missing)}")


def _check_forbidden_actions(state: dict[str, Any], errors: list[str]) -> None:
    actions = state.get("forbidden_actions")
    if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
        errors.append("forbidden_actions must be a list of strings")
        return
    missing = sorted(REQUIRED_FORBIDDEN_ACTIONS - set(actions))
    if missing:
        errors.append(f"forbidden_actions missing required entries: {', '.join(missing)}")


def _check_pre_commit_checks(state: dict[str, Any], errors: list[str]) -> None:
    checks = state.get("required_pre_commit_checks")
    if not isinstance(checks, list) or not all(isinstance(item, str) for item in checks):
        errors.append("required_pre_commit_checks must be a list of strings")
        return
    if not any("tools/check_development_cadence.py" in item for item in checks):
        errors.append("required_pre_commit_checks must include the cadence checker")


def _check_referenced_files(root: Path, state: dict[str, Any], errors: list[str]) -> None:
    active_spec = _required_text(state.get("active_spec"), "active_spec", errors)
    active_plan = _required_text(state.get("active_plan"), "active_plan", errors)
    top_level_plan = _required_text(state.get("top_level_plan"), "top_level_plan", errors)
    current_scope = _required_text(state.get("current_scope"), "current_scope", errors)
    next_action = _required_text(state.get("next_allowed_action"), "next_allowed_action", errors)
    if active_spec:
        _check_existing_text_file(root, active_spec, "active_spec", errors)
    if active_plan:
        _check_existing_text_file(root, active_plan, "active_plan", errors)
    if top_level_plan:
        _check_existing_text_file(root, top_level_plan, "top_level_plan", errors)
    progress_files = state.get("progress_files")
    if not isinstance(progress_files, list) or not progress_files:
        errors.append("progress_files must be a non-empty list")
        return
    for rel_path in progress_files:
        if not isinstance(rel_path, str):
            errors.append("progress_files entries must be strings")
            continue
        _check_progress_file(root, rel_path, state, errors, current_scope, next_action)


def _check_existing_text_file(root: Path, rel_path: str, label: str, errors: list[str], required_text: str | None = None) -> None:
    path = root / rel_path
    if not path.exists():
        errors.append(f"{label} does not exist: {rel_path}")
        return
    text = path.read_text()
    if any(marker in text.upper() for marker in ("TODO", "TBD")):
        errors.append(f"{rel_path} contains TODO/TBD placeholders")
    if required_text and required_text not in text:
        errors.append(f"{rel_path} does not mention current_scope")


def _check_progress_file(root: Path, rel_path: str, state: dict[str, Any], errors: list[str], current_scope: str | None, next_action: str | None) -> None:
    path = root / rel_path
    if not path.exists():
        errors.append(f"progress file does not exist: {rel_path}")
        return
    text = path.read_text()
    if current_scope and current_scope not in text:
        errors.append(f"{rel_path} does not mention current_scope")
    if next_action and next_action not in text:
        errors.append(f"{rel_path} does not mention next_allowed_action")
    if state.get("review_status") != "reviewed":
        for line in text.splitlines():
            if CURRENT_STATUS_RE.match(line) and _mentions_reviewed(line):
                errors.append(f"{rel_path} current status says reviewed while state is verified-only")


def _required_text(value: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")
        return None
    return value


def _mentions_reviewed(value: str) -> bool:
    return bool(re.search(r"\breviewed\b", value, re.IGNORECASE))


def _check_forbidden_staged_paths(root: Path, errors: list[str]) -> None:
    if not (root / ".git").exists():
        return
    result = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        errors.append(f"could not inspect staged files: {result.stderr.strip()}")
        return
    for rel_path in result.stdout.splitlines():
        if rel_path.startswith(FORBIDDEN_STAGED_PREFIXES):
            errors.append(f"forbidden staged path: {rel_path}")


def _check_line_budget(errors: list[str]) -> None:
    line_count = len(Path(__file__).read_text().splitlines())
    if line_count > 200:
        errors.append(f"tools/check_development_cadence.py has {line_count} lines; limit is 200")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0]) if args else Path.cwd()
    errors = check_project(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("development cadence check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
