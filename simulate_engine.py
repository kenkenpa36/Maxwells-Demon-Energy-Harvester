import numpy as np
import matplotlib.pyplot as plt
import qutip as qt

print("Initializing simulation...")

# 1. Define Hilbert space operators
# Tensor product of 3 qubits: L, R, D
sm = qt.sigmam()
sz = qt.sigmaz()
iden = qt.qeye(2)

# Jordan-Wigner transformation for fermions
dL = qt.tensor(sm, iden, iden)
dR = qt.tensor(sz, sm, iden)
dD = qt.tensor(sz, sz, sm)

iden3 = qt.tensor(iden, iden, iden)

nL = dL.dag() * dL
nR = dR.dag() * dR
nD = dD.dag() * dD

# 2. Parameters
eps = 0.0          # Energy of working dots
U = 200.0          # Coulomb repulsion between D and L/R
U_LR = 5000.0      # Coulomb repulsion between L and R (ensures single occupation)
T = 1000.0         # Temperature of L, R and phonon baths
TD = 10.0          # Temperature of Demon bath (much colder)
muL = 50.0         # Chemical potential L
muR = -50.0        # Chemical potential R (Bias eV = muL - muR = 100 > 0)
muD = 0.0          # Chemical potential D
epsD = muD - U/2.0 # Demon dot energy level

# Asymmetric tunneling rates (Information engine condition)
kappaL = 1.0       # Rate at eps
kappaL_U = 0.01    # Rate at eps + U
kappaR = 0.01      # Rate at eps
kappaR_U = 1.0     # Rate at eps + U
kappaD = 2.0       # Demon tunneling rate (faster than R)

gamma_ph = 0.1     # Phonon bath relaxation rate

# Fermi-Dirac distribution
def fD(E, mu, temp):
    # Prevent overflow
    exponent = np.clip((E - mu) / temp, -100, 100)
    return 1.0 / (np.exp(exponent) + 1.0)

# 3. Transition rates
# L bath
G_L_in_0 = kappaL * fD(eps, muL, T)
G_L_out_0 = kappaL * (1.0 - fD(eps, muL, T))
G_L_in_1 = kappaL_U * fD(eps + U, muL, T)
G_L_out_1 = kappaL_U * (1.0 - fD(eps + U, muL, T))

# R bath
G_R_in_0 = kappaR * fD(eps, muR, T)
G_R_out_0 = kappaR * (1.0 - fD(eps, muR, T))
G_R_in_1 = kappaR_U * fD(eps + U, muR, T)
G_R_out_1 = kappaR_U * (1.0 - fD(eps + U, muR, T))

# D bath
G_D_in_0 = kappaD * fD(epsD, muD, TD)
G_D_out_0 = kappaD * (1.0 - fD(epsD, muD, TD))
G_D_in_1 = kappaD * fD(epsD + U, muD, TD)
G_D_out_1 = kappaD * (1.0 - fD(epsD + U, muD, TD))
G_D_in_2 = kappaD * fD(epsD + 2*U, muD, TD)
G_D_out_2 = kappaD * (1.0 - fD(epsD + 2*U, muD, TD))

# 4. Jump operators (Partial-Secular Semilocal Lindblad)
P_D0 = iden3 - nD
P_D1 = nD

P_LR0 = (iden3 - nL) * (iden3 - nR)
P_LR1 = nL * (iden3 - nR) + (iden3 - nL) * nR
P_LR2 = nL * nR

c_ops = []
# L dot jumps
c_ops_L = [
    np.sqrt(G_L_in_0) * dL.dag() * P_D0,
    np.sqrt(G_L_out_0) * dL * P_D0,
    np.sqrt(G_L_in_1) * dL.dag() * P_D1,
    np.sqrt(G_L_out_1) * dL * P_D1
]
c_ops.extend(c_ops_L)

# R dot jumps
c_ops_R = [
    np.sqrt(G_R_in_0) * dR.dag() * P_D0,
    np.sqrt(G_R_out_0) * dR * P_D0,
    np.sqrt(G_R_in_1) * dR.dag() * P_D1,
    np.sqrt(G_R_out_1) * dR * P_D1
]
c_ops.extend(c_ops_R)

# D dot jumps
c_ops_D = [
    np.sqrt(G_D_in_0) * dD.dag() * P_LR0,
    np.sqrt(G_D_out_0) * dD * P_LR0,
    np.sqrt(G_D_in_1) * dD.dag() * P_LR1,
    np.sqrt(G_D_out_1) * dD * P_LR1,
    np.sqrt(G_D_in_2) * dD.dag() * P_LR2,
    np.sqrt(G_D_out_2) * dD * P_LR2
]
c_ops.extend(c_ops_D)

# Phonon bath jumps (coherent tunneling decoherence)
c_ops.append(np.sqrt(gamma_ph) * (dL.dag() * dR + dR.dag() * dL))

def calc_I_L(rho):
    """ Calculate particle current from bath L into dot L """
    rate = 0.0
    for c in c_ops_L:
        op = c.dag() * nL * c - 0.5 * (nL * c.dag() * c + c.dag() * c * nL)
        rate += qt.expect(op, rho)
    return rate

# 5. Sweep over tunneling coupling g
print("Sweeping tunneling coupling g...")
gs = np.logspace(-2, 1, 40)
currents = []
works = []

# Base Hamiltonian (without tunneling)
H_base = eps * (nL + nR) + epsD * nD + U_LR * nL * nR + U * nD * (nL + nR)

for g in gs:
    H = H_base + g * (dL.dag() * dR + dR.dag() * dL)
    
    # Solve steady state
    rho_ss = qt.steadystate(H, c_ops)
    
    # I_L is current from bath L to system
    # To act as engine, particles must flow from R (low mu) to L (high mu)
    # i.e., system to bath L -> I_L < 0.
    # We define positive current as R -> L.
    I_R_to_L = -calc_I_L(rho_ss)
    currents.append(I_R_to_L)
    
    # Extracted power (W_dot). Work is done if W_dot > 0 (or convention W_dot < 0 for extraction, but W > 0 here means energy extracted to electrical bias)
    # Energy generated: (mu_L - mu_R) * I_R_to_L
    W_dot = (muL - muR) * I_R_to_L
    works.append(W_dot)

print("Simulation complete. Generating plot...")

# 6. Plotting
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

ax1.plot(gs, currents, 'o-', color='tab:blue', markersize=4)
ax1.set_xscale('log')
ax1.axhline(0, color='k', linestyle='--', linewidth=1)
ax1.set_xlabel('Tunnel coupling $g$')
ax1.set_ylabel('Particle Current $I$ (R -> L)')
ax1.set_title('Particle Current vs Coherence')
ax1.grid(True, alpha=0.3)

ax2.plot(gs, works, 'o-', color='tab:orange', markersize=4)
ax2.set_xscale('log')
ax2.axhline(0, color='k', linestyle='--', linewidth=1)
ax2.set_xlabel('Tunnel coupling $g$')
ax2.set_ylabel(r'Extracted Power $\dot{W}$')
ax2.set_title('Extracted Power vs Coherence')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('results.png', dpi=300)
print("Saved results.png")
