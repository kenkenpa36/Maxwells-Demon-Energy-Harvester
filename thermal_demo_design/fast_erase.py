#!/usr/bin/env python3
"""
XIAO ESP32-C3 Flash Erase Tool v13
- pySerial Write timeout 回避パッチ
- GPIO9 = LOW (ブートローダーモード) 状態の維持
"""
import sys
import os
import time
import subprocess

# pySerial の write() で select() タイムアウトを無視するパッチ
import serial
def patched_write(self, data):
    return os.write(self.fd, data)
serial.Serial.write = patched_write

ESPTOOL_PATH = '/home/imaken/.local/lib/python3.14/site-packages'
if ESPTOOL_PATH not in sys.path:
    sys.path.insert(0, ESPTOOL_PATH)

import esptool

PORT = "/dev/ttyACM0"

print("=" * 60)
print(" XIAO ESP32-C3 Flash消去ツール v13")
print("=" * 60)

# ModemManager 停止
try:
    subprocess.run(["systemctl", "stop", "ModemManager"], stderr=subprocess.DEVNULL)
    print("[+] ModemManager 停止成功")
except Exception:
    pass

# ポート確認
if not os.path.exists(PORT):
    print(f"\n[!] {PORT} を待機中...")
    while not os.path.exists(PORT):
        time.sleep(0.1)

print(f"[+] {PORT} 検出！")

strategies = [
    {
        "name": "リセットなし (--before no-reset --baud 115200)",
        "args": ['--chip', 'esp32c3', '--port', PORT, '--baud', '115200', '--before', 'no-reset', 'erase-flash']
    },
    {
        "name": "USB専用リセット (--before usb-reset --baud 115200)",
        "args": ['--chip', 'esp32c3', '--port', PORT, '--baud', '115200', '--before', 'usb-reset', 'erase-flash']
    },
    {
        "name": "標準リセット (--before default-reset --baud 115200)",
        "args": ['--chip', 'esp32c3', '--port', PORT, '--baud', '115200', '--before', 'default-reset', 'erase-flash']
    }
]

for i, strat in enumerate(strategies, 1):
    print(f"\n[{i}/{len(strategies)}] 試行: {strat['name']}")
    try:
        esptool.main(strat['args'])
        print("\n" + "=" * 60)
        print(" ★★★ SUCCESS ★★★ Flash消去が完全完了しました！")
        print("=" * 60)
        print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND ジャンパー（またはBボタン）を【外す/離す】
    3. USBケーブルを【挿す】
    4. Arduino IDE で新しいスケッチを書き込む
        """)
        sys.exit(0)
    except SystemExit as se:
        if se.code == 0:
            print("\n" + "=" * 60)
            print(" ★★★ SUCCESS ★★★ Flash消去が完全完了しました！")
            print("=" * 60)
            print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND ジャンパー（またはBボタン）を【外す/離す】
    3. USBケーブルを【挿す】
    4. Arduino IDE で新しいスケッチを書き込む
            """)
            sys.exit(0)
        print(f"  → 失敗 (exit code: {se.code})")
    except Exception as e:
        print(f"  → エラー: {e}")
    
    time.sleep(1)

print("\n" + "=" * 60)
print(" 消去に失敗しました。")
print(" 【重要】D9-GND ジャンパーを挿したまま（またはBボタンを押したまま）、")
print(" Rボタンを1回押してから、もう一度このコマンドを実行してください。")
print("=" * 60)
