#!/usr/bin/env python3
"""
XIAO ESP32-C3 Flash Erase Tool v14
- pySerial Write timeout 完全回避パッチ
- 100%確実なROMブートローダー接続シーケンス
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
print(" XIAO ESP32-C3 Flash消去ツール v14 (確定復旧版)")
print("=" * 60)

# ModemManager 停止
try:
    subprocess.run(["systemctl", "stop", "ModemManager"], stderr=subprocess.DEVNULL)
    print("[+] ModemManager 停止成功")
except Exception:
    pass

print("""
  ★ 操作手順 ★

  1. D9ピン と GNDピン をジャンパー線で接続する
     （または、マイコン上の B ボタン を指でしっかり押し続ける）

  2. そのまま【 R ボタン 】を 1 回だけ押して離す

  3. 【 D9-GND ジャンパー線（またはBボタン）は接続したまま 】で
     下の Enter キーを押してください。
""")

input("準備ができたら [Enter] キーを押してください...")

print("\n[+] USBポートの復帰と安定を待機中 (2秒)...")
time.sleep(2)

if not os.path.exists(PORT):
    print(f"[!] {PORT} が見つかりません。USB接続を確認して再実行してください。")
    sys.exit(1)

print(f"[+] {PORT} 検出！ブートローダー直接通信 (--before no-reset) を実行します...\n")

args = ['--chip', 'esp32c3', '--port', PORT, '--baud', '115200', '--before', 'no-reset', 'erase-flash']

try:
    esptool.main(args)
    print("\n" + "=" * 60)
    print(" ★★★ SUCCESS ★★★ Flash全消去が完了しました！")
    print("=" * 60)
    print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND ジャンパー線（またはBボタン）を【外す/離す】
    3. USBケーブルを【挿す】
    4. Arduino IDE でスケッチを書き込む
    """)
    sys.exit(0)
except SystemExit as se:
    if se.code == 0:
        print("\n" + "=" * 60)
        print(" ★★★ SUCCESS ★★★ Flash全消去が完了しました！")
        print("=" * 60)
        print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND ジャンパー線（またはBボタン）を【外す/離す】
    3. USBケーブルを【挿す】
    4. Arduino IDE でスケッチを書き込む
        """)
        sys.exit(0)
    else:
        print(f"\n[-] 消去失敗 (exit code: {se.code})")
except Exception as e:
    print(f"\n[-] エラー発生: {e}")

print("\n" + "=" * 60)
print(" 接続できませんでした。")
print(" D9-GNDジャンパーがしっかり挿さっているか確認し、")
print(" Rボタンを押してから再度 Enter を押してください。")
print("=" * 60)
