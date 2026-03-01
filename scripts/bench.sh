#!/usr/bin/env bash
# FluxGraph benchmark wrapper (preset-first)
# Usage:
#   ./scripts/bench.sh [--preset <name>] [--config <cfg>] [--output-dir <path>] [--include-optional]
#                     [--no-build] [--fail-on-status] [--policy-profile <name>]
#                     [--policy-file <path>] [--baseline <path>] [--no-evaluate]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PRESET="dev-release"
CONFIG=""
OUTPUT_DIR=""
EXTRA_ARGS=()
POLICY_PROFILE="local"
POLICY_FILE=""
BASELINE_FILE=""
EVALUATE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preset)
      PRESET="$2"
      shift 2
      ;;
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --include-optional|--no-build|--fail-on-status)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    --policy-profile)
      POLICY_PROFILE="$2"
      shift 2
      ;;
    --policy-file)
      POLICY_FILE="$2"
      shift 2
      ;;
    --baseline)
      BASELINE_FILE="$2"
      shift 2
      ;;
    --no-evaluate)
      EVALUATE=0
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--preset <name>] [--config <cfg>] [--output-dir <path>] [--include-optional] [--no-build] [--fail-on-status] [--policy-profile <name>] [--policy-file <path>] [--baseline <path>] [--no-evaluate]"
      exit 0
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -n "${VCPKG_ROOT:-}" ]]; then
  :
else
  echo "WARNING: VCPKG_ROOT is not set. Presets may fail to configure." >&2
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_DIR="$REPO_ROOT/artifacts/benchmarks/${TS}_${PRESET}"
elif [[ "$OUTPUT_DIR" != /* ]]; then
  OUTPUT_DIR="$REPO_ROOT/$OUTPUT_DIR"
fi

if [[ -z "$POLICY_FILE" ]]; then
  POLICY_FILE="$REPO_ROOT/benchmarks/policy/bench_policy.json"
elif [[ "$POLICY_FILE" != /* ]]; then
  POLICY_FILE="$REPO_ROOT/$POLICY_FILE"
fi

CMD=(python3 "$SCRIPT_DIR/run_benchmarks.py" --preset "$PRESET")
if [[ -n "$CONFIG" ]]; then
  CMD+=(--config "$CONFIG")
fi
CMD+=(--output-dir "$OUTPUT_DIR")
CMD+=("${EXTRA_ARGS[@]}")

cd "$REPO_ROOT"
echo "[BENCH] ${CMD[*]}"
"${CMD[@]}"

if [[ "$EVALUATE" -eq 1 ]]; then
  EVAL_CMD=(
    python3 "$SCRIPT_DIR/evaluate_benchmarks.py"
    --results "$OUTPUT_DIR/benchmark_results.json"
    --policy "$POLICY_FILE"
    --profile "$POLICY_PROFILE"
    --output "$OUTPUT_DIR/benchmark_evaluation.json"
  )
  if [[ -n "$BASELINE_FILE" ]]; then
    if [[ "$BASELINE_FILE" != /* ]]; then
      BASELINE_FILE="$REPO_ROOT/$BASELINE_FILE"
    fi
    EVAL_CMD+=(--baseline "$BASELINE_FILE")
  fi
  echo "[EVAL] ${EVAL_CMD[*]}"
  "${EVAL_CMD[@]}"
fi
