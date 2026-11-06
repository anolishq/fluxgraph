#!/usr/bin/env bash
# Fail when an ELF binary needs a newer glibc or libstdc++ than the deploy target ships.
#
# Usage:
#   scripts/check-glibc-floor.sh [--max-glibc V] [--max-glibcxx V] [--max-cxxabi V] BINARY...
#
# Defaults are Debian 13 (trixie): glibc 2.41, and GCC 14's libstdc++ (libstdc++6
# 14.2.0), which defines up to GLIBCXX_3.4.33 and CXXABI_1.3.15. The versions are
# read from the binary's dynamic symbol table (`objdump -T`); set OBJDUMP to use a
# different objdump. Exits 0 when every binary is within the floor, 1 when one
# needs a newer version, 2 on a usage error or when a binary cannot be read.

set -euo pipefail

max_glibc="2.41"
max_glibcxx="3.4.33"
max_cxxabi="1.3.15"
objdump="${OBJDUMP:-objdump}"

usage() {
    sed -n '2,11s/^# \{0,1\}//p' "$0" >&2
    exit 2
}

binaries=()
while [ $# -gt 0 ]; do
    case "$1" in
        --max-glibc)
            [ $# -ge 2 ] || usage
            max_glibc="$2"
            shift 2
            ;;
        --max-glibcxx)
            [ $# -ge 2 ] || usage
            max_glibcxx="$2"
            shift 2
            ;;
        --max-cxxabi)
            [ $# -ge 2 ] || usage
            max_cxxabi="$2"
            shift 2
            ;;
        -h | --help) usage ;;
        --)
            shift
            binaries+=("$@")
            break
            ;;
        -*)
            echo "error: unknown option: $1" >&2
            usage
            ;;
        *)
            binaries+=("$1")
            shift
            ;;
    esac
done
[ ${#binaries[@]} -gt 0 ] || usage

# True when version $1 is newer than version $2.
newer_than() {
    [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$1" ]
}

# Prints the distinct <prefix>N.N... versions in $symbols, one per line, oldest first.
# GLIBC_PRIVATE and other non-numeric tags carry no version, so the pattern takes
# digits only; GLIBC_ never matches GLIBCXX_ because the next character differs.
versions_of() {
    printf '%s\n' "$symbols" | grep -oE "${1}_[0-9]+(\.[0-9]+)*" | sed "s/^${1}_//" | sort -uV || true
}

# Checks every <prefix> version the binary needs against <max>; sets status=1 on a miss.
check_family() {
    local prefix="$1" max="$2" list v
    list="$(versions_of "$prefix")"
    [ -n "$list" ] || return 0
    while IFS= read -r v; do
        if newer_than "$v" "$max"; then
            echo "FAIL: $bin needs ${prefix}_$v, newer than the floor ${prefix}_$max" >&2
            status=1
        fi
    done <<<"$list"
}

status=0
for bin in "${binaries[@]}"; do
    if [ ! -f "$bin" ]; then
        echo "error: $bin: no such file" >&2
        exit 2
    fi
    if ! symbols="$("$objdump" -T -- "$bin" 2>&1)"; then
        echo "error: $objdump -T $bin failed:" >&2
        printf '%s\n' "$symbols" >&2
        exit 2
    fi

    # A dynamically linked binary always references some GLIBC_ version. Finding
    # none means the symbol table was not what this check expects, so it cannot
    # vouch for the binary.
    if [ -z "$(versions_of GLIBC)" ]; then
        echo "error: $bin: no GLIBC_ symbol versions found in '$objdump -T' output" >&2
        exit 2
    fi

    top_glibc="$(versions_of GLIBC | tail -n 1)"
    top_glibcxx="$(versions_of GLIBCXX | tail -n 1)"
    top_cxxabi="$(versions_of CXXABI | tail -n 1)"
    echo "$bin: highest GLIBC_${top_glibc} (max ${max_glibc}), GLIBCXX_${top_glibcxx:-none} (max ${max_glibcxx}), CXXABI_${top_cxxabi:-none} (max ${max_cxxabi})"

    check_family GLIBC "$max_glibc"
    check_family GLIBCXX "$max_glibcxx"
    check_family CXXABI "$max_cxxabi"
done

if [ "$status" -eq 0 ]; then
    echo "OK: every binary is within GLIBC_${max_glibc} / GLIBCXX_${max_glibcxx} / CXXABI_${max_cxxabi}"
fi
exit "$status"
