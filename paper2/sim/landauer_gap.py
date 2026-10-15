"""
landauer_gap.py
===============
物理的理論極限 (Landauer 限界) と現実の計算デバイス (ESP32-C3 実機ファームウェア)
におけるエネルギーコストの定量比較。

比較対象 (1 ビット消去 / 1 制御サイクルあたり):
 1. 理論極限 (Landauer 限界 at 300 K): kT ln2 ≈ 2.87 x 10^-21 J
 2. 実験的コロイド粒子系 Landauer 実証 (Bérut et al., Nature 2012): ~3 x 10^-21 J (~1.0 kT ln2)
 3. 超伝導 SFQ (Single Flux Quantum) 単体スイッチング: ~10^-19 J (~35 kT)
 4. 最先端 CMOS 論理ゲート単体 (7nm/5nm クラス): ~10^-16 J (~3.5 x 10^4 kT)
 5. ESP32-C3 実機ファームウェア v2 (自律運転時: noHostProbe 300ms + blink 15ms + drain 50ms ≈ 365ms):
    Active power 66 mW * 365 ms ≈ 24.1 mJ = 2.41 x 10^-2 J (約 8.4 x 10^18 kT ln2, 約 19 桁上)
 6. ESP32-C3 旧ファームウェア v1 (無条件 3000ms 待機 + センサ等 ≈ 3160ms):
    Active power 66 mW * 3160 ms ≈ 208.6 mJ = 2.09 x 10^-1 J (約 7.3 x 10^19 kT ln2)

設計エネルギー収支 (構成D, ΔT = 15 ℃, 10秒サイクル):
 - TEG (SP1848) 設計発電量 (10 mW * 10 s): +100.0 mJ
 - Deep Sleep 待機電力 (0.0165 mW * 10 s): -0.165 mJ
 - v2 起床制御電力 (66 mW * 365 ms): -24.1 mJ
 - SOS 発光パルス (100 ms 点灯): -9.9 mJ
 - 正味蓄積エネルギー: +65.8 mJ / サイクル (自律給電黒字)
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
E_BERUT2012 = LANDAUER_J * 1.05  # Bérut et al. 2012 (~1.05 kT ln2)
E_SFQ = 1.0e-19                  # 単一ジョセフソン接合 switching energy
E_CMOS = 1.0e-16                 # 7nm/5nm 単一CMOSゲート switching
# ファームウェア設計定数に基づく起床時間
# v1: 3000ms (USB wait) + 15ms (blink) + 94ms (conversion wait) + 50ms (drain) = 3159 ms
AWAKE_V1_MS = 3159.0
# v2 (自律運転時): noHostProbe 300ms + blink 15ms + drain 50ms = 365 ms (変換はプローブ中と並行)
AWAKE_V2_MS = 365.0
POWER_ACTIVE_W = 0.066           # 20 mA @ 3.3V = 66 mW

E_ESP32_V2_WAKE = POWER_ACTIVE_W * (AWAKE_V2_MS / 1000.0)  # ~24.09 mJ
E_ESP32_V1_WAKE = POWER_ACTIVE_W * (AWAKE_V1_MS / 1000.0)  # ~208.49 mJ

data = {
    "Landauer_theoretical_J": E_LANDAUER,
    "Berut_colloid_experiment_J": E_BERUT2012,
    "SFQ_gate_J": E_SFQ,
    "CMOS_gate_J": E_CMOS,
    "ESP32_v2_wake_365ms_J": E_ESP32_V2_WAKE,
    "ESP32_v1_wake_3159ms_J": E_ESP32_V1_WAKE,
    "ratio_ESP32_v2_to_Landauer": E_ESP32_V2_WAKE / E_LANDAUER,
    "ratio_ESP32_v1_to_Landauer": E_ESP32_V1_WAKE / E_LANDAUER,
    "reduction_ratio_v1_to_v2": E_ESP32_V1_WAKE / E_ESP32_V2_WAKE,
    "design_budget_10s_cycle_mJ": {
        "TEG_charge_10mW_10s": 100.0,
        "Deep_sleep_10s": -0.165,
        "v2_wake_control": -E_ESP32_V2_WAKE * 1000.0,
        "SOS_flash_100ms": -9.9,
        "net_surplus_v2": 100.0 - 0.165 - (E_ESP32_V2_WAKE * 1000.0) - 9.9,
        "net_surplus_v1": 100.0 - 0.165 - (E_ESP32_V1_WAKE * 1000.0) - 9.9
    }
}


def main():
    with open(os.path.join(OUT_DIR, "landauer_gap.json"), "w") as f:
        json.dump(data, f, indent=2)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    ax = axes[0]
    categories = [
        "Landauer\nLimit",
        "Colloidal Exp.\n(Nature 2012)",
        "Supercond. SFQ\n(Logic Gate)",
        "Advanced CMOS\n(Logic Gate)",
        "ESP32-C3 v2\n(~365ms Wake)",
        "ESP32-C3 v1\n(~3.2s Wake)",
    ]
    energies_J = [E_LANDAUER, E_BERUT2012, E_SFQ, E_CMOS, E_ESP32_V2_WAKE, E_ESP32_V1_WAKE]
    colors = ["#27ae60", "#2ecc71", "#2980b9", "#8e44ad", "#e67e22", "#c0392b"]

    bars = ax.bar(categories, energies_J, color=colors)
    ax.set_yscale("log")
    ax.set_ylabel("Energy Dissipated per Operation / Wake [J]")
    ax.set_title("(a) Theoretical Limits vs. Physical Microcontrollers")
    ax.grid(True, which="both", ls=":", alpha=0.3)

    for bar, val in zip(bars, energies_J):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height * 2.0,
            f"{val:.1e} J",
            ha="center",
            va="bottom",
            fontsize=7.5,
        )

    ax = axes[1]
    items = ["TEG Harvest\n(10 s)", "Deep Sleep\n(10 s)", "Wake Control\n(v2 ~365 ms)", "SOS Optical\n(100 ms)", "Net Surplus\n(Self-Powered)"]
    vals_mJ = [
        100.0,
        -0.165,
        -E_ESP32_V2_WAKE * 1000.0,
        -9.9,
        100.0 - 0.165 - (E_ESP32_V2_WAKE * 1000.0) - 9.9
    ]
    bar_colors = ["#27ae60", "#7f8c8d", "#e67e22", "#e74c3c", "#2980b9"]

    b2 = ax.bar(items, vals_mJ, color=bar_colors)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("Energy Budget per 10 s Cycle [mJ]")
    ax.set_title(r"(b) Configuration D Energy Balance ($\Delta T = 15^\circ\mathrm{C}$)")
    ax.grid(True, ls=":", alpha=0.3)

    for bar, val in zip(b2, vals_mJ):
        height = bar.get_height()
        ypos = height + (2.5 if val >= 0 else -6.5)
        ax.text(bar.get_x() + bar.get_width() / 2.0, ypos, f"{val:+.1f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_landauer_gap.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_landauer_gap.png"), dpi=200)

    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
