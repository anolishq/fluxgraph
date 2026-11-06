#!/usr/bin/env bash
# Fail when an ELF binary needs a newer glibc or libstdc++ than the deploy target ships.
#
# Usage:
#   scripts/check-glibc-floor.sh [--max-glibc V] [--max-glibcxx V] BINARY...
#
# Defaults are Debian 13 (trixie): glibc 2.41 and GCC 14's libstdc++ (GLIBCXX_3.4.33).
# The versions are read from the binary's dynamic symbol table (`objdump -T`); set
# OBJDUMP to use a different objdump. Exits 0 when every binary is within the floor,
# 1 when one needs a newer version, 2 on a usage error or when a binary cannot be read.

set -euo pipefail

max_glibc="2.41"
max_glibcxx="3.4.33"
objdump="${OBJDUMP:-objdump}"

usage() {
    sed -n '2,10s/^# \{0,1\}//p' "$0" >&2
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

# Prints the highest version in the list read on stdin (one per line), or nothing.
highest() {
    sort -V | tail -n 1
}

# True when version $1 is newer than version $2.
newer_than() {
    [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$1" ]
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

    # GLIBC_PRIVATE and other non-numeric tags carry no version, so the patterns
    # take digits only. GLIBC_ never matches GLIBCXX_: the next character differs.
    glibc_versions="$(printf '%s\n' "$symbols" | grep -oE 'GLIBC_[0-9]+(\.[0-9]+)*' | sed 's/^GLIBC_//' | sort -uV || true)"
    glibcxx_versions="$(printf '%s\n' "$symbols" | grep -oE 'GLIBCXX_[0-9]+(\.[0-9]+)*' | sed 's/^GLIBCXX_//' | sort -uV || true)"

    # A dynamically linked binary always references some GLIBC_ version. Finding
    # none means the symbol table was not what this check expects, so it cannot
    # vouch for the binary.
    if [ -z "$glibc_versions" ]; then
        echo "error: $bin: no GLIBC_ symbol versions found in '$objdump -T' output" >&2
        exit 2
    fi

    top_glibc="$(printf '%s\n' "$glibc_versions" | highest)"
    top_glibcxx="$(printf '%s\n' "$glibcxx_versions" | highest)"
    echo "$bin: highest GLIBC_${top_glibc} (max ${max_glibc}), highest GLIBCXX_${top_glibcxx:-none} (max ${max_glibcxx})"

    while IFS= read -r v; do
        if newer_than "$v" "$max_glibc"; then
            echo "FAIL: $bin needs GLIBC_$v, newer than the floor GLIBC_$max_glibc" >&2
            status=1
        fi
    done <<<"$glibc_versions"

    if [ -n "$glibcxx_versions" ]; then
        while IFS= read -r v; do
            if newer_than "$v" "$max_glibcxx"; then
                echo "FAIL: $bin needs GLIBCXX_$v, newer than the floor GLIBCXX_$max_glibcxx" >&2
                status=1
            fi
        done <<<"$glibcxx_versions"
    fi
done

if [ "$status" -eq 0 ]; then
    echo "OK: every binary is within GLIBC_${max_glibc} / GLIBCXX_${max_glibcxx}"
fi
exit "$status"
