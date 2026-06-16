from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
from typing import Any

OPTIMIZER_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "NUMBA_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


@dataclass(frozen=True)
class OptimizerThreadAudit:
    """Runtime audit snapshot for optimizer CPU thread limiting.

    Proves that ``optimizer.optimizer_cpu_threads`` from
    ``opt_requirement.md`` / generated config reached the backend
    runtime and was applied inside the active limit context.
    """

    source: str
    requested_threads: int
    effective_threads: int
    backend: str
    execution_mode: str
    process_scope: str
    env_vars: dict[str, str | None]
    threadpoolctl: dict[str, Any]
    torch: dict[str, Any]
    issues: list[str]
    transport_mode: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _capture_threadpoolctl_info() -> tuple[dict[str, Any], list[str]]:
    """Capture threadpoolctl library summaries.

    Returns (threadpoolctl_dict, issues).
    """
    try:
        from threadpoolctl import threadpool_info  # noqa: F401
    except ImportError:
        return (
            {"available": False, "libraries": []},
            ["threadpoolctl not available: cannot verify threadpool thread limits"],
        )

    try:
        from threadpoolctl import threadpool_info

        raw = threadpool_info()
    except Exception as exc:  # noqa: BLE001
        return (
            {"available": False, "libraries": []},
            [f"threadpoolctl threadpool_info() failed: {exc}"],
        )

    libraries: list[dict[str, Any]] = []
    for entry in raw:
        libraries.append(
            {
                "user_api": entry.get("user_api"),
                "internal_api": entry.get("internal_api"),
                "num_threads": entry.get("num_threads"),
                "prefix": entry.get("prefix"),
            }
        )
    return {"available": True, "libraries": libraries}, []


def _capture_torch_info(
    threads: int, *, set_torch: bool
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Capture torch thread info before applying limits.

    Returns (torch_dict, torch_state_for_restore).
    """
    try:
        import torch
    except ImportError:
        return (
            {"available": False, "num_threads": None, "num_interop_threads": None},
            None,
        )

    info: dict[str, Any] = {"available": True}
    if hasattr(torch, "get_num_threads"):
        try:
            info["num_threads"] = torch.get_num_threads()
        except RuntimeError:
            info["num_threads"] = None
    else:
        info["num_threads"] = None

    if hasattr(torch, "get_num_interop_threads"):
        try:
            info["num_interop_threads"] = torch.get_num_interop_threads()
        except RuntimeError:
            info["num_interop_threads"] = None
    else:
        info["num_interop_threads"] = None

    return info, None


def _threadpoolctl_info() -> list[dict[str, Any]]:
    """Retrieve threadpoolctl info at call time (inside the context)."""
    try:
        from threadpoolctl import threadpool_info

        return threadpool_info()
    except ImportError:
        return []
    except Exception:  # noqa: BLE001
        return []


@contextmanager
def optimizer_cpu_thread_limits(
    threads: int,
    *,
    set_environment: bool = True,
    set_torch: bool = True,
    backend: str = "unknown",
    execution_mode: str = "local",
    transport_mode: str = "local",
) -> Iterator[OptimizerThreadAudit]:
    """Context manager that limits optimizer CPU threads and yields an audit.

    Old usage ``with optimizer_cpu_thread_limits(...):`` still works because
    the yielded value is an ``OptimizerThreadAudit`` with ``to_dict()``.

    New usage ``with optimizer_cpu_thread_limits(...) as audit:`` captures
    the audit for artifact writing.
    """
    if threads < 1:
        raise ValueError("optimizer_cpu_threads must be >= 1")

    previous_env = {name: os.environ.get(name) for name in OPTIMIZER_THREAD_ENV_VARS}
    torch_state = _apply_torch_thread_limit(threads) if set_torch else None
    issues: list[str] = []

    try:
        if set_environment:
            for name in OPTIMIZER_THREAD_ENV_VARS:
                os.environ[name] = str(threads)
        with _threadpool_limits(threads):
            # Capture audit state inside the active limit context
            env_vars = {name: os.environ.get(name) for name in OPTIMIZER_THREAD_ENV_VARS}

            # Threadpoolctl snapshot
            tpctl_dict, tpctl_issues = _capture_threadpoolctl_info()
            issues.extend(tpctl_issues)

            # If threadpoolctl is available, capture per-library summaries
            if tpctl_dict["available"]:
                raw_info = _threadpoolctl_info()
                libraries: list[dict[str, Any]] = []
                for entry in raw_info:
                    libraries.append(
                        {
                            "user_api": entry.get("user_api"),
                            "internal_api": entry.get("internal_api"),
                            "num_threads": entry.get("num_threads"),
                            "prefix": entry.get("prefix"),
                        }
                    )
                tpctl_dict["libraries"] = libraries

            # Torch snapshot
            torch_info = _capture_torch_info(threads, set_torch=set_torch)[0]

            # Determine effective_threads: the minimum of env-applied threads
            # and threadpoolctl/torch effective threads.
            effective_threads = threads
            if tpctl_dict["available"] and tpctl_dict["libraries"]:
                min_tp_threads = min(
                    (lib["num_threads"] for lib in tpctl_dict["libraries"] if lib.get("num_threads") is not None),
                    default=threads,
                )
                effective_threads = min(effective_threads, min_tp_threads)
            if torch_info["available"] and torch_info.get("num_threads") is not None:
                effective_threads = min(effective_threads, torch_info["num_threads"])

            audit = OptimizerThreadAudit(
                source="optimizer.optimizer_cpu_threads",
                requested_threads=threads,
                effective_threads=effective_threads,
                backend=backend,
                execution_mode=execution_mode,
                process_scope="local_optimizer_process",
                env_vars=env_vars,
            threadpoolctl=tpctl_dict,
            torch=torch_info,
            issues=issues,
            transport_mode=transport_mode,
        )
            yield audit
    finally:
        _restore_torch_thread_limit(torch_state)
        if set_environment:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _threadpool_limits(threads: int):
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:
        return nullcontext()
    return threadpool_limits(limits=threads)


def _apply_torch_thread_limit(threads: int) -> dict[str, Any] | None:
    try:
        import torch
    except ImportError:
        return None

    state: dict[str, Any] = {"torch": torch}
    if hasattr(torch, "get_num_threads") and hasattr(torch, "set_num_threads"):
        try:
            state["num_threads"] = torch.get_num_threads()
            torch.set_num_threads(threads)
        except RuntimeError:
            state.pop("num_threads", None)
    if hasattr(torch, "get_num_interop_threads") and hasattr(
        torch, "set_num_interop_threads"
    ):
        try:
            state["num_interop_threads"] = torch.get_num_interop_threads()
            torch.set_num_interop_threads(1)
        except RuntimeError:
            state.pop("num_interop_threads", None)
    return state


def _restore_torch_thread_limit(state: dict[str, Any] | None) -> None:
    if state is None:
        return
    torch = state["torch"]
    if "num_threads" in state:
        try:
            torch.set_num_threads(state["num_threads"])
        except RuntimeError:
            pass
    if "num_interop_threads" in state:
        try:
            torch.set_num_interop_threads(state["num_interop_threads"])
        except RuntimeError:
            pass
