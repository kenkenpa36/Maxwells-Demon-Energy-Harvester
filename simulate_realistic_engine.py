import numpy as np
import matplotlib.pyplot as plt
import qutip as qt
import time

print("Initializing realistic phase diagram simulation...")

# 1. Operators
sm = qt.sigmam()
sz = qt.sigmaz()
iden = qt.qeye(2)
iden3 = qt.tensor(iden, iden, iden)

dL = qt.tensor(sm, iden, iden)
dR = qt.tensor(sz, sm, iden)
dD = qt.tensor(sz, sz, sm)

nL = dL.dag() * dL
nR = dR.dag() * dR
nD = dD.dag() * dD

P_D0 = iden3 - nD
P_D1 = nD
P_LR0 = (iden3 - nL) * (iden3 - nR)
P_LR1 = nL * (iden3 - nR) + (iden3 - nL) * nR
P_LR2 = nL * nR

def fD(E, mu, temp):
    exponent = np.clip((E - mu) / temp, -100, 100)
    return 1.0 / (np.exp(exponent) + 1.0)

def simulate_point(T_D, U):
    # Fixed Parameters
    eps = 0.0
    U_LR = 5000.0
    T = 1000.0
    muL = 50.0
    muR = -50.0
    muD = 0.0
    epsD = muD - U/2.0
    
    kappaL = 1.0
    kappaL_U = 0.01
    kappaR = 0.01
    kappaR_U = 1.0
    kappaD = 2.0
    gamma_ph = 0.1
    g = 0.5
    
    # Rates
    G_L_in_0 = kappaL * fD(eps, muL, T)
    G_L_out_0 = kappaL * (1.0 - fD(eps, muL, T))
    G_L_in_1 = kappaL_U * fD(eps + U, muL, T)
    G_L_out_1 = kappaL_U * (1.0 - fD(eps + U, muL, T))

    G_R_in_0 = kappaR * fD(eps, muR, T)
    G_R_out_0 = kappaR * (1.0 - fD(eps, muR, T))
    G_R_in_1 = kappaR_U * fD(eps + U, muR, T)
    G_R_out_1 = kappaR_U * (1.0 - fD(eps + U, muR, T))

    G_D_in_0 = kappaD * fD(epsD, muD, T_D)
    G_D_out_0 = kappaD * (1.0 - fD(epsD, muD, T_D))
    G_D_in_1 = kappaD * fD(epsD + U, muD, T_D)
    G_D_out_1 = kappaD * (1.0 - fD(epsD + U, muD, T_D))
    G_D_in_2 = kappaD * fD(epsD + 2*U, muD, T_D)
    G_D_out_2 = kappaD * (1.0 - fD(epsD + 2*U, muD, T_D))
    
    c_ops_L = [
        np.sqrt(G_L_in_0) * dL.dag() * P_D0,
        np.sqrt(G_L_out_0) * dL * P_D0,
        np.sqrt(G_L_in_1) * dL.dag() * P_D1,
        np.sqrt(G_L_out_1) * dL * P_D1
    ]
    
    c_ops_R = [
        np.sqrt(G_R_in_0) * dR.dag() * P_D0,
        np.sqrt(G_R_out_0) * dR * P_D0,
        np.sqrt(G_R_in_1) * dR.dag() * P_D1,
        np.sqrt(G_R_out_1) * dR * P_D1
    ]
    
    c_ops_D = [
        np.sqrt(G_D_in_0) * dD.dag() * P_LR0,
        np.sqrt(G_D_out_0) * dD * P_LR0,
        np.sqrt(G_D_in_1) * dD.dag() * P_LR1,
        np.sqrt(G_D_out_1) * dD * P_LR1,
        np.sqrt(G_D_in_2) * dD.dag() * P_LR2,
        np.sqrt(G_D_out_2) * dD * P_LR2
    ]
    
    c_ops = c_ops_L + c_ops_R + c_ops_D
    c_ops.append(np.sqrt(gamma_ph) * (dL.dag() * dR + dR.dag() * dL))
    
    H = eps * (nL + nR) + epsD * nD + U_LR * nL * nR + U * nD * (nL + nR) + g * (dL.dag() * dR + dR.dag() * dL)
    
    # Solve
    rho_ss = qt.steadystate(H, c_ops)
    
    # Calc current I_L (bath L into system)
    rate = 0.0
    for c in c_ops_L:
        op = c.dag() * nL * c - 0.5 * (nL * c.dag() * c + c.dag() * c * nL)
        rate += qt.expect(op, rho_ss)
        
    I_R_to_L = -rate
    W_dot = (muL - muR) * I_R_to_L
    return W_dot

# 2. Grid Setup
T = 1000.0
n_T = 30
n_U = 30
# Log scale for TD to capture orders of magnitude difference
TD_array = np.logspace(0, 3, n_T)  # from 1 to 1000
# Linear scale for U/T
U_array = np.linspace(50, 4000, n_U)

W_grid = np.zeros((n_U, n_T))

start_time = time.time()
print(f"Starting 2D parameter sweep of {n_T * n_U} points...")

for i, U_val in enumerate(U_array):
    if i % 5 == 0:
        print(f"Progress: {i}/{n_U} U_val steps...")
    for j, TD_val in enumerate(TD_array):
        W_grid[i, j] = simulate_point(TD_val, U_val)

print(f"Simulation completed in {time.time() - start_time:.2f} seconds.")

# 3. Plotting
TD_ratio = TD_array / T
U_ratio = U_array / T

X, Y = np.meshgrid(TD_ratio, U_ratio)

plt.figure(figsize=(8, 6))

# Plot contour of extracted power
cp = plt.contourf(X, Y, W_grid, levels=50, cmap='RdYlBu_r')
cbar = plt.colorbar(cp)
cbar.set_label(r'Extracted Power $\dot{W}$', fontsize=12)

# Add contour line for W = 0 (Engine operation boundary)
plt.contour(X, Y, W_grid, levels=[0], colors='black', linewidths=2, linestyles='--')

plt.xscale('log')
plt.xlabel('Demon Temperature Ratio $T_D / T$', fontsize=12)
plt.ylabel('Coulomb Interaction $U / T$', fontsize=12)
plt.title('Phase Diagram: Environment Engine Operation Limit', fontsize=14)

# Indicate region where engine works
plt.text(0.005, 3.5, 'Engine Works\n($\dot{W} > 0$)', fontsize=12, color='black', 
         bbox=dict(facecolor='white', alpha=0.8, edgecolor='black'))

plt.tight_layout()
plt.savefig('phase_diagram.png', dpi=300)
print("Saved phase_diagram.png")
