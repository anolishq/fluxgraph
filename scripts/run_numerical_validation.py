#!/usr/bin/env python3
"""Run numerical validation executables and evaluate convergence criteria."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


VALIDATION_TARGET = "validation_thermal_mass"


def run_cmd(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def _emit_captured(label: str, proc: subprocess.CompletedProcess[str]) -> None:
    # The full logs live inside the artifact dir, which is not uploaded when a
    # step fails early, so mirror them into the CI step log for visibility.
    if proc.stdout:
        print(f"----- {label} stdout -----", flush=True)
        print(proc.stdout, flush=True)
    if proc.stderr:
        print(f"----- {label} stderr -----", flush=True)
        print(proc.stderr, flush=True)


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


def pick_executable(build_dir: Path, target: str, config: Optional[str]) -> Optional[Path]:
    ext = ".exe" if os.name == "nt" else ""

    candidates = [
        build_dir / "tests" / "validation" / f"{target}{ext}",
        build_dir / "tests" / f"{target}{ext}",
    ]
    if config:
        candidates.insert(0, build_dir / "tests" / "validation" / config / f"{target}{ext}")
        candidates.insert(1, build_dir / "tests" / config / f"{target}{ext}")

    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path

    globbed = [
        p
        for p in build_dir.glob(f"**/{target}{ext}")
        if p.is_file() and os.access(p, os.X_OK) and "CMakeFiles" not in p.parts
    ]
    if not globbed:
        return None

    def score(path: Path) -> Tuple[int, int, int]:
        in_validation = 1 if "validation" in path.parts else 0
        in_tests = 1 if "tests" in path.parts else 0
        in_config = 1 if config and config in path.parts else 0
        shorter = -len(str(path))
        return (in_validation + in_tests, in_config, shorter)

    globbed.sort(key=score, reverse=True)
    return globbed[0]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def default_output_dir(repo_root: Path, preset: str) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return repo_root / "artifacts" / "validation" / f"{ts}_{preset}"


def git_metadata(repo_root: Path) -> Dict[str, object]:
    commit = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    short = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    dirty = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return {
        "commit": (commit.stdout or "").strip(),
        "commit_short": (short.stdout or "").strip(),
        "dirty": bool((dirty.stdout or "").strip()),
    }


def as_number(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def extract_min_orders(results_doc: Dict[str, object]) -> Tuple[float, float]:
    summary_obj = results_doc.get("summary")
    if not isinstance(summary_obj, dict):
        raise ValueError("Validation results missing summary object")

    min_orders_obj = summary_obj.get("min_observed_order_linf")
    if not isinstance(min_orders_obj, dict):
        raise ValueError("Validation results missing summary.min_observed_order_linf")

    euler_raw = min_orders_obj.get("forward_euler")
    rk4_raw = min_orders_obj.get("rk4")
    euler = as_number(euler_raw)
    rk4 = as_number(rk4_raw)
    if euler is None or rk4 is None:
        raise ValueError("Validation results contain non-numeric order values")
    return (euler, rk4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run numerical validation and evaluate orders")
    parser.add_argument("--preset", default=("dev-windows-release" if os.name == "nt" else "dev-release"))
    parser.add_argument("--config", default=None, help="Build configuration for multi-config generators")
    parser.add_argument("--build-dir", default=None, help="Override build directory")
    parser.add_argument("--output-dir", default=None, help="Artifact output directory")
    parser.add_argument("--no-build", action="store_true", help="Skip configure/build and run existing executable")
    parser.add_argument("--duration-s", type=float, default=10.0, help="Simulation duration in seconds")
    parser.add_argument(
        "--dt-values",
        default="0.4,0.2,0.1,0.05,0.025",
        help="Comma-separated dt values used by validation executable",
    )
    parser.add_argument("--min-order-forward-euler", type=float, default=0.9)
    parser.add_argument("--min-order-rk4", type=float, default=3.5)
    parser.add_argument(
        "--enforce-order",
        action="store_true",
        help="Return non-zero when observed order is below threshold",
    )
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
    build_cmd.extend(["--target", VALIDATION_TARGET])

    if not args.no_build:
        cfg = run_cmd(configure_cmd, cwd=repo_root)
        (output_dir / "configure.stdout.log").write_text(cfg.stdout or "", encoding="utf-8")
        (output_dir / "configure.stderr.log").write_text(cfg.stderr or "", encoding="utf-8")
        if cfg.returncode != 0:
            print("Configure failed. See configure logs in", output_dir)
            _emit_captured("configure", cfg)
            return cfg.returncode

        bld = run_cmd(build_cmd, cwd=repo_root)
        (output_dir / "build.stdout.log").write_text(bld.stdout or "", encoding="utf-8")
        (output_dir / "build.stderr.log").write_text(bld.stderr or "", encoding="utf-8")
        if bld.returncode != 0:
            print("Build failed. See build logs in", output_dir)
            _emit_captured("build", bld)
            return bld.returncode

    exe = pick_executable(build_dir, VALIDATION_TARGET, config)
    if exe is None:
        print(f"Validation executable '{VALIDATION_TARGET}' was not found in {build_dir}")
        return 2

    results_json_path = output_dir / "validation_results.json"
    results_csv_path = output_dir / "validation_results.csv"
    cmd = [
        str(exe),
        "--output-json",
        str(results_json_path),
        "--output-csv",
        str(results_csv_path),
        "--duration-s",
        str(args.duration_s),
        "--dt-values",
        args.dt_values,
    ]
    run = run_cmd(cmd, cwd=repo_root)
    (output_dir / "validation.stdout.log").write_text(run.stdout or "", encoding="utf-8")
    (output_dir / "validation.stderr.log").write_text(run.stderr or "", encoding="utf-8")
    if run.returncode != 0:
        print("Validation executable failed. See validation logs in", output_dir)
        return run.returncode

    raw_doc = json.loads(results_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_doc, dict):
        raise ValueError("Validation results JSON must be an object")
    observed_euler, observed_rk4 = extract_min_orders(raw_doc)

    euler_ok = observed_euler >= args.min_order_forward_euler
    rk4_ok = observed_rk4 >= args.min_order_rk4
    overall_ok = euler_ok and rk4_ok

    evaluation = {
        "thresholds": {
            "forward_euler_min_order_linf": args.min_order_forward_euler,
            "rk4_min_order_linf": args.min_order_rk4,
            "enforce_order": args.enforce_order,
        },
        "observed": {
            "forward_euler_min_order_linf": observed_euler,
            "rk4_min_order_linf": observed_rk4,
        },
        "checks": {
            "forward_euler": euler_ok,
            "rk4": rk4_ok,
            "overall": overall_ok,
        },
        "run": {
            "preset": args.preset,
            "config": config,
            "multi_config": multi_config,
            "build_dir": str(build_dir),
            "output_dir": str(output_dir),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "hostname": socket.gethostname(),
            "git": git_metadata(repo_root),
            "command": " ".join(shlex.quote(part) for part in cmd),
        },
    }
    (output_dir / "validation_evaluation.json").write_text(
        json.dumps(evaluation, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Validation artifacts written to: {output_dir}")
    print(f"Results manifest: {results_json_path}")
    print(f"Observed min order (forward_euler, linf): {observed_euler:.6f}")
    print(f"Observed min order (rk4, linf): {observed_rk4:.6f}")

    if args.enforce_order and not overall_ok:
        print("Convergence order thresholds failed.")
        return 1

    if not overall_ok:
        print("Convergence thresholds not met (non-fatal without --enforce-order).")
    else:
        print("Convergence thresholds satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
