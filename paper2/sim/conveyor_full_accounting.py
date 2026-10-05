"""
conveyor_full_accounting.py
===========================
10 ドットチェーン (Information Conveyor Belt) の完全な熱力学収支。

10 ドットの連続位置測定 (測定強度 k_meas) とベイズ制御のフィードバック下で、
逆バイアス Δμ = 2.0 kT に対抗して電子を汲み上げる。

正当な熱力学収支の評価:
 (1) 抽出仕事 W_ext: 逆バイアスを超えて右熱浴に排出された粒子による仕事
 (2) 獲得情報量 I_acc: 事後確率分布の分散から算出した相互情報量累積 (nats)
 (3) メモリ消去コスト W_erase(T_M) = k_B T_M * I_acc
     - 等温設定 (T_M = T = 300 K): W_net = W_ext - W_erase(T) < 0 (第二法則と整合)
     - 極低温悪魔設定 (T_M = 4.2 K, T = 300 K): W_erase が 4.2/300 ≈ 1.4% に激減し W_net > 0
 (4) 損益分岐温度: T_M_break = T * (W_ext / (k_B T * I_acc))
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

N_DOTS = 10
DIM = N_DOTS + 1
KT_ROOM = 1.0  # 室温 (300 K) を 1.0 とする
T_ROOM_K = 300.0
T_HE_K = 4.2

proj = lambda i: qt.basis(DIM, i) * qt.basis(DIM, i).dag()
jump = lambda i, j: qt.basis(DIM, i) * qt.basis(DIM, j).dag()

LM_OP = sum((j / N_DOTS) * proj(j) for j in range(1, N_DOTS + 1))


def fD(E, mu, kT):
    exp_val = np.clip((E - mu) / kT, -100, 100)
    return 1.0 / (np.exp(exp_val) + 1.0)


def run_conveyor_sim(k_meas=100.0, muR=2.0, dt=0.002, n_steps=2000, seed=42):
    np.random.seed(seed)
    Lm = np.sqrt(k_meas) * LM_OP
    rho = proj(0)

    w_ext = 0.0
    i_acc = 0.0

    w_ext_list = []
    i_acc_list = []

    kappa_ON = 20.0
    kappa_OFF = 0.01
    muL = 0.0
    eps = 0.0

    for _step in range(n_steps):
        P = np.clip(np.real(rho.diag()), 0.0, 1.0)
        p_sum = float(np.sum(P))
        if p_sum > 1e-12:
            P = P / p_sum

        exp_Lm = sum(np.sqrt(k_meas) * (j / N_DOTS) * P[j] for j in range(1, N_DOTS + 1))
        exp_Lm2 = sum(k_meas * ((j / N_DOTS) ** 2) * P[j] for j in range(1, N_DOTS + 1))
        var_Lm = max(0.0, exp_Lm2 - exp_Lm**2)

        info_rate = 2.0 * var_Lm
        i_acc += info_rate * dt

        g_rates = np.zeros(N_DOTS + 1)
        kappaL = kappa_OFF
        kappaR = kappa_OFF

        if P[0] > 0.5:
            kappaL = kappa_ON
        else:
            x = int(np.argmax(P[1:]) + 1)
            if x < N_DOTS:
                g_rates[x] = kappa_ON
            else:
                kappaR = kappa_ON

        H0 = qt.Qobj(np.zeros((DIM, DIM)))
        for j in range(1, N_DOTS):
            H0 += g_rates[j] * (jump(j, j + 1) + jump(j + 1, j))

        G_L_in = kappaL * fD(eps, muL, KT_ROOM)
        G_L_out = kappaL * (1.0 - fD(eps, muL, KT_ROOM))
        G_R_in = kappaR * fD(eps, muR, KT_ROOM)
        G_R_out = kappaR * (1.0 - fD(eps, muR, KT_ROOM))

        c_ops = [
            np.sqrt(G_L_in) * jump(1, 0),
            np.sqrt(G_L_out) * jump(0, 1),
            np.sqrt(G_R_in) * jump(N_DOTS, 0),
            np.sqrt(G_R_out) * jump(0, N_DOTS),
        ]

        I_R_out = G_R_out * P[N_DOTS] - G_R_in * P[0]
        W_dot = (muR - muL) * I_R_out
        w_ext += W_dot * dt

        w_ext_list.append(w_ext)
        i_acc_list.append(i_acc)

        L_rho = -1j * (H0 * rho - rho * H0)
        for c in c_ops:
            L_rho += c * rho * c.dag() - 0.5 * (c.dag() * c * rho + rho * c.dag() * c)

        L_rho += Lm * rho * Lm.dag() - 0.5 * (Lm.dag() * Lm * rho + rho * Lm.dag() * Lm)
        dW = np.random.normal(0, np.sqrt(dt))
        innov = Lm * rho + rho * Lm.dag() - qt.expect(Lm + Lm.dag(), rho) * rho

        rho_new = rho + L_rho * dt + innov * dW
        rho_new = (rho_new + rho_new.dag()) * 0.5
        tr_val = float(np.real(rho_new.tr()))
        if tr_val > 1e-12:
            rho = rho_new / tr_val
        else:
            rho = rho_new

    return np.array(w_ext_list), np.array(i_acc_list)


def main():
    w_ext, i_acc = run_conveyor_sim()

    t_m_k = np.linspace(0.1, 350.0, 200)
    w_erase_vs_T = (t_m_k / T_ROOM_K) * i_acc[-1]
    w_net_vs_T = w_ext[-1] - w_erase_vs_T

    t_break_k = T_ROOM_K * (w_ext[-1] / i_acc[-1])

    w_erase_room = i_acc[-1]
    w_erase_he = (T_HE_K / T_ROOM_K) * i_acc[-1]
    w_net_room = w_ext[-1] - w_erase_room
    w_net_he = w_ext[-1] - w_erase_he

    res = {
        "W_ext_final": float(w_ext[-1]),
        "I_acc_nats": float(i_acc[-1]),
        "W_erase_room_300K": float(w_erase_room),
        "W_net_room_300K": float(w_net_room),
        "W_erase_cryo_4K": float(w_erase_he),
        "W_net_cryo_4K": float(w_net_he),
        "T_M_break_even_K": float(t_break_k),
    }

    with open(os.path.join(OUT_DIR, "conveyor_thermo.json"), "w") as f:
        json.dump(res, f, indent=2)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    t_axis = np.arange(len(w_ext)) * 0.002
    ax = axes[0]
    ax.plot(t_axis, w_ext, "k--", lw=2, label="抽出仕事 $W_{\\mathrm{ext}}$")
    ax.plot(t_axis, w_ext - i_acc, color="#c0392b", lw=2, label="等温悪魔 ($T_M=300\\text{ K}$) 正味仕事")
    ax.plot(t_axis, w_ext - (T_HE_K / T_ROOM_K) * i_acc, color="#27ae60", lw=2, label="極低温悪魔 ($T_M=4.2\\text{ K}$) 正味仕事")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xlabel("時間 [$1/\\gamma_0$ 単位系]")
    ax.set_ylabel("エネルギー [$k_B T_{\\mathrm{room}}$]")
    ax.set_title("(a) 時間発展と消去コスト")
    ax.legend(fontsize=8, loc="upper left")

    ax = axes[1]
    ax.plot(t_m_k, w_net_vs_T, color="#2980b9", lw=2)
    ax.axhline(0, color="k", lw=0.8)
    ax.axvline(t_break_k, color="#e67e22", ls="--", label=f"損益分岐温度 $T_{{M,\\mathrm{{break}}}} = {t_break_k:.1f}\\text{{ K}}$")
    ax.axvline(T_HE_K, color="#27ae60", ls=":", label="液体ヘリウム (4.2 K)")
    ax.axvline(T_ROOM_K, color="#c0392b", ls=":", label="室温 (300 K)")
    ax.set_xlabel("悪魔 (メモリ消去) の動作温度 $T_M$ [K]")
    ax.set_ylabel("正味仕事 $W_{\\mathrm{net}}$ [$k_B T_{\\mathrm{room}}$]")
    ax.set_title("(b) メモリ温度に対する正味仕事と損益分岐点")
    ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "fig_conveyor_thermo.pdf"))
    fig.savefig(os.path.join(FIG_DIR, "fig_conveyor_thermo.png"), dpi=200)

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
