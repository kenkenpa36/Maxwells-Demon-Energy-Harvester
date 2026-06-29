import numpy as np
import matplotlib.pyplot as plt
import qutip as qt
import time

print("Initializing Bayesian SME Simulation...")

# 1. System Setup (2 dots L and R, no physical demon dot)
sm = qt.sigmam()
sz = qt.sigmaz()
iden = qt.qeye(2)

dL = qt.tensor(sm, iden)
dR = qt.tensor(sz, sm)

nL = dL.dag() * dL
nR = dR.dag() * dR
N = nL + nR

def fD(E, mu, temp):
    exponent = np.clip((E - mu) / temp, -100, 100)
    return 1.0 / (np.exp(exponent) + 1.0)

# Parameters
T = 1000.0
muL = 50.0   # High potential
muR = -50.0  # Low potential
eps = 0.0
U_LR = 5000.0
g = 0.5

# Homodyne Measurement Strength (k)
k_meas = 5.0
# Meas operator
Lm = np.sqrt(k_meas) * N

H0 = eps * (nL + nR) + U_LR * nL * nR + g * (dL.dag() * dR + dR.dag() * dL)

dt = 0.005
n_steps = 3000

def run_trajectory(feedback=True):
    rho = qt.tensor(qt.fock_dm(2,0), qt.fock_dm(2,0))
    
    extracted_work = 0.0
    work_list = []
    
    # Store trajectory for plotting
    P_N1_list = []
    signal_list = []
    
    for i in range(n_steps):
        # 1. Bayesian Estimation (Current State)
        P_N = qt.expect(N, rho)
        P_N1_list.append(P_N)
        
        # 2. Feedback Protocol
        kappa_ON = 5.0
        kappa_OFF = 0.01
        
        if feedback:
            if P_N < 0.5:
                # Dot is empty. Open R, close L to suck electron from low potential
                kappaL = kappa_OFF
                kappaR = kappa_ON
            else:
                # Dot is full. Open L, close R to push electron to high potential
                kappaL = kappa_ON
                kappaR = kappa_OFF
        else:
            kappaL = 1.0
            kappaR = 1.0
            
        G_L_in = kappaL * fD(eps, muL, T)
        G_L_out = kappaL * (1.0 - fD(eps, muL, T))
        G_R_in = kappaR * fD(eps, muR, T)
        G_R_out = kappaR * (1.0 - fD(eps, muR, T))
        
        c_ops = [
            np.sqrt(G_L_in) * dL.dag(),
            np.sqrt(G_L_out) * dL,
            np.sqrt(G_R_in) * dR.dag(),
            np.sqrt(G_R_out) * dR
        ]
        
        # Current leaving the system to Bath L
        I_L_out = G_L_out * qt.expect(nL, rho) - G_L_in * (1 - qt.expect(nL, rho))
        
        # Work extracted = Energy gained by moving to high potential
        # (Electron enters L bath at muL=50)
        W_dot = (muL - muR) * I_L_out
        extracted_work += W_dot * dt
        work_list.append(extracted_work)
        
        # 3. SME Update (Euler-Maruyama)
        L_rho = -1j * (H0 * rho - rho * H0)
        for c in c_ops:
            L_rho += c * rho * c.dag() - 0.5 * (c.dag() * c * rho + rho * c.dag() * c)
            
        # Measurement Decoherence
        L_rho += Lm * rho * Lm.dag() - 0.5 * (Lm.dag() * Lm * rho + rho * Lm.dag() * Lm)
        
        dW = np.random.normal(0, np.sqrt(dt))
        dy = qt.expect(Lm + Lm.dag(), rho) * dt + dW
        signal_list.append(dy / dt)
        
        # Innovations
        innov = Lm * rho + rho * Lm.dag() - qt.expect(Lm + Lm.dag(), rho) * rho
        
        rho_new = rho + L_rho * dt + innov * dW
        rho_new = rho_new / rho_new.tr()  # Normalize
        rho = rho_new
        
    return extracted_work, P_N1_list, signal_list, work_list

print("Running Monte Carlo Trajectories...")

# Run a few trajectories and average to show consistent work extraction
n_traj = 5
avg_work_fb = np.zeros(n_steps)
avg_work_no = np.zeros(n_steps)

for n in range(n_traj):
    print(f"Trajectory {n+1}/{n_traj}")
    _, _, _, w_fb = run_trajectory(feedback=True)
    _, _, _, w_no = run_trajectory(feedback=False)
    avg_work_fb += np.array(w_fb) / n_traj
    avg_work_no += np.array(w_no) / n_traj

# For visual, just take the last trajectory
_, P_fb, sig_fb, _ = run_trajectory(feedback=True)
_, P_no, sig_no, _ = run_trajectory(feedback=False)

print(f"Total Avg Work (No Feedback)  : {avg_work_no[-1]:.4f}")
print(f"Total Avg Work (With Feedback): {avg_work_fb[-1]:.4f}")

# Plotting
t_axis = np.arange(n_steps) * dt

plt.figure(figsize=(10, 10))

plt.subplot(3, 1, 1)
plt.plot(t_axis, sig_fb, color='lightgray', alpha=0.7, label='Noisy Measurement Signal $dy/dt$')
plt.plot(t_axis, P_fb, color='blue', linewidth=2, label='Bayesian Posterior $\langle N \\rangle$')
plt.axhline(0.5, color='red', linestyle='--', label='Decision Threshold')
plt.ylabel('Signal / Prob')
plt.title('Circuit QED Bayesian Demon: Quantum Trajectory & Feedback')
plt.legend(loc='upper right')

plt.subplot(3, 1, 2)
plt.plot(t_axis, P_no, color='orange', linewidth=2, label='No Feedback $\langle N \\rangle$')
plt.ylabel('Probability')
plt.title('System State (Without Feedback)')
plt.legend(loc='upper right')

plt.subplot(3, 1, 3)
plt.plot(t_axis, avg_work_fb, color='blue', linewidth=2, label='Bayesian Feedback (Work Extracted)')
plt.plot(t_axis, avg_work_no, color='orange', linewidth=2, label='No Feedback (Energy Dissipated)')
plt.axhline(0, color='k', linestyle='-')
plt.xlabel('Time')
plt.ylabel('Accumulated Work')
plt.title('Thermodynamic Performance: Overcoming Noise Limits')
plt.legend(loc='upper left')

plt.tight_layout()
plt.savefig('bayesian_demon_results.png', dpi=300)
print("Saved bayesian_demon_results.png")
