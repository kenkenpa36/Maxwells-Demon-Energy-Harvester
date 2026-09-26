#!/usr/bin/env python3
"""
XIAO ESP32-C3 Flash Erase Tool v10
- ModemManager 停止
- PYTHONPATH 継承による esptool モジュールロード修復
- サブプロセス環境での完全分離
"""
import sys
import time
import os
import subprocess

# esptool のインストールパスを追加
ESPTOOL_PATH = '/home/imaken/.local/lib/python3.14/site-packages'
if ESPTOOL_PATH not in sys.path:
    sys.path.insert(0, ESPTOOL_PATH)

PORT = "/dev/ttyACM0"

print("=" * 60)
print(" XIAO ESP32-C3 Flash消去ツール v10")
print("=" * 60)

# 1. ModemManager の停止
print("[+] ModemManager を一時停止中...")
try:
    subprocess.run(["systemctl", "stop", "ModemManager"], stderr=subprocess.DEVNULL)
    print("  → ModemManager 停止成功！")
except Exception as e:
    print(f"  → 警告: ModemManager 停止スキップ ({e})")

# 2. ポートの存在確認
if not os.path.exists(PORT):
    print(f"\n[!] {PORT} が見つかりません。")
    print("    D9-GND ジャンパーを接続した状態でUSBを挿してください。")
    print("    ポート出現を待機中...\n")
    while not os.path.exists(PORT):
        time.sleep(0.1)
    print(f"[+] {PORT} が出現しました！\n")

# 3. ポート安定確認
print("[+] ポート安定性確認中 (3秒)...")
time.sleep(3)
if not os.path.exists(PORT):
    print("[-] ポートが消滅しました。D9-GND ジャンパーを確認してください。")
    sys.exit(1)
print("[+] ブートローダーモード確定！\n")

# サブプロセス用の環境変数設定 (PYTHONPATH を追加)
env = dict(os.environ)
env["PYTHONPATH"] = f"{ESPTOOL_PATH}:{env.get('PYTHONPATH', '')}"

python_bin = sys.executable
strategies = [
    {
        "name": "USB CDC 専用接続 (--before no-reset --baud 115200)",
        "cmd": [python_bin, "-m", "esptool", "--chip", "esp32c3", "--port", PORT, "--baud", "115200", "--before", "no-reset", "erase-flash"]
    },
    {
        "name": "ROM直接通信 (--no-stub --before no-reset)",
        "cmd": [python_bin, "-m", "esptool", "--chip", "esp32c3", "--port", PORT, "--baud", "115200", "--before", "no-reset", "--no-stub", "erase-flash"]
    },
    {
        "name": "USBリセット (--before usb-reset --baud 115200)",
        "cmd": [python_bin, "-m", "esptool", "--chip", "esp32c3", "--port", PORT, "--baud", "115200", "--before", "usb-reset", "erase-flash"]
    },
    {
        "name": "標準リセット (--before default-reset)",
        "cmd": [python_bin, "-m", "esptool", "--chip", "esp32c3", "--port", PORT, "--before", "default-reset", "erase-flash"]
    }
]

for i, strat in enumerate(strategies, 1):
    print(f"[{i}/{len(strategies)}] 試行: {strat['name']}")
    print(f"         実行: {' '.join(strat['cmd'])}")
    
    # ポートが復帰するまで待機
    start_wait = time.time()
    while not os.path.exists(PORT):
        time.sleep(0.2)
        if time.time() - start_wait > 10:
            print("  → ポート消失のため待機タイムアウト。USBを挿し直してください。")
            break
    
    time.sleep(1) # ポート復帰直後の安定化
    
    res = subprocess.run(strat['cmd'], env=env)
    if res.returncode == 0:
        print("\n" + "=" * 60)
        print(" ★★★ SUCCESS ★★★ Flash消去が完全に完了しました！")
        print("=" * 60)
        print("""
  次の手順:
    1. USBケーブルを【抜く】
    2. D9-GND のジャンパー線を【外す】
    3. USBケーブルを【挿す】
    4. Arduino IDE で新しいスケッチを書き込む
       ボード: XIAO ESP32-C3
       USB CDC On Boot: Enabled
       Upload Speed: 115200
        """)
        sys.exit(0)
    else:
        print(f"  → 失敗 (リターンコード: {res.returncode})\n")
    
    time.sleep(2)

print("\n" + "=" * 60)
print(" すべての接続パターンが失敗しました。")
print("=" * 60)
