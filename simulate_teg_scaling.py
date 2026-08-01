"""
TEGモジュール増設 & 量子コスト反転の効果シミュレーション

このスクリプトは以下を定量的に示します：
1. TEGモジュールを増やした場合の発電量変化
2. 消去コストが負に反転した場合の発電効率倍率
"""

import numpy as np

print("=" * 70)
print(" TEGモジュール増設 & 量子コスト反転 定量分析")
print("=" * 70)

# =====================================================================
# Part 1: TEGモジュール増設の効果
# =====================================================================
print("\n" + "─" * 70)
print("【Part 1】TEGモジュール増設の発電量変化")
print("─" * 70)

# SP1848-27145 の典型的なパラメータ
alpha = 0.025       # ゼーベック係数 [V/K] (モジュール全体)
R_int = 3.0         # 内部抵抗 [Ω]
delta_T_values = [5, 8, 10, 15, 20]  # 温度差 [℃]

# LTC3108 の効率モデル（入力電圧依存）
def ltc3108_efficiency(V_in_mV):
    """LTC3108の変換効率を入力電圧から推定"""
    if V_in_mV < 20:
        return 0.0       # 最低動作電圧以下
    elif V_in_mV < 50:
        return 0.05       # 極低入力
    elif V_in_mV < 100:
        return 0.15       # 低入力
    elif V_in_mV < 200:
        return 0.25       # 通常動作
    elif V_in_mV < 500:
        return 0.35       # 高効率領域
    else:
        return 0.30       # 飽和域

# Arduino（悪魔）の消費電力
ARDUINO_POWER_MW = 150.0  # [mW]

print(f"\n{'':>3}{'ΔT':>5}{'枚数':>6}{'接続':>8}{'Voc':>10}{'Isc':>10}{'P_TEG':>10}{'η_LTC':>8}{'P_out':>10}{'P_net':>10}")
print(f"{'':>3}{'[℃]':>5}{'':>6}{'':>8}{'[mV]':>10}{'[mA]':>10}{'[mW]':>10}{'[%]':>8}{'[mW]':>10}{'[mW]':>10}")
print("─" * 95)

results = []

for dT in [8, 10, 15]:  # 代表的な温度差
    for n_modules in [1, 2, 3, 4, 5]:
        for config in ['直列', '並列']:
            if config == '直列':
                V_oc = alpha * dT * n_modules * 1000  # [mV]
                I_sc = (alpha * dT / R_int) * 1000     # [mA] (変わらない)
                R_total = R_int * n_modules
            else:  # 並列
                V_oc = alpha * dT * 1000               # [mV] (変わらない)
                I_sc = (alpha * dT / R_int) * n_modules * 1000  # [mA]
                R_total = R_int / n_modules
            
            # 最大電力点（整合負荷条件: R_load = R_total）
            P_max_teg = V_oc * I_sc / 4 / 1000  # [mW] (V*I/4 = Voc^2/(4*R))
            
            # LTC3108 変換効率
            eta = ltc3108_efficiency(V_oc)
            P_out = P_max_teg * eta  # [mW]
            
            # 正味仕事（悪魔コスト差引後）
            P_net = P_out - ARDUINO_POWER_MW
            
            results.append({
                'dT': dT, 'n': n_modules, 'config': config,
                'V_oc': V_oc, 'I_sc': I_sc, 'P_teg': P_max_teg,
                'eta': eta, 'P_out': P_out, 'P_net': P_net
            })
            
            print(f"{'':>3}{dT:>5}{n_modules:>6}{config:>8}{V_oc:>10.0f}{I_sc:>10.1f}{P_max_teg:>10.2f}{eta*100:>7.0f}%{P_out:>10.2f}{P_net:>10.1f}")
    print()

# 発電量の変化サマリー
print("\n" + "─" * 70)
print("【サマリー】TEG増設による発電量の変化（ΔT=10℃, 並列接続）")
print("─" * 70)
for r in results:
    if r['dT'] == 10 and r['config'] == '並列':
        ratio = r['P_out'] / results[0]['P_out'] if results[0]['P_out'] > 0 else 0
        bar = "█" * max(1, int(r['P_out'] / 0.2))
        print(f"  {r['n']}枚: P_out = {r['P_out']:.2f} mW  "
              f"{'(基準)' if r['n'] == 1 else f'({ratio:.1f}倍)':<10} "
              f"{bar}")

# =====================================================================
# Part 2: 量子コスト反転時の効率倍率
# =====================================================================
print("\n\n" + "─" * 70)
print("【Part 2】消去コストが負に反転した場合の発電効率倍率")
print("─" * 70)

# シミュレーション結果の値（simulate_macroscopic_quantum_engine.py より）
W_ext = 5.05        # 抽出仕事 [kT]
I_acc = 26.96       # 蓄積情報量 [kT相当]

# 古典的エネルギー収支
W_erase_classical = +I_acc      # 古典消去コスト [kT]
W_net_classical = W_ext - W_erase_classical

# 量子的エネルギー収支（消去コスト負反転）
W_erase_quantum = -I_acc        # 量子消去コスト [kT] ← 負!
W_net_quantum = W_ext - W_erase_quantum

