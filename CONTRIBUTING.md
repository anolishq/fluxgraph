# Contributing to FluxGraph

Thanks for contributing.

FluxGraph is part of the Anolis ecosystem. For shared organization-level engineering and governance context, see:  
<https://github.com/anolishq/>

## Local Development

Prerequisites:

1. CMake 3.20+ (4.2+ for the Windows presets)
2. C++20 toolchain with `std::format` (GCC 13+, Clang 17+ with libc++ 17+ or libstdc++ 13+, MSVC 19.32+)
3. `VCPKG_ROOT` configured

Typical loop:

```bash
cmake --preset dev-release
cmake --build --preset dev-release
ctest --preset dev-release --output-on-failure
```

Windows (the presets use the `Visual Studio 18 2026` generator, added in CMake 4.2, with toolset
`v145`, so they need Visual Studio 2026 and CMake 4.2+):

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
