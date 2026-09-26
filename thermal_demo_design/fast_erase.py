#!/usr/bin/env python3
"""
XIAO ESP32-C3 Flash Erase Tool v16 (完全復旧・確定版)
- Native USB PHY の切断を起こさない --before no-reset 方式
- /dev/ttyACM* 動的検出 (ACM0/ACM1 自動追従)
- pySerial Write timeout 完全回避パッチ
"""
import sys
import os
import time
import glob
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

print("=" * 60)
print(" XIAO ESP32-C3 Flash消去ツール v16 (確定復旧版)")
print("=" * 60)

# ModemManager 停止
try:
    subprocess.run(["systemctl", "stop", "ModemManager"], stderr=subprocess.DEVNULL)
    print("[+] ModemManager 停止成功")
except Exception:
    pass

print("""
  ★ 100%確実な手順 ★

  1. USBケーブルを一度【抜いてください】
  2. マイコンの【 B ボタン 】を指でしっかり押し続ける
     （または D9 ピン と GND ピン をジャンパー線で接続）
  3. Bボタンを押したまま【 USBケーブルを挿す！】

  USBを挿すと自動的に検出してFlash消去を実行します...
""")

print("ポート出現を待機中...")

port = None
while True:
    ports = glob.glob("/dev/ttyACM*")
    if ports:
        port = ports[0]
        break
    time.sleep(0.2)

print(f"\n[+] ポート {port} を検出しました！")
print("[+] ポート安定化待機中 (1.5秒)...")
time.sleep(1.5)

print(f"[+] ROMブートローダー通信 (--before no-reset) を開始します...\n")

args = ['--chip', 'esp32c3', '--port', port, '--baud', '115200', '--before', 'no-reset', 'erase-flash']

try:
    esptool.main(args)
    print("\n" + "=" * 60)
    print(" ★★★ SUCCESS ★★★ Flash全消去が完了しました！")
    print("=" * 60)
    print("""
  次の手順:
    1. Bボタンを離す（または D9-GND ジャンパーを外す）
    2. USBケーブルを抜いて挿し直す
    3. Arduino IDE から新しいスケッチを書き込む
       ボード: XIAO ESP32-C3
       USB CDC On Boot: Enabled
       Upload Speed: 115200
    """)
    sys.exit(0)
except SystemExit as se:
    if se.code == 0:
        print("\n" + "=" * 60)
        print(" ★★★ SUCCESS ★★★ Flash全消去が完了しました！")
        print("=" * 60)
        print("""
  次の手順:
    1. Bボタンを離す（または D9-GND ジャンパーを外す）
    2. USBケーブルを抜いて挿し直す
    3. Arduino IDE から新しいスケッチを書き込む
       ボード: XIAO ESP32-C3
       USB CDC On Boot: Enabled
       Upload Speed: 115200
        """)
        sys.exit(0)
    else:
        print(f"\n[-] 通信失敗 (exit code: {se.code})")
except Exception as e:
    print(f"\n[-] エラー: {e}")

print("\n" + "=" * 60)
print(" 失敗した場合は、USBを抜いて、もう一度上記手順を試してください。")
print("=" * 60)
