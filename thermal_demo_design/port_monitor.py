#!/usr/bin/env python3
"""
/dev/ttyACM* と /dev/ttyUSB* の出現・消滅をミリ秒単位で監視するツール
Bボタン操作中にどのタイミングでポートが現れて消えるかを正確に把握する
"""
import time
import os
import glob

print("==================================================")
print(" USB Serial Port Monitor (ミリ秒精度)")
print("==================================================")
print("Bボタン操作を行って、ポートの出現/消滅タイミングを観察します")
print("Ctrl+C で終了\n")

known = set()
start = time.time()

while True:
    current = set(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    
    added = current - known
    removed = known - current
    
    elapsed = time.time() - start
    
    for dev in added:
        print(f"[{elapsed:8.3f}s] +++  {dev}  が出現しました！")
    for dev in removed:
        print(f"[{elapsed:8.3f}s] ---  {dev}  が消滅しました")
    
    known = current
    time.sleep(0.002)  # 2ms間隔
