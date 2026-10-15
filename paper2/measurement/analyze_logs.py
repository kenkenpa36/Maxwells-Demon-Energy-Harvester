"""
analyze_logs.py
===============
構成D ESP32-C3 ファームウェア (v2) のシリアル出力 CSV データの解析ツール。

主な機能:
 1. シリアルポート (--port /dev/ttyACM0 等) からのリアルタイムログ収集 & CSV保存
 2. 保存済み CSV ログファイル (--file path/to/log.csv) の集計・エネルギー収支解析
 3. 実機未接続時のファームウェア設計定数に基づく理論予測ベンチマーク (--benchmark)
"""
import argparse
import json
import os
import sys
import numpy as np

# プロット用スタイル
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "sim"))
import plotstyle  # noqa: F401
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results")
FIG_DIR = os.path.join(HERE, "..", "figs")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)


def parse_csv_file(filepath):
    """CSV ファイルから数値を抽出して dictionary のリストを返す。"""
    rows = []
    headers = None
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("═") or line.startswith(">"):
                continue
            parts = line.split(",")
            if "cycle" in parts or "T_hot_C" in parts:
                headers = [p.strip() for p in parts]
                continue
            if headers and len(parts) == len(headers):
                try:
                    row = {h: float(v.strip()) for h, v in zip(headers, parts) if h != "demon_state"}
                    row["demon_state"] = parts[headers.index("demon_state")].strip()
                    rows.append(row)
                except ValueError:
                    continue
    return rows


def capture_serial_port(port, baud, outfile, max_cycles=None):
    """シリアルポートから直接ログを読み取って CSV に保存する。"""
    try:
        import serial
    except ImportError:
        print("エラー: pySerial がインストールされていません。(pip install pyserial)")
        sys.exit(1)

    print(f"シリアルポート {port} ({baud} bps) に接続中...")
    with serial.Serial(port, baud, timeout=2.0) as ser, open(outfile, "w", encoding="utf-8") as f:
        cycle_count = 0
        while True:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                print(line)
                f.write(line + "\n")
                f.flush()
                if "cycle" in line:
                    continue
                if "," in line and not line.startswith("#") and not line.startswith("═"):
                    cycle_count += 1
                    if max_cycles and cycle_count >= max_cycles:
                        print(f"{max_cycles} サイクル記録完了。")
                        break


def generate_design_model_benchmark():
    """実機未接続時にファームウェアの設計パラメータに基づく理論比較モデルを計算する。

    注意: これは実測値ではなく、demon_policy.h および maxwell_demon_harvester_esp32c3_v2.ino
    に定義された設計値 (定数) に基づく理論予測である。
    """
    v1_rows = []
    v2_rows = []
    c_cap = 1.0  # 1.0 F

    # 10 サイクルのモデル計算 (充電と発光が交互に発生する定常サイクル想定)
    for c in range(1, 11):
        is_flash = (c % 2 == 0)
        v_before = 2.6
        v_after = 2.4 if is_flash else 2.6
        w_ext = 0.5 * c_cap * (v_before**2 - v_after**2) * 1000.0 if is_flash else 0.0
        w_landauer = 0.0165 * 10.0  # 10s sleep cost = 0.165 mJ

        # v1 (旧ファームウェア設計定数)
        # 3000ms (USB) + 15ms (blink) + 94ms (sensor wait) + 50ms (drain) = 3159 ms
        awake_v1 = 3159.0
        w_active_v1 = 66.0 * (awake_v1 / 1000.0)  # ≈ 208.5 mJ
        w_net_v1 = w_ext - (w_active_v1 + w_landauer)
        v1_rows.append({
            "cycle": c,
            "deltaT_C": 12.0,
            "V_store_mV": 2500.0,
            "demon_state": "DEMON_ACT" if is_flash else "CHARGING",
            "W_ext_mJ": w_ext,
            "W_landauer_mJ": w_landauer,
            "W_active_mJ": w_active_v1,
            "W_net_total_mJ": w_net_v1,
            "awake_ms": awake_v1,
        })

        # v2 (新ファームウェア自律運転定数)
        # noHostProbe 300ms + blink 15ms + drain 50ms = 365 ms (センサ変換はプローブと並行)
        awake_v2 = 365.0
        w_active_v2 = 66.0 * (awake_v2 / 1000.0)  # ≈ 24.1 mJ
        w_net_v2 = w_ext - (w_active_v2 + w_landauer)
        v2_rows.append({
            "cycle": c,
            "deltaT_C": 12.0,
            "V_store_mV": 2500.0,
            "demon_state": "DEMON_ACT" if is_flash else "CHARGING",
            "W_ext_mJ": w_ext,
            "W_landauer_mJ": w_landauer,
            "W_active_mJ": w_active_v2,
            "W_net_total_mJ": w_net_v2,
            "awake_ms": awake_v2,
        })
    return v1_rows, v2_rows


