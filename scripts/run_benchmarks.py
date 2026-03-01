#!/usr/bin/env python3
"""Run FluxGraph benchmark executables and emit reproducible artifacts.

Usage examples:
  python scripts/run_benchmarks.py --preset dev-release
  python scripts/run_benchmarks.py --preset dev-windows-release --config Release
"""

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
import time
from pathlib import Path
from typing import Dict, List, Optional


BENCHMARK_TARGETS = [
    "benchmark_signal_store",
    "benchmark_namespace",
    "benchmark_tick",
]

OPTIONAL_TARGETS = [
    "json_loader_bench",
    "yaml_loader_bench",
]


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

    # Most presets use build/<preset>. Keep explicit map for known exceptions.
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

    direct_candidates = [
        build_dir / "tests" / target / f"{target}{ext}",
        build_dir / "tests" / f"{target}{ext}",
    ]
    if config:
        direct_candidates.insert(0, build_dir / "tests" / config / f"{target}{ext}")

    for path in direct_candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path

    pattern = f"**/{target}{ext}"
    candidates = [
        p for p in build_dir.glob(pattern) if p.is_file() and os.access(p, os.X_OK) and "CMakeFiles" not in p.parts
    ]
    if not candidates:
        return None

    def score(path: Path) -> tuple[int, int, int]:
        # Higher score is better.
        in_tests = 1 if "tests" in path.parts else 0
        in_config = 1 if config and config in path.parts else 0
        shorter = -len(str(path))
        return (in_tests, in_config, shorter)

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def parse_status(stdout_text: str) -> Dict[str, object]:
    lines = re.findall(r"^\s*Status:\s*(PASS|FAIL)\s*$", stdout_text, flags=re.MULTILINE)
    if not lines:
        return {"status": "unknown", "status_lines": []}

    overall = "pass" if all(s == "PASS" for s in lines) else "fail"
    return {"status": overall, "status_lines": lines}


def parse_metrics(target: str, stdout_text: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}

    if target == "benchmark_signal_store":
        read_match = re.search(
            r"SignalStore Reads:.*?Duration:\s*([0-9]+)\s*ms",
            stdout_text,
            flags=re.DOTALL,
        )
        write_match = re.search(
            r"SignalStore Writes:.*?Duration:\s*([0-9]+)\s*ms",
            stdout_text,
            flags=re.DOTALL,
        )
        if read_match:
            metrics["read_duration_ms"] = float(read_match.group(1))
        if write_match:
            metrics["write_duration_ms"] = float(write_match.group(1))

    elif target == "benchmark_namespace":
        intern_match = re.search(
            r"Namespace Intern:.*?Duration:\s*([0-9]+)\s*ms",
            stdout_text,
            flags=re.DOTALL,
        )
        resolve_match = re.search(
            r"Namespace Resolve:.*?Duration:\s*([0-9]+)\s*ms",
            stdout_text,
            flags=re.DOTALL,
        )
        if intern_match:
            metrics["intern_duration_ms"] = float(intern_match.group(1))
        if resolve_match:
            metrics["resolve_duration_ms"] = float(resolve_match.group(1))

    elif target == "benchmark_tick":
        simple_match = re.search(
            r"Simple Graph.*?Avg/tick:\s*([0-9.]+)\s*us.*?"
            r"Allocations:\s*([0-9]+).*?"
            r"Alloc/tick:\s*([0-9.]+)",
            stdout_text,
            flags=re.DOTALL,
        )
        complex_match = re.search(
            r"Complex Graph.*?Avg/tick:\s*([0-9.]+)\s*us.*?"
            r"Allocations:\s*([0-9]+).*?"
            r"Alloc/tick:\s*([0-9.]+)",
            stdout_text,
            flags=re.DOTALL,
        )
        if simple_match:
            metrics["simple_avg_tick_us"] = float(simple_match.group(1))
            metrics["simple_allocations"] = float(simple_match.group(2))
            metrics["simple_alloc_per_tick"] = float(simple_match.group(3))
        if complex_match:
            metrics["complex_avg_tick_us"] = float(complex_match.group(1))
            metrics["complex_allocations"] = float(complex_match.group(2))
            metrics["complex_alloc_per_tick"] = float(complex_match.group(3))

    return metrics


def build_scenarios(target: str, metrics: Dict[str, float]) -> List[Dict[str, object]]:
    scenarios: List[Dict[str, object]] = []

    if target == "benchmark_signal_store":
        if "read_duration_ms" in metrics:
            scenarios.append(
                {
                    "id": "signal_store.read.v1",
                    "metrics": {"duration_ms": float(metrics["read_duration_ms"])},
                }
            )
        if "write_duration_ms" in metrics:
            scenarios.append(
                {
                    "id": "signal_store.write.v1",
                    "metrics": {"duration_ms": float(metrics["write_duration_ms"])},
                }
            )
    elif target == "benchmark_namespace":
        if "intern_duration_ms" in metrics:
            scenarios.append(
                {
                    "id": "namespace.intern.v1",
                    "metrics": {"duration_ms": float(metrics["intern_duration_ms"])},
                }
            )
        if "resolve_duration_ms" in metrics:
            scenarios.append(
                {
                    "id": "namespace.resolve.v1",
                    "metrics": {"duration_ms": float(metrics["resolve_duration_ms"])},
                }
            )
    elif target == "benchmark_tick":
        if "simple_avg_tick_us" in metrics:
            scenarios.append(
                {
                    "id": "tick.simple.v1",
                    "metrics": {
                        "avg_tick_us": float(metrics["simple_avg_tick_us"]),
                        "allocations": float(metrics.get("simple_allocations", 0.0)),
                        "alloc_per_tick": float(metrics.get("simple_alloc_per_tick", 0.0)),
                    },
                }
            )
        if "complex_avg_tick_us" in metrics:
            scenarios.append(
                {
                    "id": "tick.complex.v1",
                    "metrics": {
                        "avg_tick_us": float(metrics["complex_avg_tick_us"]),
                        "allocations": float(metrics.get("complex_allocations", 0.0)),
                        "alloc_per_tick": float(metrics.get("complex_alloc_per_tick", 0.0)),
                    },
                }
            )

    return scenarios


