"""
verify_second_law.py
====================
3 重量子ドット自律デーモン (simulate_engine.py と同一模型) の熱力学的整合性の検証。

検証項目
 (1) 全熱浴の熱流から求めたエントロピー生成率 σ = -Σ_α Q̇_α / T_α が非負であること
 (2) 悪魔の熱浴温度 T_D を作業浴温度 T に近づけると出力 Ẇ が 0 以下になること
     (等温では仕事を取り出せない = 第二法則)
 (3) 第一法則 (エネルギー保存): Ẇ = Σ_α Q̇_α
 (4) Ẇ > 0 の領域では、熱機関としての効率 η = Ẇ / Q̇_in が
     カルノー効率 1 - T_D/T を超えないこと

熱流は「局所的」なエネルギー H_base (トンネル結合 g を含まない) を用いて計算する。
g は小さい (g <= 0.1 << T) 範囲に限定し、局所 Lindblad 方程式の妥当域で評価する
(Levy & Kosloff 2014 が指摘する第二法則の見かけの破れを避けるため)。

単位: 旧コードと同じ任意単位 (k_B = 1)。
"""
import os
import json
import numpy as np
import qutip as qt
import plotstyle  # noqa: F401
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(HERE, "..", "figs")
OUT_DIR = os.path.join(HERE, "..", "results")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

sm, sz, iden = qt.sigmam(), qt.sigmaz(), qt.qeye(2)
dL = qt.tensor(sm, iden, iden)
dR = qt.tensor(sz, sm, iden)
dD = qt.tensor(sz, sz, sm)
I3 = qt.tensor(iden, iden, iden)
nL, nR, nD = dL.dag() * dL, dR.dag() * dR, dD.dag() * dD

# 旧コードと同じパラメータ
EPS, U, U_LR = 0.0, 200.0, 5000.0
T = 1000.0
MU_L, MU_R, MU_D = 50.0, -50.0, 0.0
EPS_D = MU_D - U / 2.0
KAP_L, KAP_L_U, KAP_R, KAP_R_U, KAP_D = 1.0, 0.01, 0.01, 1.0, 2.0
GAMMA_PH = 0.1

H_BASE = EPS * (nL + nR) + EPS_D * nD + U_LR * nL * nR + U * nD * (nL + nR)
N_TOT = nL + nR + nD


def fD(E, mu, temp):
    x = np.clip((E - mu) / temp, -100, 100)
    return 1.0 / (np.exp(x) + 1.0)


def build_c_ops(TD):
    P_D0, P_D1 = I3 - nD, nD
    P0 = (I3 - nL) * (I3 - nR)
    P1 = nL * (I3 - nR) + (I3 - nL) * nR
    P2 = nL * nR
    baths = {"L": [], "R": [], "D": [], "ph": []}
    for kap, E, P in ((KAP_L, EPS, P_D0), (KAP_L_U, EPS + U, P_D1)):
        f = fD(E, MU_L, T)
        baths["L"] += [np.sqrt(kap * f) * dL.dag() * P, np.sqrt(kap * (1 - f)) * dL * P]
    for kap, E, P in ((KAP_R, EPS, P_D0), (KAP_R_U, EPS + U, P_D1)):
        f = fD(E, MU_R, T)
        baths["R"] += [np.sqrt(kap * f) * dR.dag() * P, np.sqrt(kap * (1 - f)) * dR * P]
    for n, P in enumerate((P0, P1, P2)):
        f = fD(EPS_D + n * U, MU_D, TD)
        baths["D"] += [np.sqrt(KAP_D * f) * dD.dag() * P, np.sqrt(KAP_D * (1 - f)) * dD * P]
    baths["ph"] = [np.sqrt(GAMMA_PH) * (dL.dag() * dR + dR.dag() * dL)]
    return baths


def dissipator_expect(c, op, rho):
    return qt.expect(c.dag() * op * c - 0.5 * (op * c.dag() * c + c.dag() * c * op), rho)


def thermo(g, TD):
    baths = build_c_ops(TD)
    c_all = [c for v in baths.values() for c in v]
    H = H_BASE + g * (dL.dag() * dR + dR.dag() * dL)
    rho = qt.steadystate(H, c_all)
    temps = {"L": T, "R": T, "D": TD, "ph": T}
    mus = {"L": MU_L, "R": MU_R, "D": MU_D, "ph": 0.0}
    JE, JN, Q = {}, {}, {}
    for a, cs in baths.items():
        JE[a] = float(np.real(sum(dissipator_expect(c, H_BASE, rho) for c in cs)))
        JN[a] = float(np.real(sum(dissipator_expect(c, N_TOT, rho) for c in cs)))
        Q[a] = JE[a] - mus[a] * JN[a]          # 熱浴から系へ流れ込む熱
    # 電気的出力: R から L へ化学ポテンシャルの坂を上って運ばれた粒子
    W_dot = -(MU_L * JN["L"] + MU_R * JN["R"] + MU_D * JN["D"])  # 系が外部にする仕事率
    sigma = -sum(Q[a] / temps[a] for a in baths)
    first_law_residual = W_dot - sum(Q.values())
    return dict(W_dot=W_dot, sigma=sigma, Q=Q, JN=JN, first_law_residual=first_law_residual)