def main():
    parser = argparse.ArgumentParser(description="Analyze Maxwell's Demon hardware logs.")
    parser.add_argument("--file", type=str, default=None, help="Path to recorded CSV file.")
    parser.add_argument("--port", type=str, default=None, help="Serial port to capture from (e.g. /dev/ttyACM0).")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200).")
    parser.add_argument("--out", type=str, default="captured_log.csv", help="Output file for serial capture.")
    parser.add_argument("--benchmark", action="store_true", help="Generate theoretical benchmark from firmware constants.")
    args = parser.parse_args()

    if args.port:
        capture_serial_port(args.port, args.baud, args.out)
        args.file = args.out

    if args.file and os.path.exists(args.file):
        rows_v2 = parse_csv_file(args.file)
        rows_v1 = None
        source_label = f"実機ログ解析 ({os.path.basename(args.file)})"
        is_simulated = False
    elif args.benchmark or args.file is None:
        rows_v1, rows_v2 = generate_design_model_benchmark()
        source_label = "ファームウェア設計定数に基づく理論予測モデル (未接続)"
        is_simulated = True
    else:
        print(f"エラー: 指定されたファイルが見つかりません: {args.file}")
        sys.exit(1)

    avg_awake_v2 = np.mean([r["awake_ms"] for r in rows_v2])
    avg_active_v2 = np.mean([r["W_active_mJ"] for r in rows_v2])
    avg_net_v2 = np.mean([r["W_net_total_mJ"] for r in rows_v2])

    summary = {
        "source": source_label,
        "is_measured_data": not is_simulated,
        "v2_avg_awake_ms": float(avg_awake_v2),
        "v2_avg_active_mJ": float(avg_active_v2),
        "v2_avg_net_total_mJ": float(avg_net_v2),
    }

    if rows_v1:
        avg_awake_v1 = np.mean([r["awake_ms"] for r in rows_v1])
        avg_active_v1 = np.mean([r["W_active_mJ"] for r in rows_v1])
        avg_net_v1 = np.mean([r["W_net_total_mJ"] for r in rows_v1])
        summary["v1_avg_awake_ms"] = float(avg_awake_v1)
        summary["v1_avg_active_mJ"] = float(avg_active_v1)
        summary["v1_avg_net_total_mJ"] = float(avg_net_v1)
        summary["reduction_ratio_v1_to_v2"] = float(avg_active_v1 / avg_active_v2)

    with open(os.path.join(OUT_DIR, "hardware_log_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Plot: Design model comparison
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    cycles = [r["cycle"] for r in rows_v2]

    ax = axes[0]
    if rows_v1:
        ax.plot(cycles, [r["W_active_mJ"] for r in rows_v1], "r^--", label="v1 (Unconditioned ~3.2s Wake)")
    ax.plot(cycles, [r["W_active_mJ"] for r in rows_v2], "go-", label="v2 (Optimized ~365ms Wake)")
    ax.set_xlabel("Cycle Number")
    ax.set_ylabel(r"Demon Wake Energy $W_{\mathrm{active}}$ [mJ]")
    ax.set_title("(a) Wake-Time Energy Reduction (Design Model)")
    ax.legend(fontsize=8)
    ax.grid(True, ls=":", alpha=0.3)

    ax = axes[1]
    if rows_v1:
        ax.plot(cycles, [r["W_net_total_mJ"] for r in rows_v1], "r^--", label="v1 Net Balance (Deficit)")
    ax.plot(cycles, [r["W_net_total_mJ"] for r in rows_v2], "bo-", label="v2 Net Balance (Surplus)")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("Cycle Number")
    ax.set_ylabel(r"Net Energy Surplus $W_{\mathrm{net}}$ [mJ]")
    ax.set_title("(b) Energy Surplus Achievement (Design Model)")
    ax.legend(fontsize=8)
    ax.grid(True, ls=":", alpha=0.3)

    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_hardware_v1_vs_v2.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_hardware_v1_vs_v2.png"), dpi=200)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
