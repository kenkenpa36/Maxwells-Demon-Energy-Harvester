import numpy as np
import matplotlib.pyplot as plt
import qutip as qt

print("Initializing 10-Dot Chain Collective Bayesian Demon...")

n_dots = 10
dim = n_dots + 1

proj = lambda i: qt.basis(dim, i) * qt.basis(dim, i).dag()
jump = lambda i, j: qt.basis(dim, i) * qt.basis(dim, j).dag()

Lm_op = sum((j / n_dots) * proj(j) for j in range(1, n_dots + 1))
k_meas = 10.0
Lm = np.sqrt(k_meas) * Lm_op

def fD(E, mu, temp):
    exponent = np.clip((E - mu) / temp, -100, 100)
    return 1.0 / (np.exp(exponent) + 1.0)

T = 1000.0
muL = 0.0
muR = 100.0 
eps = 0.0

dt = 0.002
n_steps = 4000

def run_chain_trajectory(feedback=True):
    rho = proj(0)
    
    extracted_work = 0.0
    work_list = []
    
    P_matrix = np.zeros((n_steps, dim))
    
    for i in range(n_steps):
        P = [np.real(rho[j,j]) for j in range(dim)]
        P_matrix[i, :] = P
        
        kappa_ON = 5.0
        kappa_OFF = 0.01
        
        g_rates = np.zeros(n_dots)
        kappaL = kappa_OFF
        kappaR = kappa_OFF
        
        if feedback:
            if P[0] > 0.5:
                kappaL = kappa_ON
            else:
                x = np.argmax(P[1:]) + 1
                if x < n_dots:
                    g_rates[x] = kappa_ON
                else:
                    kappaR = kappa_ON
        else:
            kappaL = 1.0
            kappaR = 1.0
            g_rates = np.ones(n_dots) * 1.0
            
        H0 = qt.Qobj(np.zeros((dim, dim)))
        for j in range(1, n_dots):
            H0 += g_rates[j] * (jump(j, j+1) + jump(j+1, j))
            
        G_L_in = kappaL * fD(eps, muL, T)
        G_L_out = kappaL * (1.0 - fD(eps, muL, T))
        G_R_in = kappaR * fD(eps, muR, T)
        G_R_out = kappaR * (1.0 - fD(eps, muR, T))
        
        c_ops = [
            np.sqrt(G_L_in) * jump(1, 0),
            np.sqrt(G_L_out) * jump(0, 1),
            np.sqrt(G_R_in) * jump(n_dots, 0),
            np.sqrt(G_R_out) * jump(0, n_dots)
        ]
        
        I_R_out = G_R_out * P[n_dots] - G_R_in * P[0] 
        W_dot = (muR - muL) * I_R_out
        extracted_work += W_dot * dt
        work_list.append(extracted_work)
        
        L_rho = -1j * (H0 * rho - rho * H0)
        for c in c_ops:
            L_rho += c * rho * c.dag() - 0.5 * (c.dag() * c * rho + rho * c.dag() * c)
            
        L_rho += Lm * rho * Lm.dag() - 0.5 * (Lm.dag() * Lm * rho + rho * Lm.dag() * Lm)
        
        dW = np.random.normal(0, np.sqrt(dt))
        innov = Lm * rho + rho * Lm.dag() - qt.expect(Lm + Lm.dag(), rho) * rho
        
        rho_new = rho + L_rho * dt + innov * dW
        rho_new = rho_new / rho_new.tr()
        rho = rho_new
        
    return P_matrix, work_list

print("Running Trajectory WITHOUT Feedback...")
P_mat_no, w_no = run_chain_trajectory(feedback=False)

print("Running Trajectory WITH Bayesian Feedback...")
P_mat_fb, w_fb = run_chain_trajectory(feedback=True)

print(f"Total Work Extracted (No Feedback) : {w_no[-1]:.2f}")
print(f"Total Work Extracted (Feedback)    : {w_fb[-1]:.2f}")

plt.figure(figsize=(12, 8))

ax1 = plt.subplot(2, 2, 1)
im1 = ax1.imshow(P_mat_no[:, 1:].T, aspect='auto', origin='lower', cmap='inferno', interpolation='nearest',
                 extent=[0, n_steps*dt, 1, n_dots])
ax1.set_ylabel('Dot Position')
ax1.set_title('Electron Position Prob (No Feedback)')
plt.colorbar(im1, ax=ax1)

ax2 = plt.subplot(2, 2, 2)
im2 = ax2.imshow(P_mat_fb[:, 1:].T, aspect='auto', origin='lower', cmap='inferno', interpolation='nearest',
                 extent=[0, n_steps*dt, 1, n_dots])
ax2.set_ylabel('Dot Position')
ax2.set_title('Bayesian Conveyor Belt (Feedback ON)')
plt.colorbar(im2, ax=ax2)

ax3 = plt.subplot(2, 1, 2)
t_axis = np.arange(n_steps) * dt
ax3.plot(t_axis, w_fb, color='blue', linewidth=2, label='With Bayesian Feedback')
ax3.plot(t_axis, w_no, color='orange', linewidth=2, label='No Feedback')
ax3.axhline(0, color='k', linestyle='--')
ax3.set_xlabel('Time')
ax3.set_ylabel('Extracted Work')
ax3.set_title('Work Extracted from 10-Dot Chain')
ax3.legend()

plt.tight_layout()
plt.savefig('chain_dynamics.png', dpi=300)
print("Saved chain_dynamics.png")