def main():
    g = 0.1
    td_ratios = np.concatenate([np.logspace(-2, -0.05, 22), [0.95, 0.99, 1.0]])
    rows = []
    for r in td_ratios:
        res = thermo(g, r * T)
        Qin = res["Q"]["L"] + res["Q"]["R"] + res["Q"]["ph"]  # 高温側 (T) から入る熱
        eta = res["W_dot"] / Qin if (res["W_dot"] > 0 and Qin > 0) else np.nan
        rows.append(dict(TD_over_T=float(r), W_dot=res["W_dot"], sigma=res["sigma"],
                         Q_hot=Qin, Q_demon=res["Q"]["D"], eta=float(eta),
                         eta_carnot=float(1 - r), first_law_residual=res["first_law_residual"]))

    gs = np.logspace(-3, -1, 9)
    g_rows = []
    for gg in gs:
        iso = thermo(gg, T)
        cold = thermo(gg, 0.01 * T)
        g_rows.append(dict(g=float(gg), W_iso=iso["W_dot"], sigma_iso=iso["sigma"],
                           W_cold=cold["W_dot"], sigma_cold=cold["sigma"]))

    checks = {
        "sigma_min": min(r["sigma"] for r in rows + [{"sigma": x["sigma_iso"]} for x in g_rows]
                         + [{"sigma": x["sigma_cold"]} for x in g_rows]),
        "W_isothermal_max": max(x["W_iso"] for x in g_rows),
        "W_at_TD_equal_T": rows[-1]["W_dot"],
        "max_eta_over_carnot": float(np.nanmax([r["eta"] / r["eta_carnot"] for r in rows
                                                if not np.isnan(r["eta"])] or [0])),
        "max_abs_first_law_residual": max(abs(r["first_law_residual"]) for r in rows),
    }
    checks["PASS_sigma_nonneg"] = bool(checks["sigma_min"] >= -1e-9)
    checks["PASS_isothermal_no_work"] = bool(checks["W_isothermal_max"] <= 1e-9)
    checks["PASS_carnot"] = bool(checks["max_eta_over_carnot"] <= 1.0 + 1e-9)

    with open(os.path.join(OUT_DIR, "second_law_3dot.json"), "w") as f:
        json.dump(dict(rows=rows, g_rows=g_rows, checks=checks), f, indent=2)

    # --- 図 ---
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    x = [r["TD_over_T"] for r in rows]
    ax = axes[0]
    ax.semilogx(x, [r["W_dot"] for r in rows], "o-", color="#e67e22", ms=3, label="出力 $\\dot W$")
    ax.semilogx(x, [r["sigma"] * T for r in rows], "s--", color="#27ae60", ms=3,
                label="$T\\,\\dot\\sigma$ (エントロピー生成)")
    ax.axhline(0, color="k", lw=0.8)
    ax.axvline(1.0, color="gray", ls=":", lw=1)
    ax.set_xlabel("悪魔の熱浴温度 $T_D/T$")
    ax.set_ylabel("仕事率・散逸率 [任意単位]")
    ax.set_title("(a) 出力は $T_D \\to T$ で消える")
    ax.legend(fontsize=8)

    ax = axes[1]
    ok = [r for r in rows if not np.isnan(r["eta"])]
    ax.semilogx([r["TD_over_T"] for r in ok], [r["eta"] for r in ok], "o-", color="#8e44ad", ms=3,
                label="デーモン機関の効率 $\\eta$")
    ax.semilogx(x, [r["eta_carnot"] for r in rows], "k--", lw=1.2, label="カルノー効率 $1-T_D/T$")
    ax.set_xlabel("悪魔の熱浴温度 $T_D/T$")
    ax.set_ylabel("効率")
    ax.set_ylim(0, 1.05)
    ax.set_title("(b) 自律デーモン = 2温度間の熱機関")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_3dot_second_law.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_3dot_second_law.png"), dpi=200)

    print(json.dumps(checks, indent=2))
    for r in rows[::4] + [rows[-1]]:
        print(f"TD/T={r['TD_over_T']:.3f}  W={r['W_dot']:+.4e}  sigma={r['sigma']:+.4e}  eta={r['eta']:.4f}  carnot={r['eta_carnot']:.4f}")


if __name__ == "__main__":
    main()
