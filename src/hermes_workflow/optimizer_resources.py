from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

OPTIMIZER_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "NUMBA_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


@contextmanager
def optimizer_cpu_thread_limits(
    threads: int,
    *,
    set_environment: bool = True,
    set_torch: bool = True,
) -> Iterator[None]:
    if threads < 1:
        raise ValueError("optimizer_cpu_threads must be >= 1")

    previous_env = {name: os.environ.get(name) for name in OPTIMIZER_THREAD_ENV_VARS}
    torch_state = _apply_torch_thread_limit(threads) if set_torch else None
    try:
        if set_environment:
            for name in OPTIMIZER_THREAD_ENV_VARS:
                os.environ[name] = str(threads)
        with _threadpool_limits(threads):
            yield
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
