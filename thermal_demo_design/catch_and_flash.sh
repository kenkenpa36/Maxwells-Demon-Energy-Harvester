#!/usr/bin/env python3
import time
import subprocess
import os
import sys

ESPTOOL = "/home/imaken/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool"
PORT = "/dev/ttyACM0"

print("==================================================")
print(" XIAO ESP32-C3 Ultra-Fast Catch & Connect Script")
print("==================================================")
print("1. マイコンの【Bボタン（BOOT）を押しっぱなし】にする")
print("2. Bボタンを押したまま【Rボタン（RESET）を1回短く押して離す】")
print("3. その後【Bボタンを離す】")
print("\n/dev/ttyACM0 の出現をミリ秒単位で高速監視中...")

while True:
    if os.path.exists(PORT):
        print(f"\n[+] {PORT} を検出！即座に同期（no_reset）を開始します...")
        cmd = [ESPTOOL, "--chip", "esp32c3", "--port", PORT, "--baud", "115200", "--before", "no_reset", "chip-id"]
        res = subprocess.run(cmd)
        if res.returncode == 0:
            print("\n==================================================")
            print(" [SUCCESS] マイコンのロックオンに成功しました！")
            print(" これで Deep Sleep は実行されず、USB接続が固定されました。")
            print(" Arduino IDE からスケッチを「書き込み」してください！")
            print("==================================================")
            sys.exit(0)
        else:
            print("[-] 同期失敗。再検出を継続します...")
    time.sleep(0.005)
