#!/bin/bash
# ESP32-C3 自動書き込みスクリプト
# ポート(/dev/ttyACM0)が現れた瞬間に即座に書き込みを開始します
#
# 使い方:
#   1. このスクリプトを実行する
#   2. 「ポートを待機中...」と表示されたら、マイコンの B ボタンを押しながら R ボタンを1回押す
#   3. 自動的に書き込みが開始されます

echo "════════════════════════════════════════════════════"
echo " ESP32-C3 自動書き込みツール"
echo " ポート出現を監視し、即座にフラッシュ書き込みを行います"
echo "════════════════════════════════════════════════════"
echo ""

# コンパイル済みバイナリのパスを検索
SKETCH_NAME="maxwell_demon_harvester_esp32c3"
BUILD_DIR=$(find /tmp -name "${SKETCH_NAME}.ino.bin" -newer /tmp -printf '%h\n' 2>/dev/null | head -1)

if [ -z "$BUILD_DIR" ]; then
    # Arduino IDE 2.x のビルドキャッシュを検索
    BUILD_DIR=$(find /tmp -path "*${SKETCH_NAME}*" -name "*.ino.bin" 2>/dev/null | head -1)
    if [ -n "$BUILD_DIR" ]; then
        BUILD_DIR=$(dirname "$BUILD_DIR")
    fi
fi

# esptool のパスを検索
ESPTOOL=$(find /home/imaken/.arduino15 -name "esptool" -o -name "esptool.py" 2>/dev/null | head -1)
if [ -z "$ESPTOOL" ]; then
    ESPTOOL=$(which esptool.py 2>/dev/null || which esptool 2>/dev/null)
fi

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