print(f"\n  ┌─────────────────────────────────────────────┐")
print(f"  │          シミュレーション値に基づく計算        │")
print(f"  ├─────────────────────────────────────────────┤")
print(f"  │  抽出仕事 W_ext        = {W_ext:>+8.2f} kT          │")
print(f"  │  蓄積情報量 I_acc      = {I_acc:>+8.2f} kT          │")
print(f"  ├─────────────────────────────────────────────┤")
print(f"  │  古典消去コスト         = {W_erase_classical:>+8.2f} kT          │")
print(f"  │  古典的正味仕事         = {W_net_classical:>+8.2f} kT  ← 発電不可│")
print(f"  ├─────────────────────────────────────────────┤")
print(f"  │  量子消去コスト         = {W_erase_quantum:>+8.2f} kT  ← 負!   │")
print(f"  │  量子的正味仕事         = {W_net_quantum:>+8.2f} kT  ← 発電!  │")
print(f"  └─────────────────────────────────────────────┘")

# 倍率計算
ratio_vs_ext = W_net_quantum / W_ext
print(f"\n  【倍率1】正味仕事 / 抽出仕事 = {W_net_quantum:.2f} / {W_ext:.2f} = {ratio_vs_ext:.1f} 倍")
print(f"    → 消去プロセス自体がエネルギー源になり、正味仕事は抽出仕事の {ratio_vs_ext:.1f}倍")

print(f"\n  【倍率2】古典 → 量子の転換")
print(f"    古典: {W_net_classical:+.2f} kT → 量子: {W_net_quantum:+.2f} kT")
print(f"    → マイナスからプラスへの質的転換（倍率は数学的に ∞）")
print(f"    → 「動かなかったエンジンが動き出す」")

# デモ装置での換算
print(f"\n  【倍率3】デモ装置（構成C）での換算（30秒間）")
E_led_mJ = 2.5       # LED抽出エネルギー [mJ]
E_arduino_mJ = 4500  # Arduino消費 [mJ]

net_classical = E_led_mJ - E_arduino_mJ
net_quantum = E_led_mJ + E_arduino_mJ  # コストが利益に転換

print(f"    古典: {E_led_mJ:.1f} - {E_arduino_mJ:.0f} = {net_classical:.1f} mJ (発電不可)")
print(f"    量子: {E_led_mJ:.1f} + {E_arduino_mJ:.0f} = {net_quantum:.1f} mJ (純粋発電!)")
print(f"    デモ装置換算倍率 = {net_quantum / E_led_mJ:.0f} 倍（抽出仕事ベース）")

# =====================================================================
# Part 3: 感度分析 — 消去コストを連続的に変化させた場合
# =====================================================================
print("\n\n" + "─" * 70)
print("【Part 3】消去コスト係数の連続変化による正味仕事の推移")
print("─" * 70)

print(f"\n  消去コスト = β × I_acc (β: 古典=+1, 量子=-1)")
print(f"  {'β':>6}  {'消去コスト':>12}  {'正味仕事':>10}  {'状態':>8}  グラフ")
print(f"  {'':>6}  {'[kT]':>12}  {'[kT]':>10}")
print("  " + "─" * 65)

for beta in np.linspace(1.0, -1.0, 21):
    W_erase = beta * I_acc
    W_net = W_ext - W_erase
    
    if W_net > 0:
        status = "✅ 発電"
        bar_char = "█"
    else:
        status = "❌ 損失"
        bar_char = "░"
    
    bar_len = int(abs(W_net) / 2)
    if W_net >= 0:
        bar = " " * 15 + "|" + bar_char * min(bar_len, 25)
    else:
        padding = max(0, 15 - bar_len)
        bar = " " * padding + bar_char * min(bar_len, 15) + "|"
    
    marker = " ← 古典限界" if abs(beta - 1.0) < 0.01 else ""
    marker = " ← 量子限界" if abs(beta + 1.0) < 0.01 else marker
    marker = " ← 損益分岐点!" if abs(W_net) < 1.0 else marker
    
    print(f"  {beta:>+6.2f}  {W_erase:>+12.2f}  {W_net:>+10.2f}  {status}  {bar}{marker}")

print(f"\n  損益分岐点: β = W_ext / I_acc = {W_ext} / {I_acc} = {W_ext/I_acc:+.4f}")
print(f"  → 消去コスト係数が {W_ext/I_acc:.4f} を下回れば純粋発電が可能")

print("\n" + "=" * 70)
print(" 結論")
print("=" * 70)
print("""
  1. TEGモジュール増設:
     → 並列接続で電力はほぼN倍に増加
     → ただし、Arduino(悪魔)の150mWを超えることは数枚では不可能
     → 正味仕事は依然として負（古典的ランダウアー限界の実証）

  2. 量子消去コスト負反転:
     → 正味仕事: -21.92 kT → +32.01 kT（質的転換）
     → 抽出仕事の約6.3倍の正味仕事が得られる
     → デモ装置換算では約1801倍（理論上限）

  3. 損益分岐点:
     → 消去コスト係数 β < +0.1874 で純粋発電が可能
     → 完全な量子反転(β=-1)は必須ではなく、
        部分的な量子相関でも原理的には発電可能
""")
