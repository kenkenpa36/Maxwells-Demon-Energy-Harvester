#!/usr/bin/env python3
import time
import os
import sys
import esptool

PORT = "/dev/ttyACM0"

print("==================================================")
print(" XIAO ESP32-C3 Zero-Latency Connection Lock Tool")
print("==================================================")
print("Pythonモジュールロード完了！オーバーヘッド0で待機中...")
print("【Bボタンを押しながらRボタンを1回短く押し、Bボタンを離してください】\n")

while True:
    if os.path.exists(PORT):
        print(f"\n[!] {PORT} 検出！即座にROMブートローダーと同期します...")
        try:
            esptool.main([
                '--chip', 'esp32c3',
                '--port', PORT,
                '--baud', '115200',
                '--before', 'no-reset',
                'chip-id'
            ])
            print("\n==================================================")
            print(" [SUCCESS] マイコンの接続ロックに成功しました！")
            print(" これで Deep Sleep は実行されません。")
            print(" Arduino IDE から「書き込み」を実行してください！")
            print("==================================================")
            sys.exit(0)
        except SystemExit as se:
            if se.code == 0:
                print("\n==================================================")
                print(" [SUCCESS] マイコンの接続ロックに成功しました！")
                print(" これで Deep Sleep は実行されません。")
                print(" Arduino IDE から「書き込み」を実行してください！")
                print("==================================================")
                sys.exit(0)
            else:
                print(f"[-] リトライ中... (exit code: {se.code})")
        except Exception as e:
            print(f"[-] リトライ中... ({e})")
    time.sleep(0.002)
