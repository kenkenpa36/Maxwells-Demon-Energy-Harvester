import numpy as np
import matplotlib.pyplot as plt
import qutip as qt

print("Initializing Noise Cycle Simulation...")

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

# Base Parameters
eps = 0.0
U = 200.0
U_LR = 5000.0
T = 1000.0
TD = 10.0
muL = 50.0
muR = -50.0
muD = 0.0
epsD = muD - U/2.0
gamma_ph = 0.1
g = 0.5
kappaD = 2.0

# Base Rates for Demon
G_D_in_0 = kappaD * fD(epsD, muD, TD)
G_D_out_0 = kappaD * (1.0 - fD(epsD, muD, TD))
G_D_in_1 = kappaD * fD(epsD + U, muD, TD)
G_D_out_1 = kappaD * (1.0 - fD(epsD + U, muD, TD))
G_D_in_2 = kappaD * fD(epsD + 2*U, muD, TD)
G_D_out_2 = kappaD * (1.0 - fD(epsD + 2*U, muD, TD))

c_ops_D_base = [
    np.sqrt(G_D_in_0) * dD.dag() * P_LR0,
    np.sqrt(G_D_out_0) * dD * P_LR0,
    np.sqrt(G_D_in_1) * dD.dag() * P_LR1,
    np.sqrt(G_D_out_1) * dD * P_LR1,
    np.sqrt(G_D_in_2) * dD.dag() * P_LR2,
    np.sqrt(G_D_out_2) * dD * P_LR2
]

H = eps * (nL + nR) + epsD * nD + U_LR * nL * nR + U * nD * (nL + nR) + g * (dL.dag() * dR + dR.dag() * dL)
c_ops_ph = [np.sqrt(gamma_ph) * (dL.dag() * dR + dR.dag() * dL)]

def simulate_noise(alpha=0.0, gamma_phi=0.0, gamma_rand=0.0):
    # Asymmetry Noise
    kappaL = 1.0
    kappaL_U = 0.01 + alpha * (1.0 - 0.01)
    kappaR = 0.01 + alpha * (1.0 - 0.01)
    kappaR_U = 1.0
    
    G_L_in_0 = kappaL * fD(eps, muL, T)
    G_L_out_0 = kappaL * (1.0 - fD(eps, muL, T))
    G_L_in_1 = kappaL_U * fD(eps + U, muL, T)
    G_L_out_1 = kappaL_U * (1.0 - fD(eps + U, muL, T))

    G_R_in_0 = kappaR * fD(eps, muR, T)
    G_R_out_0 = kappaR * (1.0 - fD(eps, muR, T))
    G_R_in_1 = kappaR_U * fD(eps + U, muR, T)
    G_R_out_1 = kappaR_U * (1.0 - fD(eps + U, muR, T))
    
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
    
    c_ops = c_ops_L + c_ops_R + c_ops_D_base + c_ops_ph
    
    # Dephasing Noise
    if gamma_phi > 0:
        c_ops.append(np.sqrt(gamma_phi) * nL)
        c_ops.append(np.sqrt(gamma_phi) * nR)
        
    # Demon Random Flip Noise (Depolarization-like channel)
    # sigma_x on demon: dD.dag() + dD
    if gamma_rand > 0:
        c_ops.append(np.sqrt(gamma_rand) * (dD.dag() + dD))
        
    rho_ss = qt.steadystate(H, c_ops)
    
    # Calc current I_L (bath L into system)
    rate = 0.0
    for c in c_ops_L:
        op = c.dag() * nL * c - 0.5 * (nL * c.dag() * c + c.dag() * c * nL)
        rate += qt.expect(op, rho_ss)
        
    I_R_to_L = -rate
    W_dot = (muL - muR) * I_R_to_L
    return W_dot

print("Cycle 1: Asymmetry Degradation")
alphas = np.linspace(0, 1, 40)
W_alphas = []
for a in alphas:
    W_alphas.append(simulate_noise(alpha=a))

plt.figure(figsize=(6, 4))
plt.plot(alphas, W_alphas, 'o-', color='blue')
plt.axhline(0, color='k', linestyle='--')
plt.xlabel(r'Asymmetry Degradation $\alpha$ (0=Ideal, 1=Symmetric)')
plt.ylabel(r'Extracted Power $\dot{W}$')
plt.title('Cycle 1: Robustness against Asymmetry Loss')
plt.tight_layout()
plt.savefig('noise_1_asymmetry.png', dpi=300)

print("Cycle 2: Charge Dephasing")
gamma_phis = np.logspace(-3, 1, 40)
W_phis = []
for gp in gamma_phis:
    W_phis.append(simulate_noise(gamma_phi=gp))

plt.figure(figsize=(6, 4))
plt.plot(gamma_phis, W_phis, 'o-', color='orange')
plt.axhline(0, color='k', linestyle='--')
plt.xscale('log')
plt.xlabel(r'Dephasing Rate $\gamma_\phi$')
plt.ylabel(r'Extracted Power $\dot{W}$')
plt.title('Cycle 2: Robustness against Dephasing')
plt.tight_layout()
plt.savefig('noise_2_dephasing.png', dpi=300)

print("Cycle 3: Demon Random Flip")
gamma_rands = np.logspace(-3, 1, 40)
W_rands = []
for gr in gamma_rands:
    W_rands.append(simulate_noise(gamma_rand=gr))

plt.figure(figsize=(6, 4))
plt.plot(gamma_rands, W_rands, 'o-', color='red')
plt.axhline(0, color='k', linestyle='--')
plt.xscale('log')
plt.xlabel(r'Demon Flip Rate $\gamma_{rand}$')
plt.ylabel(r'Extracted Power $\dot{W}$')
plt.title('Cycle 3: Robustness against Demon Measurement Noise')
plt.tight_layout()
plt.savefig('noise_3_demon_flip.png', dpi=300)

print("All cycles completed successfully.")
