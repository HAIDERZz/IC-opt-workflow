from __future__ import annotations

import os
from unittest.mock import patch

from hermes_workflow.optimizer_resources import (
    OPTIMIZER_THREAD_ENV_VARS,
    OptimizerThreadAudit,
    optimizer_cpu_thread_limits,
)


class TestOptimizerThreadAuditDataclass:
    """OptimizerThreadAudit must exist as a frozen dataclass with to_dict()."""

    def test_audit_has_to_dict(self) -> None:
        audit = OptimizerThreadAudit(
            source="optimizer.optimizer_cpu_threads",
            requested_threads=32,
            effective_threads=32,
            backend="openbox",
            execution_mode="local",
            process_scope="local_optimizer_process",
            env_vars={name: "32" for name in OPTIMIZER_THREAD_ENV_VARS},
            threadpoolctl={"available": False, "libraries": []},
            torch={"available": False, "num_threads": None, "num_interop_threads": None},
            issues=[],
        )
        d = audit.to_dict()
        assert isinstance(d, dict)
        assert d["source"] == "optimizer.optimizer_cpu_threads"
        assert d["requested_threads"] == 32
        assert d["effective_threads"] == 32
        assert d["backend"] == "openbox"
        assert d["execution_mode"] == "local"
        assert d["process_scope"] == "local_optimizer_process"
        assert d["transport_mode"] == "local"
        assert d["env_vars"]["OMP_NUM_THREADS"] == "32"
        assert d["threadpoolctl"]["available"] is False
        assert d["torch"]["available"] is False
        assert d["issues"] == []


class TestOptimizerCpuThreadLimitsYieldsAudit:
    """optimizer_cpu_thread_limits(32) must yield an audit object."""

    def test_yields_audit_object(self) -> None:
        with optimizer_cpu_thread_limits(32) as audit:
            assert isinstance(audit, OptimizerThreadAudit)
            assert audit.requested_threads == 32

    def test_audit_inside_context_env_vars_are_set(self) -> None:
        with optimizer_cpu_thread_limits(32) as audit:
            for name in OPTIMIZER_THREAD_ENV_VARS:
                assert os.environ.get(name) == "32", f"{name} not set to 32 inside context"
            assert audit.env_vars.get("OMP_NUM_THREADS") == "32"

    def test_audit_after_context_env_vars_restored(self) -> None:
        saved = {name: os.environ.get(name) for name in OPTIMIZER_THREAD_ENV_VARS}
        with optimizer_cpu_thread_limits(16):
            pass
        for name in OPTIMIZER_THREAD_ENV_VARS:
            assert os.environ.get(name) == saved.get(name), (
                f"{name} not restored after context exit"
            )

    def test_audit_records_backend(self) -> None:
        with optimizer_cpu_thread_limits(
            8, backend="native_turbo", execution_mode="local"
        ) as audit:
            assert audit.backend == "native_turbo"
            assert audit.execution_mode == "local"

    def test_default_backend_and_execution_mode(self) -> None:
        with optimizer_cpu_thread_limits(8) as audit:
            assert audit.backend == "unknown"
            assert audit.execution_mode == "local"


class TestFakeThreadpoolctlPath:
    """When threadpoolctl is available, the audit must record library summaries."""

    def test_fake_threadpoolctl_recorded(self) -> None:
        fake_lib_info = [
            {
                "user_api": "blas",
                "internal_api": "openblas",
                "num_threads": 32,
                "prefix": "libopenblas",
            }
        ]

        with patch(
            "hermes_workflow.optimizer_resources._capture_threadpoolctl_info",
            return_value=(
                {"available": True, "libraries": []},
                [],
            ),
        ), patch(
            "hermes_workflow.optimizer_resources._threadpoolctl_info",
            return_value=fake_lib_info,
        ):
            with optimizer_cpu_thread_limits(32) as audit:
                assert audit.threadpoolctl["available"] is True
                assert len(audit.threadpoolctl["libraries"]) == 1
                assert audit.threadpoolctl["libraries"][0]["user_api"] == "blas"
                assert audit.threadpoolctl["libraries"][0]["num_threads"] == 32

    def test_threadpoolctl_unavailable_records_false_and_issue(self) -> None:
        with patch(
            "hermes_workflow.optimizer_resources._capture_threadpoolctl_info",
            return_value=(
                {"available": False, "libraries": []},
                ["threadpoolctl not available: cannot verify threadpool thread limits"],
            ),
        ):
            with optimizer_cpu_thread_limits(32) as audit:
                assert audit.threadpoolctl["available"] is False
                assert audit.threadpoolctl["libraries"] == []
                assert any(
                    "threadpoolctl" in issue.lower() for issue in audit.issues
                ), f"Expected threadpoolctl issue, got: {audit.issues}"


