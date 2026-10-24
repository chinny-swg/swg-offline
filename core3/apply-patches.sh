#!/bin/bash
#
# Applies patches/core3/*.patch and patches/engine3/*.patch to a Core3 checkout:
#
#   core3/apply-patches.sh /path/to/Core3
#   core3/apply-patches.sh --reverse /path/to/Core3   # takes them out again, e.g. before a pin bump
#
# Patches already applied (or, with --reverse, not applied) are skipped, so it is safe to run again.

set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVERSE=false

if [ "${1:-}" = "--reverse" ]; then
    REVERSE=true
    shift
fi

CORE3="${1:?usage: apply-patches.sh [--reverse] /path/to/Core3}"

apply_series() {
    local dir="$1" target="$2" patch patches

    patches=("${dir}"/*.patch)
    [ -e "${patches[0]}" ] || return 0

    if ${REVERSE}; then
        for ((i = ${#patches[@]} - 1; i >= 0; i--)); do
            patch="${patches[i]}"

            if git -C "${target}" apply --reverse --check "${patch}" 2> /dev/null; then
                git -C "${target}" apply --reverse "${patch}"
                echo "reverted: $(basename "${patch}")"
            fi
        done
        return 0
    fi

    for patch in "${patches[@]}"; do
        if git -C "${target}" apply --reverse --check "${patch}" 2> /dev/null; then
            echo "already applied: $(basename "${patch}")"
        elif git -C "${target}" apply --whitespace=nowarn "${patch}"; then
            echo "applied: $(basename "${patch}")"
        else
            echo "FAILED: $(basename "${patch}") does not apply to ${target}" >&2
            exit 1
        fi
    done
}

[ -f "${CORE3}/MMOCoreORB/utils/engine3/MMOEngine/src/engine/engine.h" ] ||
    { echo "engine3 submodule missing in ${CORE3}; run: git -C ${CORE3} submodule update --init" >&2; exit 1; }

if ${REVERSE}; then
    apply_series "${HERE}/patches/engine3" "${CORE3}/MMOCoreORB/utils/engine3"
    apply_series "${HERE}/patches/core3" "${CORE3}"
else
    apply_series "${HERE}/patches/core3" "${CORE3}"
    apply_series "${HERE}/patches/engine3" "${CORE3}/MMOCoreORB/utils/engine3"
fi
