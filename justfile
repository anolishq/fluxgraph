# Shared task runner for anolis providers. Copy to `justfile` at the repo root and
# set `preset` to the repo's primary CMake configure/test preset.
#
# Standard recipes (match the org convention): setup, fmt, fmt-check, lint, check, test.
#
# `fmt`/`fmt-check`/`lint` call `clang-format`/`clang-tidy` on PATH. The org pins
# those to a SHA-verified static LLVM 18.1.8 build — installed in CI by the
# `setup-clang-tools` action and on dev boxes by workstation-configs
# `apps/clang-tools` — so dev, editor, and CI run byte-identical bits. Do NOT use
# the distro/apt clang-format here (it drifts: Debian 18.1.8 vs Ubuntu 18.1.3).

# Primary CMake preset — override per repo (e.g. ci-linux-release).
preset := "ci-linux-release"

# C++ sources tracked by git (excludes generated build/ output).
cpp_files := "git ls-files '*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx'"

# List available recipes.
default:
    @just --list

# Configure (vcpkg deps resolve during CMake configure).
setup:
    cmake --preset {{preset}}

# Format C++ sources in place (pinned clang-format 18.1.8).
fmt:
    {{cpp_files}} | xargs clang-format -i

# Verify formatting without modifying files (CI gate; pinned clang-format 18.1.8).
fmt-check:
    {{cpp_files}} | xargs clang-format --dry-run --Werror

# Static analysis over the compile database (pinned clang-tidy 18.1.8; needs a
# configured build dir with CMAKE_EXPORT_COMPILE_COMMANDS=ON).
lint:
    run-clang-tidy -p build/{{preset}} $({{cpp_files}})

# CI-equivalent: formatting + lint.
check: fmt-check lint

# Build and run the test suite.
test:
    cmake --build --preset {{preset}} --parallel
    ctest --preset {{preset}} --output-on-failure
