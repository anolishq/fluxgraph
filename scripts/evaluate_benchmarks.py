#!/usr/bin/env python3
"""Evaluate benchmark artifacts against policy profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def flatten_metrics_from_results(doc: Dict[str, object]) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for bench in doc.get("benchmarks", []):
        if not isinstance(bench, dict):
            continue
        target = bench.get("target")
        bench_metrics = bench.get("metrics")
        if not isinstance(target, str) or not isinstance(bench_metrics, dict):
            continue
        for key, value in bench_metrics.items():
            if isinstance(key, str) and _is_number(value):
                metrics[f"{target}.{key}"] = float(value)

        scenarios = bench.get("scenarios")
        if isinstance(scenarios, list):
            for scenario in scenarios:
                if not isinstance(scenario, dict):
                    continue
                scenario_id = scenario.get("id")
                scenario_metrics = scenario.get("metrics")
                if not isinstance(scenario_id, str) or not isinstance(
                    scenario_metrics, dict
                ):
                    continue
                for key, value in scenario_metrics.items():
                    if isinstance(key, str) and _is_number(value):
                        metrics[f"scenario.{scenario_id}.{key}"] = float(value)

    # Backward-compatible aliases for pre-scenario benchmark artifacts.
    legacy_aliases = {
        "benchmark_tick.simple_avg_tick_us": "scenario.tick.simple.v1.avg_tick_us",
        "benchmark_tick.simple_allocations": "scenario.tick.simple.v1.allocations",
        "benchmark_tick.simple_alloc_per_tick": "scenario.tick.simple.v1.alloc_per_tick",
        "benchmark_tick.complex_avg_tick_us": "scenario.tick.complex.v1.avg_tick_us",
        "benchmark_tick.complex_allocations": "scenario.tick.complex.v1.allocations",
        "benchmark_tick.complex_alloc_per_tick": "scenario.tick.complex.v1.alloc_per_tick",
    }
    for src_key, dst_key in legacy_aliases.items():
        if src_key in metrics and dst_key not in metrics:
            metrics[dst_key] = float(metrics[src_key])
    return metrics


def load_metrics(path: Path) -> Tuple[Dict[str, object], Dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")

    # 1) benchmark_results.json format
    if isinstance(data.get("benchmarks"), list):
        return data, flatten_metrics_from_results(data)

    # 2) baseline template format: {"metrics": {...}}
    if isinstance(data.get("metrics"), dict):
        out: Dict[str, float] = {}
        for key, value in data["metrics"].items():
            if isinstance(key, str) and _is_number(value):
                out[key] = float(value)
        return data, out

    # 3) flat map format: {"metric": number}
    out_flat: Dict[str, float] = {}
    for key, value in data.items():
        if isinstance(key, str) and _is_number(value):
            out_flat[key] = float(value)
    if out_flat:
        return data, out_flat

    raise ValueError(
        f"Could not parse metrics from {path}. Expected benchmark_results.json, "
        "a {metrics:{...}} map, or a flat metric map."
    )


def add_issue(
    issues: List[Dict[str, object]],
    severity: str,
    check: str,
    message: str,
    metric_key: str | None = None,
    actual: float | None = None,
    expected: float | None = None,
) -> None:
    entry: Dict[str, object] = {
        "severity": severity,
        "check": check,
        "message": message,
    }
    if metric_key is not None:
        entry["metric_key"] = metric_key
    if actual is not None:
        entry["actual"] = actual
    if expected is not None:
        entry["expected"] = expected
    issues.append(entry)


def evaluate(
    results_doc: Dict[str, object],
    result_metrics: Dict[str, float],
    profile_name: str,
    profile: Dict[str, object],
    baseline_metrics: Dict[str, float],
) -> Dict[str, object]:
    issues: List[Dict[str, object]] = []

    summary = results_doc.get("summary")
    if isinstance(summary, dict):
        execution_failures = int(summary.get("execution_failures", 0))
        if execution_failures > 0:
            add_issue(
                issues,
                severity="error",
                check="execution_failures",
                message=f"Benchmark execution reported {execution_failures} execution failures.",
            )

    checks = profile.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}

    # Check: tick allocation counts
    alloc_cfg = checks.get("tick_alloc_per_tick", {})
    if isinstance(alloc_cfg, dict) and alloc_cfg.get("enabled", False):
        severity = str(alloc_cfg.get("severity", "warning"))
        max_value = float(alloc_cfg.get("max_value", 0.0))
        metric_keys = alloc_cfg.get("metric_keys", [])
        if not isinstance(metric_keys, list):
            metric_keys = []

        for key in metric_keys:
            if not isinstance(key, str):
                continue
            if key not in result_metrics:
                add_issue(
                    issues,
                    severity=severity,
                    check="tick_alloc_per_tick",
                    metric_key=key,
                    message="Metric not found in benchmark results.",
                )
                continue
            actual = float(result_metrics[key])
            if actual > max_value:
                add_issue(
                    issues,
                    severity=severity,
                    check="tick_alloc_per_tick",
                    metric_key=key,
                    actual=actual,
                    expected=max_value,
                    message=f"Allocation metric exceeded max value ({max_value}).",
                )

    # Check: latency regression against baseline
    latency_cfg = checks.get("latency_regression", {})
    if isinstance(latency_cfg, dict) and latency_cfg.get("enabled", False):
        warn_pct = float(latency_cfg.get("warn_pct", 20.0))
        fail_pct = float(latency_cfg.get("fail_pct", 50.0))
        require_baseline = bool(latency_cfg.get("require_baseline", False))
        enforce_fail_threshold = bool(latency_cfg.get("enforce_fail_threshold", False))
        missing_metric_severity = str(
            latency_cfg.get("missing_metric_severity", "error")
        )
        missing_baseline_metric_severity = str(
            latency_cfg.get(
                "missing_baseline_metric_severity",
                "error" if require_baseline else "warning",
            )
        )
        metric_keys = latency_cfg.get("metric_keys", [])
        if not isinstance(metric_keys, list):
            metric_keys = []

        if not baseline_metrics:
            add_issue(
                issues,
                severity="error" if require_baseline else "warning",
                check="latency_regression",
                message="No baseline metrics provided for latency regression check.",
            )
        else:
            for key in metric_keys:
                if not isinstance(key, str):
                    continue
                if key not in result_metrics:
                    add_issue(
                        issues,
                        severity=missing_metric_severity,
                        check="latency_regression",
                        metric_key=key,
                        message="Metric not found in benchmark results.",
                    )
                    continue
                if key not in baseline_metrics:
                    add_issue(
                        issues,
                        severity=missing_baseline_metric_severity,
                        check="latency_regression",
                        metric_key=key,
                        message="Metric not found in baseline data.",
                    )
                    continue

                actual = float(result_metrics[key])
                baseline = float(baseline_metrics[key])
                if baseline <= 0:
                    invalid_baseline_severity = (
                        "error" if require_baseline or enforce_fail_threshold else "warning"
                    )
                    add_issue(
                        issues,
                        severity=invalid_baseline_severity,
                        check="latency_regression",
                        metric_key=key,
                        actual=actual,
                        expected=baseline,
                        message="Baseline metric is non-positive; cannot compute regression percentage.",
                    )
                    continue

                delta_pct = ((actual - baseline) / baseline) * 100.0
                if delta_pct > fail_pct:
                    sev = "error" if enforce_fail_threshold else "warning"
                    add_issue(
                        issues,
                        severity=sev,
                        check="latency_regression",
                        metric_key=key,
                        actual=actual,
                        expected=baseline,
                        message=(
                            f"Latency regression {delta_pct:.2f}% exceeds fail threshold "
                            f"{fail_pct:.2f}%"
                        ),
                    )
                elif delta_pct > warn_pct:
                    add_issue(
                        issues,
                        severity="warning",
                        check="latency_regression",
                        metric_key=key,
                        actual=actual,
                        expected=baseline,
                        message=(
                            f"Latency regression {delta_pct:.2f}% exceeds warning threshold "
                            f"{warn_pct:.2f}%"
                        ),
                    )

    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]

    report = {
        "profile": profile_name,
        "profile_description": profile.get("description", ""),
        "metrics": result_metrics,
        "issue_counts": {
            "errors": len(errors),
            "warnings": len(warnings),
            "total": len(issues),
        },
        "issues": issues,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate benchmark results against policy")
    parser.add_argument("--results", required=True, help="Path to benchmark_results.json")
    parser.add_argument("--policy", required=True, help="Path to benchmark policy JSON")
    parser.add_argument("--profile", required=True, help="Policy profile name")
    parser.add_argument("--baseline", default=None, help="Optional baseline JSON path")
    parser.add_argument("--output", default=None, help="Optional output path for evaluation report JSON")
    args = parser.parse_args()

    results_path = Path(args.results).resolve()
    policy_path = Path(args.policy).resolve()
    baseline_path = Path(args.baseline).resolve() if args.baseline else None
    output_path = Path(args.output).resolve() if args.output else None

    results_doc, result_metrics = load_metrics(results_path)

    policy_doc = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy_doc, dict):
        raise ValueError(f"Expected JSON object at {policy_path}")

    profiles = policy_doc.get("profiles", {})
    if not isinstance(profiles, dict) or args.profile not in profiles:
        available = ", ".join(sorted(profiles.keys())) if isinstance(profiles, dict) else ""
        raise ValueError(
            f"Unknown profile '{args.profile}'. Available profiles: {available}"
        )

    profile = profiles[args.profile]
    if not isinstance(profile, dict):
        raise ValueError(f"Invalid profile structure for '{args.profile}'")

    baseline_metrics: Dict[str, float] = {}
    if baseline_path:
        _, baseline_metrics = load_metrics(baseline_path)

    report = evaluate(
        results_doc=results_doc,
        result_metrics=result_metrics,
        profile_name=args.profile,
        profile=profile,
        baseline_metrics=baseline_metrics,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    errors = int(report["issue_counts"]["errors"])
    warnings = int(report["issue_counts"]["warnings"])
    print(f"Policy profile: {args.profile}")
    print(f"Errors: {errors}")
    print(f"Warnings: {warnings}")

    for issue in report["issues"]:
        sev = str(issue.get("severity", "warning")).upper()
        check = str(issue.get("check", "unknown"))
        msg = str(issue.get("message", ""))
        metric = issue.get("metric_key")
        if metric:
            print(f"[{sev}] {check} ({metric}): {msg}")
        else:
            print(f"[{sev}] {check}: {msg}")

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
