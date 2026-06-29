import gymnasium as gym
from gymnasium import spaces
import numpy as np
import qutip as qt

class QuantumDemonEnv(gym.Env):
    """
    Gymnasium environment for a 2-dot quantum information engine (Maxwell's demon).
    The agent controls the tunneling barriers (L and R) to extract work against a voltage bias.
    """
    metadata = {"render_modes": ["human"]}

    def __init__(self):
        super().__init__()
        
        # System Setup (2 dots L and R)
        self.sm = qt.sigmam()
        self.sz = qt.sigmaz()
        self.iden = qt.qeye(2)
        
        self.dL = qt.tensor(self.sm, self.iden)
        self.dR = qt.tensor(self.sz, self.sm)
        
        self.nL = self.dL.dag() * self.dL
        self.nR = self.dR.dag() * self.dR
        self.N_op = self.nL + self.nR
        
        # Parameters
        self.T = 1000.0
        self.muL = 50.0   # High potential
        self.muR = -50.0  # Low potential
        self.eps = 0.0
        self.U_LR = 5000.0
        self.g = 0.5
        
        # Homodyne Measurement Strength (k)
        self.k_meas = 5.0
        self.Lm = np.sqrt(self.k_meas) * self.N_op
        
        self.H0 = self.eps * (self.nL + self.nR) + self.U_LR * self.nL * self.nR + self.g * (self.dL.dag() * self.dR + self.dR.dag() * self.dL)
        
        self.dt = 0.005
        self.max_steps = 3000
        
        self.kappa_ON = 5.0
        self.kappa_OFF = 0.01
        
        # Action space: 4 discrete actions
        # 0: L OFF, R OFF
        # 1: L OFF, R ON
        # 2: L ON,  R OFF
        # 3: L ON,  R ON
        self.action_space = spaces.Discrete(4)
        
        # Observation space: Probabilities of 4 basis states (diagonal of rho)
        # plus the noisy measurement signal dy/dt
        self.observation_space = spaces.Box(low=-100.0, high=100.0, shape=(5,), dtype=np.float32)
        
        self.reset()
        
    def fD(self, E, mu, temp):
        exponent = np.clip((E - mu) / temp, -100, 100)
        return 1.0 / (np.exp(exponent) + 1.0)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # Initialize to empty state
        self.rho = qt.tensor(qt.fock_dm(2,0), qt.fock_dm(2,0))
        self.current_step = 0
        self.extracted_work = 0.0
        
        # Initial observation
        obs = self._get_obs(dy_dt=0.0)
        return obs, {}

    def _get_obs(self, dy_dt):
        diag = self.rho.diag()
        probs = np.real(diag)
        # State probabilities + latest measurement signal
        obs = np.array([probs[0], probs[1], probs[2], probs[3], dy_dt], dtype=np.float32)
        return obs

    def step(self, action):
        if action == 0:
            kappaL, kappaR = self.kappa_OFF, self.kappa_OFF
        elif action == 1:
            kappaL, kappaR = self.kappa_OFF, self.kappa_ON
        elif action == 2:
            kappaL, kappaR = self.kappa_ON, self.kappa_OFF
        elif action == 3:
            kappaL, kappaR = self.kappa_ON, self.kappa_ON
            
        G_L_in = kappaL * self.fD(self.eps, self.muL, self.T)
        G_L_out = kappaL * (1.0 - self.fD(self.eps, self.muL, self.T))
        G_R_in = kappaR * self.fD(self.eps, self.muR, self.T)
        G_R_out = kappaR * (1.0 - self.fD(self.eps, self.muR, self.T))
        
        c_ops = [
            np.sqrt(G_L_in) * self.dL.dag(),
            np.sqrt(G_L_out) * self.dL,
            np.sqrt(G_R_in) * self.dR.dag(),
            np.sqrt(G_R_out) * self.dR
        ]
        
        # Current leaving the system to Bath L
        exp_nL = qt.expect(self.nL, self.rho)
        I_L_out = G_L_out * exp_nL - G_L_in * (1 - exp_nL)
        
        # Work extracted = Energy gained by moving to high potential
        W_dot = (self.muL - self.muR) * I_L_out
        reward = W_dot * self.dt
        self.extracted_work += reward
        
        # SME Update
        L_rho = -1j * (self.H0 * self.rho - self.rho * self.H0)
        for c in c_ops:
            L_rho += c * self.rho * c.dag() - 0.5 * (c.dag() * c * self.rho + self.rho * c.dag() * c)
            
        # Measurement Decoherence
        L_rho += self.Lm * self.rho * self.Lm.dag() - 0.5 * (self.Lm.dag() * self.Lm * self.rho + self.rho * self.Lm.dag() * self.Lm)
        
        dW = np.random.normal(0, np.sqrt(self.dt))
        exp_Lm = qt.expect(self.Lm + self.Lm.dag(), self.rho)
        dy = exp_Lm * self.dt + dW
        dy_dt = dy / self.dt
        
        # Innovations
        innov = self.Lm * self.rho + self.rho * self.Lm.dag() - exp_Lm * self.rho
        
        rho_new = self.rho + L_rho * self.dt + innov * dW
        rho_new = rho_new / rho_new.tr()
        self.rho = rho_new
        
        self.current_step += 1
        terminated = False
        truncated = bool(self.current_step >= self.max_steps)
        
        obs = self._get_obs(dy_dt)
        
        # Add small penalty to encourage action switching or simply return reward
        return obs, float(reward), terminated, truncated, {}
