#!/bin/bash
# ESP32-C3 自動書き込みスクリプト
# ポート(/dev/ttyACM0)が現れた瞬間に即座に書き込みを開始します
#
# 使い方:
#   1. このスクリプトを実行する
#   2. 「ポートを待機中...」と表示されたら、マイコンの B ボタンを押しながら R ボタンを1回押す
#   3. 自動的に書き込みが開始されます
#
# 既定は v2 (発電効率向上版)。旧版を書き込む場合:
#   SKETCH_NAME=maxwell_demon_harvester_esp32c3 ./flash_esp32c3.sh
# ビルドキャッシュの検索先を変える場合: SEARCH_ROOT=/path ./flash_esp32c3.sh

# ---------------------------------------------------------------------
#  ビルドディレクトリ選択 (test/test_flash_select.sh でテスト)
# ---------------------------------------------------------------------

# find_build_dir <sketch name> <search root>
#   "<sketch name>.ino.bin" に完全一致するファイルを探し、最新のものの
#   ディレクトリを出力する。前方一致 (v1 名で v2 に一致する等) はしない。
find_build_dir() {
    local name=$1 root=$2 newest="" candidate
    while IFS= read -r candidate; do
        [ -n "$candidate" ] || continue
        if [ -z "$newest" ] || [ "$candidate" -nt "$newest" ]; then
            newest=$candidate
        fi
    done < <(find "$root" -name "${name}.ino.bin" 2>/dev/null)
    [ -n "$newest" ] || return 1
    dirname "$newest"
}

# verify_artifacts <build dir> <sketch name>
#   esptool に渡す 3 つのバイナリが揃っているか確認する。
verify_artifacts() {
    local dir=$1 name=$2 f ok=0
    for f in "${name}.ino.bootloader.bin" "${name}.ino.partitions.bin" "${name}.ino.bin"; do
        if [ ! -f "$dir/$f" ]; then
            echo "見つかりません: $dir/$f"
            ok=1
        fi
    done
    return $ok
}

# ライブラリとして source された場合はここで終了 (テスト用)
if [ -n "${FLASH_ESP32C3_LIB_ONLY:-}" ]; then
    return 0 2>/dev/null || exit 0
fi

# ---------------------------------------------------------------------
#  メイン
# ---------------------------------------------------------------------
echo "════════════════════════════════════════════════════"
echo " ESP32-C3 自動書き込みツール"
echo " ポート出現を監視し、即座にフラッシュ書き込みを行います"
echo "════════════════════════════════════════════════════"
echo ""

SKETCH_NAME="${SKETCH_NAME:-maxwell_demon_harvester_esp32c3_v2}"
SEARCH_ROOT="${SEARCH_ROOT:-/tmp}"

# コンパイル済みバイナリのパスを検索 (Arduino IDE 2.x のビルドキャッシュ)
BUILD_DIR=$(find_build_dir "$SKETCH_NAME" "$SEARCH_ROOT")
if [ -n "$BUILD_DIR" ] && ! verify_artifacts "$BUILD_DIR" "$SKETCH_NAME"; then
    echo "ビルドディレクトリ $BUILD_DIR に必要なバイナリが揃っていません。"
    BUILD_DIR=""
fi

# esptool のパスを検索
ESPTOOL=$(find "${HOME}/.arduino15" -name "esptool" -o -name "esptool.py" 2>/dev/null | head -1)
if [ -z "$ESPTOOL" ]; then
    ESPTOOL=$(which esptool.py 2>/dev/null || which esptool 2>/dev/null)
fi

echo "スケッチ: $SKETCH_NAME"
echo "esptool: $ESPTOOL"
echo "ビルドディレクトリ: $BUILD_DIR"
echo ""

# ポートの待機と即時書き込み
PORT="/dev/ttyACM0"
ALT_PORT="/dev/ttyACM1"

echo ">>> ポートを待機中... <<<"
echo ">>> マイコンの B ボタンを押しながら R ボタンを1回チョンと押してください <<<"
echo ""

while true; do
    if [ -e "$PORT" ]; then
        echo "★ ポート $PORT を検出！即座に書き込みを開始します..."
        sleep 0.2

        if [ -n "$ESPTOOL" ] && [ -n "$BUILD_DIR" ]; then
            $ESPTOOL --chip esp32c3 --port $PORT --baud 460800 \
                --before default_reset --after hard_reset \
                write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect \
                0x0 "$BUILD_DIR/${SKETCH_NAME}.ino.bootloader.bin" \
                0x8000 "$BUILD_DIR/${SKETCH_NAME}.ino.partitions.bin" \
                0x10000 "$BUILD_DIR/${SKETCH_NAME}.ino.bin"
        else
            echo "esptool またはビルドファイルが見つかりません。"
            echo "Arduino IDE から直接書き込みを試してください。"
            echo "ポートが現れている今のうちに、Arduino IDE の書き込みボタンを素早く押してください！"
            echo "（15秒間ポートを監視します）"
            sleep 15
        fi
        break
    elif [ -e "$ALT_PORT" ]; then
        echo "★ ポート $ALT_PORT を検出！"
        PORT="$ALT_PORT"
        continue
    fi
    sleep 0.1
done

echo ""
echo "完了！R ボタンを1回押してプログラムを開始してください。"
