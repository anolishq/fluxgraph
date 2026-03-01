# Benchmark Policy

This directory defines benchmark evaluation policy profiles and baseline references.

## Files

1. `bench_policy.json`: policy profiles used by `scripts/evaluate_benchmarks.py`.
2. `baseline_template.json`: template for stable-hardware latency baseline.

## Profile Intent

1. `local`: developer machine feedback, no latency hard fail.
2. `ci-hosted`: GitHub runner monitoring, warning-oriented due host variance.
3. `ci-dedicated`: strict gating profile for stable hardware and publication/release evidence.

## Baseline Workflow

1. Run benchmark suite on stable hardware.
2. Copy measured latency metrics into a baseline file derived from `baseline_template.json`.
3. Commit baseline file and reference it with `--baseline` in dedicated-gate runs.
