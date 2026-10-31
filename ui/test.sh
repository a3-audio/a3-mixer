#!/bin/bash
# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The desk's tests: build, then run what was just built -- against an offline
# copy of the truth, on a screen of its own.
#
#   ./test.sh [-- CTEST ARGS]          e.g. ./test.sh -- -R LedScale
#
# ctest runs a binary, it does not build one (a3-motion-ui test.sh,
# 2026-09-13): this builds first and prints when the runner was built.
# The truth: $A3_OSC_TRUTH if given, else a3-core beside this checkout,
# else the installed one -- always as an offline copy, every named host moved
# to 192.0.2.x (a3-motion-ui #67): the second wall after the runner's guard.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"
CTEST_ARGS=()
if [[ "${1:-}" == "--" ]]; then shift; CTEST_ARGS=("$@"); fi

nice -n 19 cmake -S "$HERE" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DA3DESK_TESTS=ON \
    -DCMAKE_PREFIX_PATH="$HOME/local/juce"
nice -n 19 cmake --build "$BUILD" -j2

RUNNER="$BUILD/tests/a3-desk-tests_artefacts/Release/a3-desk-tests"
echo "=== runner built $(date -r "$RUNNER" '+%Y-%m-%d %H:%M:%S') ==="

truth_source() {
    if [[ -n "${A3_OSC_TRUTH:-}" ]]; then echo "$A3_OSC_TRUTH"; return; fi
    local beside="$HERE/../../a3-core/platform-config/debian-x86_64/a3-core/usr/share/a3/a3-osc.json"
    if [[ -f "$beside" ]]; then realpath "$beside"; return; fi
    if [[ -f /usr/share/a3/a3-osc.json ]]; then echo /usr/share/a3/a3-osc.json; fi
}
SOURCE="$(truth_source)"
[[ -n "$SOURCE" ]] || { echo "no a3-osc.json found: set A3_OSC_TRUTH" >&2; exit 1; }
export A3_OSC_TRUTH="$BUILD/a3-osc-offline.json"
python3 -I "$HERE/tools/a3-offline-truth" "$SOURCE" "$A3_OSC_TRUTH"
echo "=== OSC truth: offline copy of $SOURCE ==="

RUN=(ctest --test-dir "$BUILD" --output-on-failure "${CTEST_ARGS[@]}")
if command -v xvfb-run >/dev/null; then xvfb-run -a "${RUN[@]}"; else "${RUN[@]}"; fi
