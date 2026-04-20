# Contributing to FluxGraph

Thanks for contributing.

FluxGraph is part of the Anolis ecosystem. For shared organization-level engineering and governance context, see:  
<https://github.com/anolishq/>

## Local Development

Prerequisites:

1. CMake 3.20+
2. C++17 toolchain
3. `VCPKG_ROOT` configured

Typical loop:

```bash
cmake --preset dev-release
cmake --build --preset dev-release
ctest --preset dev-release --output-on-failure
```

Windows:

```powershell
cmake --preset dev-windows-release
cmake --build --preset dev-windows-release --config Release
ctest --preset dev-windows-release -C Release --output-on-failure
```

## Pull Request Expectations

1. Keep changes scoped and cohesive.
2. Add/update tests for behavioral changes.
3. Update relevant docs for public-surface changes.
4. Keep core dependency boundaries intact (see `docs/dependencies.md`).
5. Ensure CI is green before merge.

## Design and Semantics References

1. `docs/semantics_spec.md`
2. `docs/numerical-methods.md`
3. `docs/graph-visualization.md`
4. `docs/dependencies.md`
