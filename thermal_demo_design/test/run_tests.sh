#!/usr/bin/env bash
# Host-side test runner for the ESP32-C3 firmware policy logic.
#
#   ./test/run_tests.sh            # build + run unit tests
#   ./test/run_tests.sh --coverage # additionally print llvm-cov line coverage
#   ./test/run_tests.sh --syntax   # additionally syntax-check the .ino with Arduino stubs
#
# Requires clang++ (Apple clang or LLVM). Coverage needs llvm-profdata/llvm-cov
# (available via `xcrun` on macOS).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKETCH_DIR="$(cd "$HERE/.." && pwd)"
BUILD="$HERE/build"
mkdir -p "$BUILD"

CXX="${CXX:-clang++}"
CXXFLAGS=(-std=c++17 -Wall -Wextra -Werror -O0 -g)

want_coverage=false
want_syntax=false
for arg in "$@"; do
    case "$arg" in
        --coverage) want_coverage=true ;;
        --syntax)   want_syntax=true ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if $want_coverage; then
    CXXFLAGS+=(-fprofile-instr-generate -fcoverage-mapping)
fi

echo "== build"
"$CXX" "${CXXFLAGS[@]}" "$HERE/test_demon_policy.cpp" -o "$BUILD/test_demon_policy"

echo "== run"
set +e
if $want_coverage; then
    LLVM_PROFILE_FILE="$BUILD/test.profraw" "$BUILD/test_demon_policy"
else
    "$BUILD/test_demon_policy"
fi
status=$?
set -e


echo "== sketch tests (setup/loop against stateful fakes)"
for idf_major in 4 5; do
    "$CXX" -std=c++17 -Wall -Wextra -O0 -g -DSTUB_IDF_MAJOR="$idf_major" \
        -I"$HERE/stubs" "$HERE/test_sketch.cpp" -o "$BUILD/test_sketch_idf$idf_major"
    "$BUILD/test_sketch_idf$idf_major" || status=1
done

if $want_coverage; then
    echo "== coverage (demon_policy.h)"
    PROFDATA="$(command -v llvm-profdata || xcrun -f llvm-profdata)"
    LLVMCOV="$(command -v llvm-cov || xcrun -f llvm-cov)"
    "$PROFDATA" merge -sparse "$BUILD/test.profraw" -o "$BUILD/test.profdata"
    "$LLVMCOV" report "$BUILD/test_demon_policy" \
        -instr-profile="$BUILD/test.profdata" \
        "$SKETCH_DIR/demon_policy.h"
fi

if $want_syntax; then
    # Both arduino-esp32 core generations: 2.x (ESP-IDF 4.4) and 3.x (ESP-IDF 5.x).
    for idf_major in 4 5; do
        echo "== syntax check: maxwell_demon_harvester_esp32c3_v2.ino (Arduino stubs, IDF ${idf_major}.x)"
        "$CXX" -std=c++17 -fsyntax-only -Wall -Wextra -x c++ \
            -DSTUB_IDF_MAJOR="$idf_major" \
            -I"$HERE/stubs" -include "$HERE/stubs/Arduino.h" \
            "$SKETCH_DIR/maxwell_demon_harvester_esp32c3_v2.ino"
        echo "   ok"
    done
fi

exit $status
