"""
conveyor_full_accounting.py
===========================
10 ドットチェーン「情報ベルトコンベア」の完全な熱力学収支 (改訂版)。

模型 (旧 simulate_macroscopic_quantum_engine.py と同一パラメータ)
  - 状態: |0> = 空, |j> = 電子がドット j (j=1..10) にいる。次元 11
  - 連続位置測定: L = sqrt(k_meas) * X,  X = sum_j (j/10)|j><j|,  k_meas = 100
  - ベイズ (事後状態) に基づくゲート制御: 空なら入口を開け、電子位置 argmax の前方障壁を開ける
  - 逆バイアス Δμ = μR - μL = 2 kT に逆らって電子を右浴へ送り出す -> 抽出仕事 W_ext
  - 室温 T を kT = 1 とする

旧版からの変更点
  1. 確率マスター方程式 (SME) の積分を、正値性を保存する Rouchon-Ralph 型の
     Kraus 写像に置き換えた (旧版の陽的オイラー法 + クリップは状態が破綻しうる)
  2. 単一の乱数系列ではなく N_SEEDS 本の測定記録について平均と標準誤差を求める
  3. 刻み幅 dt を半分にした計算と比較して収束を確認する
  4. 獲得情報量 I_acc は Duncan (1970) の公式で計算する:
        測定記録 dy = h dt + dW, h = <L + L^†> = 2 sqrt(k) X に対し
        dI/dt = (1/2) E[(h - ĥ)^2] = 2 k Var_post(X)   [nats/時間]
     (測定で位相緩和が速く、占有数を古典的な隠れ状態とみなす近似)
  5. 収支を3通りで評価する
     (a) 等温 (メモリも室温 T):            W_net = W_ext - kT * I
     (b) 低温メモリ T_M (自然の低温浴がある場合): W_net = W_ext - k T_M * I
     (c) 低温メモリを室温から冷凍機で維持する場合:
         メモリに捨てた熱 Q_M = k T_M I を T まで汲み上げるのに W_fr >= Q_M (T/T_M - 1)
         -> W_net = W_ext - k T_M I - W_fr <= W_ext - kT I  (= (a) と同じ)
"""
import os
import json
import numpy as np
from multiprocessing import Pool
import plotstyle  # noqa: F401
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(HERE, "..", "figs")
OUT_DIR = os.path.join(HERE, "..", "results")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

N_DOTS = 10
DIM = N_DOTS + 1
KT = 1.0
T_ROOM_K = 300.0
K_MEAS = 100.0
MU_L, MU_R, EPS = 0.0, 2.0, 0.0
KAPPA_ON, KAPPA_OFF = 20.0, 0.01
T_FINAL = 6.0           # 旧版と同じ総時間 (dt=0.002 x 3000 step)
N_SEEDS = 48

X_DIAG = np.array([0.0] + [j / N_DOTS for j in range(1, DIM)])
L_OP = np.sqrt(K_MEAS) * np.diag(X_DIAG)
I_DIM = np.eye(DIM)


def ket_bra(i, j):
    m = np.zeros((DIM, DIM))
    m[i, j] = 1.0
    return m


def fD(E, mu):
    return 1.0 / (np.exp(np.clip((E - mu) / KT, -100, 100)) + 1.0)


F_L, F_R = fD(EPS, MU_L), fD(EPS, MU_R)
HOP = [None] + [ket_bra(j, j + 1) + ket_bra(j + 1, j) for j in range(1, N_DOTS)]
J_L_IN, J_L_OUT = ket_bra(1, 0), ket_bra(0, 1)
J_R_IN, J_R_OUT = ket_bra(N_DOTS, 0), ket_bra(0, N_DOTS)


def run(args):
    seed, dt = args
    rng = np.random.default_rng(seed)
    n_steps = int(round(T_FINAL / dt))
    rho = np.zeros((DIM, DIM), dtype=complex)
    rho[0, 0] = 1.0
    w_ext = 0.0
    i_acc = 0.0
    w_hist = np.empty(n_steps)
    i_hist = np.empty(n_steps)
    for n in range(n_steps):
        P = np.real(np.diag(rho)).clip(0.0)
        P /= P.sum()
        # 情報獲得率 (Duncan): 2 k Var_post(X)
        mx = float(X_DIAG @ P)
        var_x = float((X_DIAG ** 2) @ P - mx ** 2)
        i_acc += 2.0 * K_MEAS * max(var_x, 0.0) * dt

        # ベイズ制御 (旧版と同じ規則)
        H = np.zeros((DIM, DIM))
        kL = kR = KAPPA_OFF
        if P[0] > 0.5:
            kL = KAPPA_ON
        else:
            x = int(np.argmax(P[1:]) + 1)
            if x < N_DOTS:
                H = KAPPA_ON * HOP[x]
            else:
                kR = KAPPA_ON
        c_ops = [np.sqrt(kL * F_L) * J_L_IN, np.sqrt(kL * (1 - F_L)) * J_L_OUT,
                 np.sqrt(kR * F_R) * J_R_IN, np.sqrt(kR * (1 - F_R)) * J_R_OUT]

        # 抽出仕事: 右浴へ送り出された粒子 x Δμ
        I_R_out = kR * (1 - F_R) * P[N_DOTS] - kR * F_R * P[0]
        w_ext += (MU_R - MU_L) * I_R_out * dt
        w_hist[n] = w_ext
        i_hist[n] = i_acc

        # 正値性を保存する Kraus 写像 (Rouchon & Ralph 型)
        dW = rng.normal(0.0, np.sqrt(dt))
        dy = 2.0 * np.real(np.trace(L_OP @ rho)) * dt + dW
        Kc = sum(c.T @ c for c in c_ops)
        M = (I_DIM - (1j * H + 0.5 * Kc + 0.5 * L_OP @ L_OP) * dt
             + L_OP * dy + 0.5 * (L_OP @ L_OP) * (dy * dy - dt))
        rho_new = M @ rho @ M.conj().T
        for c in c_ops:
            rho_new += c @ rho @ c.T * dt
        rho_new = 0.5 * (rho_new + rho_new.conj().T)
        rho = rho_new / np.real(np.trace(rho_new))
    min_eig = float(np.linalg.eigvalsh(rho).min())
    return w_hist, i_hist, min_eig


