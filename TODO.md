# FluxGraph - TODO

## CI / Quality

- [ ] Setup precommit hooks for relevant tooling
- [ ] Add `ENABLE_TSAN` CMake option and Linux TSAN validation for embedded + server modes.
- [ ] Add fuzzing targets for YAML/JSON loaders and RPC request parsing surfaces.
- [ ] Add valgrind leak-analysis jobs for server lifecycle and embedded examples.
- [ ] Add benchmark regression tracking in CI (tick loop, signal store, config loaders).
- [ ] Add dependency/CVE scanning workflow for this repository.

## Stress / Scale Validation

- [ ] Run long-duration soak tests (>24h).
- [ ] Run high tick-rate stress (>100 Hz) and large-graph stress (>1000 signals, >100 models).
- [ ] Run multi-provider coordination stress (>10 providers).

## Integration / Docs

- [ ] Add provider restart recovery and network-failure handling examples.
- [ ] Keep one embedded reference example and one service reference example maintained.
- [ ] Publish concise troubleshooting and performance-tuning guides.
