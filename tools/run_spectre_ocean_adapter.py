from __future__ import annotations

import argparse
from pathlib import Path

from hermes_workflow.execution_adapters.spectre_ocean import (
    AdapterPreconditionError,
    run_spectre_ocean_adapter,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the execution-side Spectre + OCEAN adapter.",
    )
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--run-id", default="real_001")
    parser.add_argument("--testbench-id")
    parser.add_argument("--corner-id")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_spectre_ocean_adapter(
            args.project_dir,
            run_id=args.run_id,
            testbench_id=args.testbench_id,
            corner_id=args.corner_id,
            allow_overwrite=args.allow_overwrite,
        )
    except AdapterPreconditionError as exc:
        print(f"failed: {exc}")
        return 2

    print(f"{result.status}: run_id={result.run_id}")
    print(f"result_manifest={result.result_manifest_path}")
    if result.metric_result_manifest_path is not None:
        print(f"metric_result_manifest={result.metric_result_manifest_path}")
    for issue in result.issues:
        print(f"issue: {issue}")
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