def stats(x):
    x = np.asarray(x)
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x)))


def main():
    dt0 = 0.002
    with Pool(min(8, os.cpu_count() or 1)) as pool:
        res0 = pool.map(run, [(s, dt0) for s in range(N_SEEDS)])
        res1 = pool.map(run, [(s, dt0 / 2) for s in range(N_SEEDS)])

    W0 = np.array([r[0][-1] for r in res0]); I0 = np.array([r[1][-1] for r in res0])
    W1 = np.array([r[0][-1] for r in res1]); I1 = np.array([r[1][-1] for r in res1])
    min_eig = min(min(r[2] for r in res0), min(r[2] for r in res1))

    w_m, w_se = stats(W0)
    i_m, i_se = stats(I0)
    net_iso_m, net_iso_se = stats(W0 - KT * I0)
    tm_break = T_ROOM_K * w_m / i_m
    out = {
        "n_seeds": N_SEEDS, "dt": dt0, "T_final": T_FINAL,
        "W_ext_mean": w_m, "W_ext_se": w_se,
        "I_acc_mean_nats": i_m, "I_acc_se": i_se,
        "W_net_isothermal_mean": net_iso_m, "W_net_isothermal_se": net_iso_se,
        "fraction_seeds_W_ext_gt_kT_I": float(np.mean(W0 > KT * I0)),
        "W_net_cold_4p2K_mean": float(np.mean(W0 - (4.2 / T_ROOM_K) * I0)),
        "W_net_cold_77K_mean": float(np.mean(W0 - (77.0 / T_ROOM_K) * I0)),
        "W_net_cold_with_refrigerator_mean": net_iso_m,
        "T_M_break_even_K": tm_break,
        "convergence_dt_half": {"W_ext_mean": stats(W1)[0], "W_ext_se": stats(W1)[1],
                                "I_acc_mean": stats(I1)[0], "I_acc_se": stats(I1)[1]},
        "min_eigenvalue_final_rho": min_eig,
        "legacy_single_run_reported": {"W_ext": 5.05, "I_acc": 26.96,
                                       "note": "旧版: 陽的オイラー法・単一乱数系列"},
    }
    with open(os.path.join(OUT_DIR, "conveyor_thermo.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # --- Plot ---
    t = np.arange(len(res0[0][0])) * dt0
    Wm = np.mean([r[0] for r in res0], axis=0)
    Im = np.mean([r[1] for r in res0], axis=0)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    ax = axes[0]
    ax.plot(t, Wm, "k--", lw=2, label=r"Extracted Work $W_{\rm ext}$")
    ax.plot(t, Wm - KT * Im, color="#c0392b", lw=2,
            label=r"(a) Isothermal / (c) Active Cryocooling")
    ax.plot(t, Wm - (4.2 / T_ROOM_K) * Im, color="#27ae60", lw=2,
            label=r"(b) Passive Cold Reservoir (4.2 K)")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xlabel("Time [dimensionless]")
    ax.set_ylabel(r"Energy [$k_BT$]")
    ax.set_title(f"(a) Mean of {N_SEEDS} Stochastic Trajectories")
    ax.legend(fontsize=7.5, loc="lower left")

    ax = axes[1]
    tm = np.linspace(0.5, 320, 300)
    net_b = w_m - (tm / T_ROOM_K) * i_m
    ax.plot(tm, net_b, color="#27ae60", lw=2, label="(b) Passive Cold Reservoir")
    ax.fill_between(tm, net_b - np.sqrt(w_se**2 + (tm / T_ROOM_K * i_se) ** 2),
                    net_b + np.sqrt(w_se**2 + (tm / T_ROOM_K * i_se) ** 2),
                    color="#27ae60", alpha=0.2)
    ax.axhline(net_iso_m, color="#c0392b", lw=2, label=r"(c) Active Carnot Refrigeration (Any $T_M$)")
    ax.axhline(0, color="k", lw=0.8)
    ax.axvline(tm_break, color="#e67e22", ls="--", label=f"Break-even $T_M$ = {tm_break:.0f} K")
    ax.set_xlabel(r"Demon Memory Temperature $T_M$ [K] (Working Substance: 300 K)")
    ax.set_ylabel(r"Net Cyclic Work $W_{\rm net}$ [$k_BT$]")
    ax.set_title("(b) Refrigerator Tax: Active Cooling Is Not Free")
    ax.legend(fontsize=7.5, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_conveyor_thermo.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_conveyor_thermo.png"), dpi=200)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
