#!/usr/bin/env python3
"""Promote benchmark results into a baseline JSON for policy comparison."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Dict, Iterable, Set

from evaluate_benchmarks import load_metrics


def collect_policy_metric_keys(policy: Dict[str, object], profile_name: str) -> Set[str]:
    profiles = policy.get("profiles", {})
    if not isinstance(profiles, dict) or profile_name not in profiles:
        available = ", ".join(sorted(profiles.keys())) if isinstance(profiles, dict) else ""
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

    profile = profiles[profile_name]
    if not isinstance(profile, dict):
        raise ValueError(f"Invalid profile structure for '{profile_name}'")

    checks = profile.get("checks", {})
    if not isinstance(checks, dict):
        return set()

    keys: Set[str] = set()
    for cfg in checks.values():
        if not isinstance(cfg, dict):
            continue
        metric_keys = cfg.get("metric_keys", [])
        if isinstance(metric_keys, list):
            for key in metric_keys:
                if isinstance(key, str):
                    keys.add(key)
    return keys


def pick_metrics(
    result_metrics: Dict[str, float],
    desired_keys: Iterable[str],
    include_all: bool,
) -> Dict[str, float]:
    if include_all:
        return dict(sorted(result_metrics.items(), key=lambda kv: kv[0]))

    out: Dict[str, float] = {}
    for key in desired_keys:
        if key in result_metrics:
            out[key] = float(result_metrics[key])
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote benchmark_results.json into a baseline JSON")
    parser.add_argument("--results", required=True, help="Path to benchmark_results.json")
    parser.add_argument("--policy", required=True, help="Path to benchmark policy JSON")
    parser.add_argument("--profile", required=True, help="Policy profile name")
    parser.add_argument("--output", required=True, help="Output baseline JSON path")
    parser.add_argument(
        "--include-all-metrics",
        action="store_true",
        help="Include all parsed metrics (default is only policy-referenced metrics)",
    )
    args = parser.parse_args()

    results_path = Path(args.results).resolve()
    policy_path = Path(args.policy).resolve()
    output_path = Path(args.output).resolve()

    results_doc, result_metrics = load_metrics(results_path)

    policy_doc = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy_doc, dict):
        raise ValueError(f"Expected JSON object at {policy_path}")

    desired_keys = collect_policy_metric_keys(policy_doc, args.profile)
    selected_metrics = pick_metrics(
        result_metrics=result_metrics,
        desired_keys=desired_keys,
        include_all=args.include_all_metrics,
    )

    if not selected_metrics:
        raise ValueError(
            "No metrics selected for baseline. Ensure results contain policy metric keys or use --include-all-metrics."
        )

    metadata = {
        "promoted_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profile": args.profile,
        "source_results": str(results_path),
        "source": {},
    }

    result_meta = results_doc.get("metadata")
    if isinstance(result_meta, dict):
        for key in [
            "timestamp_utc",
            "preset",
            "config",
            "platform",
            "hostname",
            "benchmark_schema_version",
        ]:
            if key in result_meta:
                metadata["source"][key] = result_meta[key]

        git_meta = result_meta.get("git")
        if isinstance(git_meta, dict):
            metadata["source"]["git"] = {
                "commit": git_meta.get("commit", ""),
                "commit_short": git_meta.get("commit_short", ""),
            }

    baseline = {
        "metadata": metadata,
        "metrics": selected_metrics,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote baseline: {output_path}")
    print(f"Metric count: {len(selected_metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
