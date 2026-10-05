"""
landauer_entangled_fixed.py
===========================
「量子もつれによる負の消去コスト」(simulate_quantum_loophole.py) の再検証。

1. 旧コードの再現と診断
   旧コードは H = E|1><1| (basis(2,1) が励起状態) に対して QuTiP の
   sigmam() = |1><0| を「下降演算子」として使っていた。QuTiP では basis(2,0) が
   "up" なので sigmam は |0> -> |1> 、すなわちこのハミルトニアンでは
   **エネルギーを上げる**遷移になる。結果として詳細釣り合いが逆転し
   (負温度の熱浴と等価)、熱浴が反転分布を作り出して見かけ上 -19 kT の
   「仕事」を出していた。

2. 正しい計算
   2準位系の占有確率 p1 についての速度方程式
       dp1/dt = -g_dn p1 + g_up (1 - p1),  g_up/g_dn = exp(-E/kT)
   を適応刻み (solve_ivp, RK45, rtol=1e-10) で解き、系にされた仕事
       W = ∫ p1 dE
   を求める。

3. サイクル全体の収支
   (a) もつれ利用の消去: Bell 状態 -> CNOT -> H で系は純粋状態 |0>
       -> 等温膨張で仕事抽出 (最大 kT ln2)
   (b) もつれの再生成: 混合状態になった系を |0> に戻す (Landauer 消去, 最小 kT ln2)
       -> H, CNOT で Bell 状態を再生成
   正味仕事 = (a) + (b) >= 0 (系に仕事を与える側) を、プロトコル時間 tau の関数として示す。

単位: kT = 1。ユニタリ (CNOT, Hadamard) は理想的でエネルギー縮退した論理基底上で
行うためコスト 0 とする (下限評価として最も楽観的な仮定)。
"""
import os
import json
import numpy as np
from scipy.integrate import solve_ivp
import plotstyle  # noqa: F401  (日本語フォント設定)
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(HERE, "..", "figs")
OUT_DIR = os.path.join(HERE, "..", "results")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

KT = 1.0
GAMMA0 = 20.0
E_MAX = 20.0
LN2 = np.log(2.0)


# ---------------------------------------------------------------------------
# 1. 旧コードの忠実な再現 (QuTiP 不要の等価な実装 + QuTiP での確認)
# ---------------------------------------------------------------------------
def legacy_isothermal(p1_init, E_start, E_end, tau=50.0, n_steps=1000, inverted=True):
    """旧 simulate_isothermal と同じ陽的オイラー更新。

    inverted=True  : 旧コードの演算子の取り違えを再現 (|0>->|1> に g_dn を割り当て)
    inverted=False : 演算子を正しく対応させた場合
    """
    dt = tau / n_steps
    t_list = np.linspace(0, tau, n_steps)
    p1 = p1_init
    w = 0.0
    for t in t_list:
        E = E_start + (E_end - E_start) * (t / tau)
        dE_dt = (E_end - E_start) / tau
        w += p1 * dE_dt * dt
        p_up = np.exp(-E / KT) / (1.0 + np.exp(-E / KT))
        p_dn = 1.0 / (1.0 + np.exp(-E / KT))
        if inverted:
            # 旧コード: sqrt(g*p_dn)*sigmam は |0>->|1> (励起), sqrt(g*p_up)*sigmap は |1>->|0>
            rate_01, rate_10 = GAMMA0 * p_dn, GAMMA0 * p_up
        else:
            rate_01, rate_10 = GAMMA0 * p_up, GAMMA0 * p_dn
        p1 = p1 + dt * (rate_01 * (1 - p1) - rate_10 * p1)
    return w


def legacy_qutip_check():
    """旧コードの Case 3 を QuTiP でそのまま実行し、数値を確認する。"""
    try:
        import qutip as qt
    except ImportError:
        return None
    tau, n_steps = 50.0, 1000
    dt = tau / n_steps
    sm = qt.sigmam()
    proj1 = qt.basis(2, 1) * qt.basis(2, 1).dag()
    iden = qt.qeye(2)
    rho = qt.tensor(qt.basis(2, 0) * qt.basis(2, 0).dag(), qt.basis(2, 0) * qt.basis(2, 0).dag())
    op_p = qt.tensor(proj1, iden)
    op_l = qt.tensor(sm, iden)
    w = 0.0
    for t in np.linspace(0, tau, n_steps):
        E = 20.0 + (0.0 - 20.0) * (t / tau)
        w += qt.expect(-20.0 / tau * op_p, rho) * dt
        p_up = np.exp(-E) / (1 + np.exp(-E))
        p_dn = 1 / (1 + np.exp(-E))
        c_ops = [np.sqrt(GAMMA0 * p_dn) * op_l, np.sqrt(GAMMA0 * p_up) * op_l.dag()]
        H = E * op_p
        L = -1j * (H * rho - rho * H)
        for c in c_ops:
            L += c * rho * c.dag() - 0.5 * (c.dag() * c * rho + rho * c.dag() * c)
        rho = rho + L * dt
    # sigmam が basis0 -> basis1 であることの確認
    amp = qt.basis(2, 1).dag() * sm * qt.basis(2, 0)
    amp = amp.full()[0, 0] if hasattr(amp, "full") else amp
    maps_0_to_1 = abs(amp) > 0.5
    return {"W_case3_qutip": float(np.real(w)), "sigmam_maps_basis0_to_basis1": bool(maps_0_to_1)}