class TestFakeTorchPath:
    """When torch is available, the audit must record num_threads and
    num_interop_threads."""

    def test_fake_torch_recorded(self) -> None:
        """Patch _apply_torch_thread_limit and _capture_torch_info so we can
        test the audit recording path without needing real torch."""

        class _FakeTorch:
            def get_num_threads(self):
                return 32

            def set_num_threads(self, n):
                pass

            def get_num_interop_threads(self):
                return 1

            def set_num_interop_threads(self, n):
                pass

        fake_torch_obj = _FakeTorch()
        fake_torch_state = {
            "torch": fake_torch_obj,
            "num_threads": 32,
            "num_interop_threads": 1,
        }
        fake_torch_info = {
            "available": True,
            "num_threads": 32,
            "num_interop_threads": 1,
        }

        with patch(
            "hermes_workflow.optimizer_resources._apply_torch_thread_limit",
            return_value=fake_torch_state,
        ), patch(
            "hermes_workflow.optimizer_resources._capture_torch_info",
            return_value=(fake_torch_info, fake_torch_state),
        ):
            with optimizer_cpu_thread_limits(32, set_torch=True) as audit:
                assert audit.torch["available"] is True
                assert audit.torch["num_threads"] == 32
                assert audit.torch["num_interop_threads"] == 1

    def test_torch_unavailable_records_false(self) -> None:
        """When torch is not importable, the audit must record available=False."""

        with patch(
            "hermes_workflow.optimizer_resources._apply_torch_thread_limit",
            return_value=None,
        ), patch(
            "hermes_workflow.optimizer_resources._capture_torch_info",
            return_value=(
                {"available": False, "num_threads": None, "num_interop_threads": None},
                None,
            ),
        ):
            with optimizer_cpu_thread_limits(32, set_torch=True) as audit:
                assert audit.torch["available"] is False
                assert audit.torch["num_threads"] is None
                assert audit.torch["num_interop_threads"] is None


class TestOldUsageStillWorks:
    """Using optimizer_cpu_thread_limits as a plain context manager (without
    capturing the audit) must still work."""

    def test_context_without_as_clause(self) -> None:
        with optimizer_cpu_thread_limits(16):
            for name in OPTIMIZER_THREAD_ENV_VARS:
                assert os.environ.get(name) == "16"

    def test_set_environment_false_still_works(self) -> None:
        saved = {name: os.environ.get(name) for name in OPTIMIZER_THREAD_ENV_VARS}
        with optimizer_cpu_thread_limits(16, set_environment=False) as audit:
            # Env vars should NOT be set when set_environment=False
            for name in OPTIMIZER_THREAD_ENV_VARS:
                assert os.environ.get(name) == saved.get(name)
            # But audit should still record the requested_threads
            assert audit.requested_threads == 16


class TestEffectiveThreadsDiffersFromRequested:
    """When effective_threads cannot match requested (e.g., threadpoolctl reports
    fewer), the audit records the actual effective threads."""

    def test_transport_mode_can_record_remote_orchestration(self) -> None:
        with optimizer_cpu_thread_limits(32, transport_mode="remote") as audit:
            assert audit.execution_mode == "local"
            assert audit.transport_mode == "remote"
            assert audit.to_dict()["transport_mode"] == "remote"

    def test_effective_threads_reflects_env_when_set(self) -> None:
        with optimizer_cpu_thread_limits(32) as audit:
            assert audit.effective_threads <= 32
            # All env vars must match the requested value
            for name in OPTIMIZER_THREAD_ENV_VARS:
                assert os.environ.get(name) == "32"

    def test_effective_threads_reduced_by_threadpoolctl(self) -> None:
        fake_lib_info = [
            {
                "user_api": "blas",
                "internal_api": "openblas",
                "num_threads": 16,
                "prefix": "libopenblas",
            }
        ]

        with patch(
            "hermes_workflow.optimizer_resources._capture_threadpoolctl_info",
            return_value=({"available": True, "libraries": []}, []),
        ), patch(
            "hermes_workflow.optimizer_resources._threadpoolctl_info",
            return_value=fake_lib_info,
        ):
            with optimizer_cpu_thread_limits(32) as audit:
                # effective_threads should be min(requested, threadpoolctl actual)
                assert audit.effective_threads == 16
                assert audit.requested_threads == 32
