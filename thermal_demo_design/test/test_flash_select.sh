#!/usr/bin/env bash
# Tests for the build-directory selection in flash_esp32c3.sh.
# The script is sourced in library mode (FLASH_ESP32C3_LIB_ONLY=1) so that
# find_build_dir / verify_artifacts can be exercised on a temporary tree.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLASH_SCRIPT="$HERE/../flash_esp32c3.sh"

failures=0
checks=0
check() {  # check <description> <condition...>
    local desc=$1; shift
    checks=$((checks + 1))
    if ! "$@"; then
        failures=$((failures + 1))
        echo "  FAIL: $desc"
    fi
}

# shellcheck source=../flash_esp32c3.sh
FLASH_ESP32C3_LIB_ONLY=1 source "$FLASH_SCRIPT" || { echo "  FAIL: cannot source $FLASH_SCRIPT"; exit 1; }

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

V1=maxwell_demon_harvester_esp32c3
V2=maxwell_demon_harvester_esp32c3_v2

# Two build directories: v2 is newer than v1, and v1 is complete.
mkdir -p "$ROOT/build-v1" "$ROOT/build-v2" "$ROOT/build-v1-old"
for f in ino.bin ino.bootloader.bin ino.partitions.bin; do
    : > "$ROOT/build-v1-old/$V1.$f"
    : > "$ROOT/build-v1/$V1.$f"
    : > "$ROOT/build-v2/$V2.$f"
done
touch -t 202601010000 "$ROOT/build-v1-old/$V1.ino.bin"
touch -t 202601020000 "$ROOT/build-v1/$V1.ino.bin"
touch -t 202601030000 "$ROOT/build-v2/$V2.ino.bin"

echo "- v1 override selects the v1 directory even though a newer v2 build exists"
check "find_build_dir v1" test "$(find_build_dir "$V1" "$ROOT")" = "$ROOT/build-v1"

echo "- v2 default selects the v2 directory"
check "find_build_dir v2" test "$(find_build_dir "$V2" "$ROOT")" = "$ROOT/build-v2"

echo "- newest matching build wins among several v1 builds"
check "newest v1" test "$(find_build_dir "$V1" "$ROOT")" != "$ROOT/build-v1-old"

echo "- no match returns failure"
check "no match" ! find_build_dir "does_not_exist" "$ROOT" >/dev/null

echo "- verify_artifacts passes on a complete directory"
check "complete" verify_artifacts "$ROOT/build-v1" "$V1"

echo "- verify_artifacts fails when the requested names are missing in the chosen directory"
check "wrong version in dir" ! verify_artifacts "$ROOT/build-v2" "$V1" >/dev/null

rm "$ROOT/build-v1/$V1.ino.bootloader.bin"
echo "- verify_artifacts fails when the bootloader image is missing"
check "missing bootloader" ! verify_artifacts "$ROOT/build-v1" "$V1" >/dev/null

echo
echo "$checks checks, $failures failures (flash_esp32c3.sh)"
[ "$failures" -eq 0 ]