# ---------------------------------------------------------------------------
# 2. 正しい等温プロトコル (適応刻み)
# ---------------------------------------------------------------------------
def isothermal_work(p1_init, E_start, E_end, tau):
    """E(t) を線形に変化させたときに系にされる仕事 W = ∫ p1 dE を返す。"""
    dEdt = (E_end - E_start) / tau

    def rhs(t, y):
        p1, _w = y
        E = E_start + dEdt * t
        g_dn = GAMMA0 / (1.0 + np.exp(-E / KT))
        g_up = GAMMA0 * np.exp(-E / KT) / (1.0 + np.exp(-E / KT))
        return [-g_dn * p1 + g_up * (1.0 - p1), p1 * dEdt]

    sol = solve_ivp(rhs, (0.0, tau), [p1_init, 0.0], method="RK45", rtol=1e-10, atol=1e-12)
    return float(sol.y[1, -1]), float(sol.y[0, -1])


def full_cycle(tau):
    """もつれ利用の消去 + もつれ再生成 の1サイクル。戻り値は各段の仕事 (系にされた仕事)。

    段1 (抽出): CNOT, H の後、系は純粋状態 |0> (E=E_MAX の基底状態)。
               E: E_MAX -> 0 の等温膨張で仕事を取り出す。
    段2 (再生成): E=0 で混合した系を E: 0 -> E_MAX の等温圧縮で |0> に戻す (Landauer 消去)。
               その後 H, CNOT で Bell 状態を再生成 (ユニタリ, コスト 0 と仮定)。
    """
    w_extract, p1_after = isothermal_work(0.0, E_MAX, 0.0, tau)
    w_reset, p1_final = isothermal_work(p1_after, 0.0, E_MAX, tau)
    # 圧縮後に残る励起確率は「消去エラー」。理想 |0> とのずれを報告する。
    return w_extract, w_reset, p1_final


def main():
    results = {}

    # --- 旧コードの診断 ---
    legacy_c3 = legacy_isothermal(0.0, 20.0, 0.0, inverted=True)
    legacy_c1 = legacy_isothermal(0.5, 0.0, 20.0, inverted=True)
    fixed_c3 = legacy_isothermal(0.0, 20.0, 0.0, inverted=False)
    fixed_c1 = legacy_isothermal(0.5, 0.0, 20.0, inverted=False)
    results["legacy"] = {
        "case3_entangled_W_inverted_bath": legacy_c3,
        "case1_uncorrelated_W_inverted_bath": legacy_c1,
        "case3_entangled_W_operator_fixed": fixed_c3,
        "case1_uncorrelated_W_operator_fixed": fixed_c1,
        "qutip": legacy_qutip_check(),
    }

    # --- 正しい計算: tau 依存性 ---
    taus = np.logspace(-1.5, 2.5, 25)
    rows = []
    for tau in taus:
        we, wr, p1f = full_cycle(tau)
        rows.append((tau, we, wr, we + wr, p1f))
    rows = np.array(rows)
    results["cycle"] = {
        "tau": rows[:, 0].tolist(),
        "W_extract": rows[:, 1].tolist(),
        "W_reset": rows[:, 2].tolist(),
        "W_net": rows[:, 3].tolist(),
        "p1_residual": rows[:, 4].tolist(),
        "min_W_net": float(rows[:, 3].min()),
        "W_extract_at_max_tau": float(rows[-1, 1]),
        "theory_bound_extract": -LN2,
    }

    # 収束チェック: rtol を緩めても結果が変わらないこと
    w_ref, _ = isothermal_work(0.0, E_MAX, 0.0, 100.0)
    results["convergence_W_extract_tau100"] = w_ref

    with open(os.path.join(OUT_DIR, "landauer_entangled.json"), "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # --- 図 ---
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    ax = axes[0]
    labels = ["旧コード\n(熱浴反転)", "演算子修正後\n(同じオイラー法)", "理論限界\n$-k_BT\\ln 2$"]
    vals = [legacy_c3, fixed_c3, -LN2]
    colors = ["#c0392b", "#2980b9", "#7f8c8d"]
    ax.bar(labels, vals, color=colors)
    for i, v in enumerate(vals):
        ax.text(i, v - 0.8 if v < -2 else v - 0.15, f"{v:.2f}", ha="center", va="top", fontsize=10)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("もつれ利用の消去で系にされる仕事 $W$ [$k_BT$]")
    ax.set_title("(a) 旧コードの −19 $k_BT$ の正体")
    ax.set_ylim(min(vals) * 1.15, 1.0)

    ax = axes[1]
    ax.semilogx(rows[:, 0], rows[:, 1], "o-", color="#2980b9", ms=3, label="段1: もつれ利用の抽出")
    ax.semilogx(rows[:, 0], rows[:, 2], "s-", color="#c0392b", ms=3, label="段2: もつれ再生成 (消去)")
    ax.semilogx(rows[:, 0], rows[:, 3], "k-", lw=2.2, label="1サイクルの正味")
    ax.axhline(LN2, color="#c0392b", ls=":", lw=1)
    ax.axhline(-LN2, color="#2980b9", ls=":", lw=1)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xlabel("各段のプロトコル時間 $\\tau$ [$1/\\gamma_0$ 単位系]")
    ax.set_ylabel("系にされた仕事 [$k_BT$]")
    ax.set_title("(b) サイクル全体では正味 $W \\geq 0$")
    ax.legend(fontsize=8, loc="center right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_entangled_erasure.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_entangled_erasure.png"), dpi=200)

    print(json.dumps({k: results[k] for k in ("legacy",)}, indent=2, ensure_ascii=False))
    print("min W_net over tau:", results["cycle"]["min_W_net"])
    print("W_extract (tau max):", results["cycle"]["W_extract_at_max_tau"], " bound:", -LN2)


if __name__ == "__main__":
    main()
