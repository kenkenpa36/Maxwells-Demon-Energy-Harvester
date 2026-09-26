#!/usr/bin/env python3
import time
import subprocess
import os
import sys

ESPTOOL = "/home/imaken/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool"
PORT = "/dev/ttyACM0"

print("==================================================")
print(" XIAO ESP32-C3 Flash Erase Tool (Emergency Reset)")
print("==================================================")
print("旧プログラム（Deep Sleep処理）を完全に消去します。")
print("Bボタンを押したままRボタンを1回押し、Bボタンを離してください...\n")

while True:
    if os.path.exists(PORT):
        print(f"[!] {PORT} 検出！Flash全消去を実行します...")
        cmd = [ESPTOOL, "--chip", "esp32c3", "--port", PORT, "--baud", "115200", "--before", "no_reset", "erase-flash"]
        res = subprocess.run(cmd)
        if res.returncode == 0:
            print("\n[SUCCESS] フラッシュメモリの消去に成功しました！")
            print("Deep Sleepプログラムが消去されたため、ポートが永久に固定されます。")
            print("Arduino IDE から通常通り書き込んでください！")
            sys.exit(0)
    time.sleep(0.005)
