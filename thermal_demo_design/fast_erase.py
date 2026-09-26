#!/usr/bin/env python3
"""
XIAO ESP32-C3 Flash Erase Tool v12
- pySerial の select() Write timeout 完全回避パッチ適用
- ModemManager 自動停止
- 複数接続パターンの自動試行
"""
import sys
import os
import time
import subprocess

# pySerial の write() で select() タイムアウトを無視して os.write を直接呼ぶパッチ
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
print(" XIAO ESP32-C3 Flash消去ツール v12")
print(" 【Write timeout 完全回避パッチ適用版】")
print("=" * 60)

# 1. ModemManager 停止
try:
    subprocess.run(["systemctl", "stop", "ModemManager"], stderr=subprocess.DEVNULL)
    print("[+] ModemManager 停止成功")
except Exception:
    pass

# 2. ポート確認
if not os.path.exists(PORT):
    print(f"\n[!] {PORT} を待機中...")
    while not os.path.exists(PORT):
        time.sleep(0.1)

print(f"[+] {PORT} 検出！ Flash消去を順番に試行します...\n")

strategies = [
    {
        "name": "USB専用リセット (usb-reset)",
        "args": ['--chip', 'esp32c3', '--port', PORT, '--before', 'usb-reset', 'erase-flash']
    },
    {
        "name": "標準リセット (default-reset)",
        "args": ['--chip', 'esp32c3', '--port', PORT, '--before', 'default-reset', 'erase-flash']
    },
    {
        "name": "リセットなし (no-reset)",
        "args": ['--chip', 'esp32c3', '--port', PORT, '--before', 'no-reset', 'erase-flash']
    },
]

for i, strat in enumerate(strategies, 1):
    print(f"[{i}/{len(strategies)}] 試行: {strat['name']}")
    try:
        esptool.main(strat['args'])
        print("\n" + "=" * 60)
        print(" ★★★ SUCCESS ★★★ Flash消去が完全に完了しました！")
        print("=" * 60)
        print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND ジャンパーを【外す】
    3. USBケーブルを【挿す】
    4. Arduino IDE で新しいスケッチを書き込む
        """)
        sys.exit(0)
    except SystemExit as se:
        if se.code == 0:
            print("\n" + "=" * 60)
            print(" ★★★ SUCCESS ★★★ Flash消去が完全に完了しました！")
            print("=" * 60)
            print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND ジャンパーを【外す】
    3. USBケーブルを【挿す】
    4. Arduino IDE で新しいスケッチを書き込む
            """)
            sys.exit(0)
        print(f"  → 失敗 (exit code: {se.code})\n")
    except Exception as e:
        print(f"  → エラー: {e}\n")
    
    time.sleep(2)

print("\n" + "=" * 60)
print(" すべての試行が失敗しました。")
print(" Bボタンを押しながらRボタンを押し直してから、再度実行してください。")
print("=" * 60)
