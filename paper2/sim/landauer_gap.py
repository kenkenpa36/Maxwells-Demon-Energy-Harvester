"""
landauer_gap.py
===============
理想的な物理極限 (Landauer 限界) と現実の電子機器 (ESP32-C3 デーモン実機)
におけるエネルギーコストの定量比較 (桁違いの可視化)。

比較対象 (1 ビット / 1 操作あたり):
 1. 理論極限 (Landauer 限界 at 300 K): kT ln2 = 2.87 x 10^-21 J (1.0 kT)
 2. 最先端 CMOS 論理ゲート単体 (7nm クラス): ~10^-16 J (~3.5 x 10^4 kT)
 3. 超伝導 SFQ (Single Flux Quantum) 論理: ~10^-19 J (~3.5 x 10^1 kT, 4K 冷却除く)
 4. 本プロジェクト 構成D v2 ファームウェア (ESP32-C3 起床 10ms):
    Active power 66 mW * 10 ms = 0.66 mJ = 6.6 x 10^-4 J (~2.3 x 10^17 kT)
    -> Landauer 限界の 約 2.3 x 10^17 倍

実機 (構成D) での自律エネルギー収支 (体温 ΔT = 15 ℃):
 - TEG (SP1848) 発電電力: ~10 mW
 - 10 秒スリープ中の蓄電: E_charge = 100 mJ
 - Deep Sleep 待機電力: 0.0165 mW * 10 s = 0.165 mJ
 - 起床中 (10 ms) 消費: E_active = 0.66 mJ
 - 発光パルス (100 ms) 消費: E_flash = 9.9 mJ
 - 正味蓄積エネルギー W_net_cycle = +89.3 mJ (> 0 自律連続給電成立!)
"""
import os
import json
import numpy as np
import plotstyle  # noqa: F401
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(HERE, "..", "figs")
OUT_DIR = os.path.join(HERE, "..", "results")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

KB = 1.380649e-23
T_ROOM = 300.0
KT_J = KB * T_ROOM
LANDAUER_J = KT_J * np.log(2.0)

E_LANDAUER = LANDAUER_J
E_SFQ = 1e-19
E_CMOS = 1e-16
E_ESP32_V2_WAKE = 6.6e-4
E_ESP32_V1_WAKE = 2.0e-1

data = {
    "Landauer_J": E_LANDAUER,
    "SFQ_J": E_SFQ,
    "CMOS_gate_J": E_CMOS,
    "ESP32_v2_wake_10ms_J": E_ESP32_V2_WAKE,
    "ESP32_v1_wake_3s_J": E_ESP32_V1_WAKE,
    "ratio_ESP32_v2_to_Landauer": E_ESP32_V2_WAKE / E_LANDAUER,
    "ratio_ESP32_v1_to_Landauer": E_ESP32_V1_WAKE / E_LANDAUER,
    "ratio_v1_to_v2_waste": E_ESP32_V1_WAKE / E_ESP32_V2_WAKE,
}


def main():
    with open(os.path.join(OUT_DIR, "landauer_gap.json"), "w") as f:
        json.dump(data, f, indent=2)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    ax = axes[0]
    categories = [
        "Landauer\n理論限界",
        "超伝導SFQ\n(論理単体)",
        "最先端CMOS\n(論理単体)",
        "実機悪魔 v2\n(10ms起床)",
        "旧実機悪魔 v1\n(3s待機)",
    ]
    energies_J = [E_LANDAUER, E_SFQ, E_CMOS, E_ESP32_V2_WAKE, E_ESP32_V1_WAKE]
    colors = ["#27ae60", "#2980b9", "#8e44ad", "#e67e22", "#c0392b"]

    bars = ax.bar(categories, energies_J, color=colors)
    ax.set_yscale("log")
    ax.set_ylabel("1操作あたりのエネルギー消費 [J]")
    ax.set_title("(a) 理論限界と現実の悪魔の17桁のギャップ")
    ax.grid(True, which="both", ls=":", alpha=0.3)

    for bar, val in zip(bars, energies_J):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height * 2.0,
            f"{val:.1e} J",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax = axes[1]
    items = ["TEG発電\n(10秒間)", "Deep Sleep\n(10秒間)", "起床10ms\n(v2)", "SOS発光\n(100ms)", "正味蓄積\n(自律給電)"]
    vals_mJ = [100.0, -0.165, -0.66, -9.9, +89.275]
    bar_colors = ["#27ae60", "#7f8c8d", "#e67e22", "#e74c3c", "#2980b9"]

    b2 = ax.bar(items, vals_mJ, color=bar_colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("1サイクル (10秒) あたりの収支 [mJ]")
    ax.set_title("(b) 構成D実機における自律給電エネルギー収支 (ΔT=15℃)")
    ax.grid(True, ls=":", alpha=0.3)

    for bar, val in zip(b2, vals_mJ):
        height = bar.get_height()
        ypos = height + (2.0 if val >= 0 else -6.0)
        ax.text(bar.get_x() + bar.get_width() / 2.0, ypos, f"{val:+.1f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_landauer_gap.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_landauer_gap.png"), dpi=200)

    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
