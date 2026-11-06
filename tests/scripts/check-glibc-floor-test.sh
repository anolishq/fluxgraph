#!/usr/bin/env bash
# Tests for scripts/check-glibc-floor.sh. Runs anywhere with bash, objdump and coreutils:
#   bash tests/scripts/check-glibc-floor-test.sh
# Fixture cases feed canned `objdump -T` output through the script's OBJDUMP hook;
# real-binary cases use this shell's own executable with floors far below / above it,
# so they do not depend on the host's glibc version.

set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="$repo_root/scripts/check-glibc-floor.sh"
work="$(mktemp -d)" || {
    echo "error: mktemp -d failed; cannot create the test's work directory" >&2
    exit 1
}
if [ -z "$work" ] || [ ! -d "$work" ]; then
    echo "error: mktemp -d returned no usable directory ('$work')" >&2
    exit 1
fi
trap 'rm -rf "$work"' EXIT

pass=0
fail=0

# expect <want-rc> <name> <command...>
# Optional: set EXPECT_OUT / EXPECT_NOT_OUT to a fixed string the output must / must not contain.
expect() {
    local want="$1" name="$2" out rc ok=1
    shift 2
    out="$("$@" 2>&1)"
    rc=$?
    [ "$rc" = "$want" ] || ok=0
    if [ -n "${EXPECT_OUT:-}" ] && [[ "$out" != *"$EXPECT_OUT"* ]]; then ok=0; fi
    if [ -n "${EXPECT_NOT_OUT:-}" ] && [[ "$out" == *"$EXPECT_NOT_OUT"* ]]; then ok=0; fi
    if [ "$ok" = 1 ]; then
        echo "PASS [$name] rc=$rc"
        pass=$((pass + 1))
    else
        echo "FAIL [$name] want rc=$want${EXPECT_OUT:+, output containing \"$EXPECT_OUT\"}${EXPECT_NOT_OUT:+, output without \"$EXPECT_NOT_OUT\"}; got rc=$rc"
        printf '%s\n' "$out" | sed 's/^/    | /'
        fail=$((fail + 1))
    fi
}

# Fake objdump: prints the fixture whose name is the basename of the binary it is
# given (its last argument), so each fake binary gets its own symbol table.
mkdir -p "$work/fixtures" "$work/bin"
fake="$work/fake-objdump"
# shellcheck disable=SC2016 # the expressions must expand when the fake runs, not here
printf '#!/usr/bin/env bash\ncat "$FIXTURES/$(basename "${!#}")"\n' >"$fake"
chmod +x "$fake"

# fixture <name> <version-tag>... : writes an `objdump -T`-shaped file, one symbol per
# tag, and an empty placeholder binary $work/bin/<name> for the script to be given.
fixture() {
    local name="$1" tag
    shift
    {
        printf '\nfakebin:     file format elf64-x86-64\n\nDYNAMIC SYMBOL TABLE:\n'
        for tag in "$@"; do
            printf '0000000000000000      DF *UND*  0000000000000000 (%s) sym_%s\n' "$tag" "$tag"
        done
    } >"$work/fixtures/$name"
    : >"$work/bin/$name"
}

# check <binary-name>... : runs the script on the named fake binaries.
check() {
    local args=() name
    for name in "$@"; do args+=("$work/bin/$name"); done
    OBJDUMP="$fake" FIXTURES="$work/fixtures" bash "$script" "${args[@]}"
}

target="$work/bin/at-floor"

fixture at-floor GLIBC_2.2.5 GLIBC_2.41 GLIBC_PRIVATE GLIBCXX_3.4.33 CXXABI_1.3.15
fixture glibc-over GLIBC_2.34 GLIBC_2.42
fixture glibcxx-over GLIBC_2.34 GLIBCXX_3.4.34
fixture cxxabi-over GLIBC_2.34 GLIBCXX_3.4.30 CXXABI_1.3.16
fixture short-versions GLIBC_2.5 GLIBCXX_3.4.9 CXXABI_1.3.9
fixture no-glibc GLIBCXX_3.4.30

expect 0 "exactly at the Debian 13 floor passes; GLIBC_PRIVATE ignored" check at-floor
expect 1 "GLIBC_2.42 fails" check glibc-over
expect 1 "GLIBCXX_3.4.34 fails" check glibcxx-over
expect 1 "CXXABI_1.3.16 fails" check cxxabi-over
expect 0 "2.5 < 2.41 and 3.4.9 < 3.4.33 compare as versions" check short-versions
expect 2 "no GLIBC_ versions at all is an error" check no-glibc
expect 0 "two binaries, both within the floor: passes" check at-floor short-versions
EXPECT_OUT="glibc-over needs GLIBC_2.42" EXPECT_NOT_OUT="at-floor needs" \
    expect 1 "two binaries, one within and one over: fails on the over one only" check at-floor glibc-over
EXPECT_OUT="glibc-over needs GLIBC_2.42" EXPECT_NOT_OUT="at-floor needs" \
    expect 1 "same mix, over binary first: still fails" check glibc-over at-floor

# Real ELF: this shell's executable. Every glibc binary needs some GLIBC_ version > 1.0
# and all of them are < 999.
real="$(readlink -f "$BASH")"
expect 0 "real binary under generous floors" bash "$script" --max-glibc 999 --max-glibcxx 999 --max-cxxabi 999 "$real"
expect 1 "real binary over a floor of 1.0" bash "$script" --max-glibc 1.0 "$real"

expect 2 "missing file" bash "$script" "$work/does-not-exist"
expect 2 "non-ELF file (objdump fails)" bash "$script" "$script"
expect 2 "no arguments" bash "$script"
expect 2 "unknown option" bash "$script" --bogus "$target"

echo "passed=$pass failed=$fail"
[ "$fail" -eq 0 ]