def git_metadata(repo_root: Path) -> Dict[str, object]:
    commit = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    short = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    dirty = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    return {
        "commit": (commit.stdout or "").strip(),
        "commit_short": (short.stdout or "").strip(),
        "dirty": bool((dirty.stdout or "").strip()),
    }


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def default_output_dir(repo_root: Path, preset: str) -> Path:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return repo_root / "artifacts" / "benchmarks" / f"{ts}_{preset}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run FluxGraph benchmarks and collect artifacts.")
    parser.add_argument("--preset", default=("dev-windows-release" if os.name == "nt" else "dev-release"))
    parser.add_argument(
        "--config", default=None, help="Build configuration for multi-config generators (e.g., Release)"
    )
    parser.add_argument("--build-dir", default=None, help="Override build directory")
    parser.add_argument("--output-dir", default=None, help="Artifact output directory")
    parser.add_argument("--no-build", action="store_true", help="Skip configure/build and run existing binaries")
    parser.add_argument("--include-optional", action="store_true", help="Attempt optional loader benchmarks too")
    parser.add_argument(
        "--fail-on-status",
        action="store_true",
        help="Return non-zero if any benchmark reports Status: FAIL",
    )
    parser.add_argument("--timeout-sec", type=int, default=300)
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

    targets = list(BENCHMARK_TARGETS)
    if args.include_optional:
        targets.extend(OPTIONAL_TARGETS)

    build_cmd.extend(["--target", *targets])

    run_records: List[Dict[str, object]] = []

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

    for target in targets:
        exe = pick_executable(build_dir, target, config)
        if exe is None:
            run_records.append(
                {
                    "target": target,
                    "skipped": True,
                    "reason": "executable-not-found",
                }
            )
            continue

        cmd = [str(exe)]
        start = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(repo_root),
                text=True,
                capture_output=True,
                timeout=args.timeout_sec,
                check=False,
            )
            duration_sec = time.perf_counter() - start
            stdout_text = proc.stdout or ""
            stderr_text = proc.stderr or ""
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            duration_sec = time.perf_counter() - start
            timed_out = True
            stdout_text = exc.stdout or ""
            stderr_text = exc.stderr or ""
            exit_code = 124

        out_path = output_dir / f"{target}.stdout.log"
        err_path = output_dir / f"{target}.stderr.log"
        out_path.write_text(stdout_text, encoding="utf-8")
        err_path.write_text(stderr_text, encoding="utf-8")

        status = parse_status(stdout_text)
        metrics = parse_metrics(target, stdout_text)
        scenarios = build_scenarios(target, metrics)
        run_records.append(
            {
                "target": target,
                "executable": str(exe),
                "command": " ".join(shlex.quote(c) for c in cmd),
                "exit_code": exit_code,
                "duration_sec": round(duration_sec, 6),
                "timed_out": timed_out,
                "stdout_log": out_path.name,
                "stderr_log": err_path.name,
                "status": status["status"],
                "status_lines": status["status_lines"],
                "metrics": metrics,
                "scenarios": scenarios,
            }
        )

    metadata = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "preset": args.preset,
        "config": config,
        "multi_config": multi_config,
        "build_dir": str(build_dir),
        "output_dir": str(output_dir),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "git": git_metadata(repo_root),
        "targets_requested": targets,
        "fail_on_status": args.fail_on_status,
        "benchmark_schema_version": 2,
    }

    status_failures = [r for r in run_records if r.get("status") == "fail"]
    execution_failures = [r for r in run_records if r.get("exit_code", 0) != 0]

    summary = {
        "total": len(run_records),
        "status_failures": len(status_failures),
        "execution_failures": len(execution_failures),
        "scenario_count": sum(len(r.get("scenarios", [])) for r in run_records),
    }

    result = {
        "metadata": metadata,
        "summary": summary,
        "benchmarks": run_records,
    }

    result_file = output_dir / "benchmark_results.json"
    result_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    missing_required = [r["target"] for r in run_records if r.get("skipped") and r.get("target") in BENCHMARK_TARGETS]

    print(f"Benchmark artifacts written to: {output_dir}")
    print(f"Results manifest: {result_file}")

    if missing_required:
        print(
            "Missing required benchmark executable(s):",
            ", ".join(missing_required),
        )
        print("Build benchmarks first or rerun without --no-build.")
        return 2

    if execution_failures:
        print(f"Benchmark run completed with {len(execution_failures)} execution failure(s).")
        return 1

    if status_failures:
        print(f"Benchmark run completed with {len(status_failures)} status failure(s).")
        if args.fail_on_status:
            return 1
        print("Status failures were reported but did not fail the run (use --fail-on-status to enforce).")
        return 0

    print("Benchmark run completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
