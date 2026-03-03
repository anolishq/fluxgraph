#!/usr/bin/env python3
"""Run strict dimensional validation tests and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_REGEX = (
    r"(GraphCompilerTest\.(StrictMode.*|PermissiveModeEmitsLinearBoundaryWarning)"
    r"|UnitRegistryTest\..*"
    r"|UnitConvertTransformTest\..*"
    r"|EngineTest\.EdgePropagationUsesTargetContractUnit"
    r"|SignalStoreTest\.(WriteWithContractUnitUsesDeclaredContract|DeclareUnitRejectsConflictingRedefinition))"
)


def run_cmd(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def cmake_is_multi_config(preset: str, repo_root: Path) -> bool:
    result = run_cmd(["cmake", "--preset", preset, "-N", "-LA"], cwd=repo_root)
    blob = (result.stdout or "") + "\n" + (result.stderr or "")
    return "CMAKE_CONFIGURATION_TYPES" in blob


def resolve_build_dir(repo_root: Path, preset: str, override: Optional[Path]) -> Path:
    if override:
        return override.resolve()

    special = {
        "ci-linux-release-server": repo_root / "build-server",
        "dev-windows-server": repo_root / "build-windows-server",
        "ci-windows-release-server": repo_root / "build-windows-server-release",
    }
    if preset in special:
        return special[preset]
    return (repo_root / "build" / preset).resolve()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def default_output_dir(repo_root: Path, preset: str) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return repo_root / "artifacts" / "dimensional-validation" / f"{ts}_{preset}"


def parse_total_tests(ctest_list_stdout: str) -> int:
    pattern = re.compile(r"Total Tests:\s+(\d+)")
    match = pattern.search(ctest_list_stdout)
    if not match:
        return 0
    return int(match.group(1))


def git_metadata(repo_root: Path) -> Dict[str, object]:
    commit = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    short = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    describe = run_cmd(["git", "describe", "--tags", "--always"], cwd=repo_root)
    dirty = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return {
        "commit": (commit.stdout or "").strip(),
        "commit_short": (short.stdout or "").strip(),
        "describe": (describe.stdout or "").strip(),
        "dirty": bool((dirty.stdout or "").strip()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict dimensional validation tests and emit evidence artifacts.")
    parser.add_argument("--preset", default=("dev-windows-release" if os.name == "nt" else "dev-release"))
    parser.add_argument("--config", default=None, help="Build configuration for multi-config generators")
    parser.add_argument("--build-dir", default=None, help="Override build directory")
    parser.add_argument("--output-dir", default=None, help="Artifact output directory")
    parser.add_argument("--target", default="fluxgraph_tests", help="Build target containing dimensional tests")
    parser.add_argument("--regex", default=DEFAULT_REGEX, help="CTest regex selecting dimensional validation tests")
    parser.add_argument("--no-build", action="store_true", help="Skip configure/build and run existing tests")
    parser.add_argument("--enforce", action="store_true", help="Return non-zero when validation tests fail")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    build_dir = resolve_build_dir(repo_root, args.preset, Path(args.build_dir) if args.build_dir else None)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else default_output_dir(repo_root, args.preset)
    ensure_dir(output_dir)

    multi_config = cmake_is_multi_config(args.preset, repo_root)
    config = args.config
    if multi_config and not config:
        config = "Release"

    configure_cmd = ["cmake", "--preset", args.preset]
    build_cmd = ["cmake", "--build", "--preset", args.preset]
    if config:
        build_cmd.extend(["--config", config])
    build_cmd.extend(["--target", args.target])

    if not args.no_build:
        cfg = run_cmd(configure_cmd, cwd=repo_root)
        (output_dir / "configure.stdout.log").write_text(cfg.stdout or "", encoding="utf-8")
        (output_dir / "configure.stderr.log").write_text(cfg.stderr or "", encoding="utf-8")
        if cfg.returncode != 0:
            print("Configure failed. See configure logs in", output_dir)
            return cfg.returncode

        bld = run_cmd(build_cmd, cwd=repo_root)
        (output_dir / "build.stdout.log").write_text(bld.stdout or "", encoding="utf-8")
        (output_dir / "build.stderr.log").write_text(bld.stderr or "", encoding="utf-8")
        if bld.returncode != 0:
            print("Build failed. See build logs in", output_dir)
            return bld.returncode

    ctest_list_cmd = ["ctest", "--preset", args.preset, "-N", "-R", args.regex]
    if config:
        ctest_list_cmd.extend(["-C", config])
    list_result = run_cmd(ctest_list_cmd, cwd=repo_root)
    (output_dir / "ctest_list.stdout.log").write_text(list_result.stdout or "", encoding="utf-8")
    (output_dir / "ctest_list.stderr.log").write_text(list_result.stderr or "", encoding="utf-8")
    selected_tests = parse_total_tests(list_result.stdout or "")

    junit_path = output_dir / "dimensional_validation_junit.xml"
    ctest_cmd = [
        "ctest",
        "--preset",
        args.preset,
        "--output-on-failure",
        "-R",
        args.regex,
        "--output-junit",
        str(junit_path),
    ]
    if config:
        ctest_cmd.extend(["-C", config])

    run = run_cmd(ctest_cmd, cwd=repo_root)
    (output_dir / "ctest_dimensional.stdout.log").write_text(run.stdout or "", encoding="utf-8")
    (output_dir / "ctest_dimensional.stderr.log").write_text(run.stderr or "", encoding="utf-8")

    passed = run.returncode == 0 and selected_tests > 0
    evaluation = {
        "schema_version": 1,
        "validation": "strict-dimensional",
        "selected_test_count": selected_tests,
        "checks": {
            "ctest_passed": run.returncode == 0,
            "selected_tests_nonzero": selected_tests > 0,
            "overall": passed,
        },
        "run": {
            "preset": args.preset,
            "config": config,
            "multi_config": multi_config,
            "build_dir": str(build_dir),
            "output_dir": str(output_dir),
            "regex": args.regex,
            "target": args.target,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "hostname": socket.gethostname(),
            "git": git_metadata(repo_root),
            "commands": {
                "configure": " ".join(shlex.quote(part) for part in configure_cmd),
                "build": " ".join(shlex.quote(part) for part in build_cmd),
                "ctest_list": " ".join(shlex.quote(part) for part in ctest_list_cmd),
                "ctest_run": " ".join(shlex.quote(part) for part in ctest_cmd),
            },
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "artifacts": {
            "junit_xml": str(junit_path),
            "ctest_stdout_log": str(output_dir / "ctest_dimensional.stdout.log"),
            "ctest_stderr_log": str(output_dir / "ctest_dimensional.stderr.log"),
        },
    }

    evaluation_path = output_dir / "dimensional_validation_evaluation.json"
    evaluation_path.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")

    print(f"Dimensional validation artifacts written to: {output_dir}")
    print(f"Selected tests: {selected_tests}")
    print(f"JUnit report: {junit_path}")
    print(f"Evaluation JSON: {evaluation_path}")

    if args.enforce and not passed:
        print("Dimensional validation failed.")
        return 1
    if not passed:
        print("Dimensional validation reported failures (non-fatal without --enforce).")
    else:
        print("Dimensional validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
