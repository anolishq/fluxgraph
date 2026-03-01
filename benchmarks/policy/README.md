# Benchmark Policy

This directory defines benchmark evaluation policy profiles and baseline references.

## Files

1. `bench_policy.json`: policy profiles used by `scripts/evaluate_benchmarks.py`.
2. `baseline_template.json`: template for stable-hardware latency baseline.
3. `baselines/`: committed baseline references by environment/profile.

## Profile Intent

1. `local`: developer machine feedback, no latency hard fail.
2. `ci-hosted`: GitHub runner monitoring, warning-oriented due host variance.
3. `ci-dedicated`: strict gating profile for stable hardware and publication/release evidence.

## Baseline Workflow

1. Run benchmark suite on stable hardware.
2. Promote artifact metrics into a baseline file:
   - `python scripts/promote_benchmark_baseline.py --results <artifact>/benchmark_results.json --policy benchmarks/policy/bench_policy.json --profile ci-hosted --output benchmarks/policy/baselines/ci-hosted.windows-2022.json`
3. Commit baseline file and reference it with `--baseline` in dedicated-gate runs.

## Current Baseline Files

1. `baselines/ci-hosted.windows-2022.json`: hosted-runner reference baseline (warning-oriented profile).
2. `baselines/ci-dedicated.windows-2022.template.json`: template for strict dedicated-runner baseline.
