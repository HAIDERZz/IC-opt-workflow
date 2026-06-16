from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_RUNTIMES = ("claude", "opencode")


@dataclass(frozen=True)
class RuntimeAsset:
    source: Path
    target: Path
    kind: str


@dataclass(frozen=True)
class RuntimeInstallResult:
    runtime: str
    target_home: Path
    installed: list[Path]
    skipped: list[Path]


@dataclass(frozen=True)
class RuntimeStatusResult:
    runtime: str
    target_home: Path
    present: list[Path]
    missing: list[Path]


RUNTIME_ASSETS: dict[str, tuple[RuntimeAsset, ...]] = {
    "claude": (
        RuntimeAsset(
            source=Path("claude_skills/ic-opt"),
            target=Path("skills/ic-opt"),
            kind="directory",
        ),
    ),
    "opencode": (
        RuntimeAsset(
            source=Path("agent_runtime/opencode/command/ic-opt.md"),
            target=Path("command/ic-opt.md"),
            kind="file",
        ),
        RuntimeAsset(
            source=Path("agent_runtime/opencode/agents/ic-opt-execution.md"),
            target=Path("agents/ic-opt-execution.md"),
            kind="file",
        ),
    ),
}


def default_runtime_home(runtime: str) -> Path:
    normalized = _normalize_runtime(runtime)
    if normalized == "claude":
        return Path.home() / ".claude"
    if normalized == "opencode":
        return Path.home() / ".config" / "opencode"
    raise ValueError(f"unsupported runtime: {runtime}")


def install_runtime_adapter(
    runtime: str,
    *,
    target_home: Path | None = None,
    force: bool = False,
    repo_root: Path | None = None,
) -> RuntimeInstallResult:
    normalized = _normalize_runtime(runtime)
    root = repo_root or _repo_root()
    home = (target_home or default_runtime_home(normalized)).expanduser()
    installed: list[Path] = []
    skipped: list[Path] = []

    for asset in RUNTIME_ASSETS[normalized]:
        source = root / asset.source
        target = home / asset.target
        if not source.exists():
            raise FileNotFoundError(f"runtime asset is missing: {source}")
        if target.exists():
            if not force:
                skipped.append(target)
                continue
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        if asset.kind == "directory":
            shutil.copytree(source, target)
        elif asset.kind == "file":
            shutil.copy2(source, target)
        else:
            raise ValueError(f"unsupported runtime asset kind: {asset.kind}")
        installed.append(target)

    return RuntimeInstallResult(
        runtime=normalized,
        target_home=home,
        installed=installed,
        skipped=skipped,
    )


def inspect_runtime_adapter(
    runtime: str,
    *,
    target_home: Path | None = None,
) -> RuntimeStatusResult:
    normalized = _normalize_runtime(runtime)
    home = (target_home or default_runtime_home(normalized)).expanduser()
    present: list[Path] = []
    missing: list[Path] = []

    for asset in RUNTIME_ASSETS[normalized]:
        target = home / asset.target
        if target.exists():
            present.append(target)
        else:
            missing.append(target)

    return RuntimeStatusResult(
        runtime=normalized,
        target_home=home,
        present=present,
        missing=missing,
    )


def _normalize_runtime(runtime: str) -> str:
    normalized = runtime.strip().lower()
    if normalized not in SUPPORTED_RUNTIMES:
        supported = ", ".join(SUPPORTED_RUNTIMES)
        raise ValueError(f"runtime must be one of: {supported}")
    return normalized


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
