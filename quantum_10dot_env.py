import gymnasium as gym
from gymnasium import spaces
import numpy as np
import qutip as qt

class Quantum10DotEnv(gym.Env):
    """
    Gymnasium environment for a 10-dot quantum information engine (Information Conveyor Belt).
    The agent controls 11 barriers (L bath, 9 internal barriers, R bath) to pump an electron.
    """
    metadata = {"render_modes": ["human"]}

    def __init__(self):
        super().__init__()
        
        self.n_dots = 10
        self.dim = self.n_dots + 1
        
        self.proj = lambda i: qt.basis(self.dim, i) * qt.basis(self.dim, i).dag()
        self.jump = lambda i, j: qt.basis(self.dim, i) * qt.basis(self.dim, j).dag()
        
        # Measurement operator (center of mass)
        self.k_meas = 10.0
        self.Lm_op = sum((j / self.n_dots) * self.proj(j) for j in range(1, self.n_dots + 1))
        self.Lm = np.sqrt(self.k_meas) * self.Lm_op
        
        # Parameters
        self.T = 1000.0
        self.muL = 0.0
        self.muR = 100.0 
        self.eps = 0.0
        
        self.dt = 0.002
        self.max_steps = 4000
        
        self.kappa_ON = 5.0
        self.kappa_OFF = 0.01
        self.g_OFF = 0.0
        
        # Action space: MultiDiscrete([2]*11) to avoid PyTorch casting bug in RecurrentPPO
        # index 0: kappaL
        # index 1-9: g_rates[1] to g_rates[9]
        # index 10: kappaR
        self.action_space = spaces.MultiDiscrete([2] * 11)
        
        # Observation space: 11 probabilities + dy_dt
        self.observation_space = spaces.Box(low=-100.0, high=100.0, shape=(12,), dtype=np.float32)
        
        self.reset()
        
    def fD(self, E, mu, temp):
        exponent = np.clip((E - mu) / temp, -100, 100)
        return 1.0 / (np.exp(exponent) + 1.0)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # Initialize to empty state
        self.rho = self.proj(0)
        self.current_step = 0
        self.extracted_work = 0.0
        
        obs = self._get_obs(dy_dt=0.0)
        return obs, {}

    def _get_obs(self, dy_dt):
        P = [np.real(self.rho[j,j]) for j in range(self.dim)]
        obs = np.array(P + [dy_dt], dtype=np.float32)
        return obs

    def step(self, action):
        kappaL = self.kappa_ON if action[0] == 1 else self.kappa_OFF
        kappaR = self.kappa_ON if action[10] == 1 else self.kappa_OFF
        
        g_rates = np.zeros(self.n_dots)
        for j in range(1, self.n_dots):
            g_rates[j] = self.kappa_ON if action[j] == 1 else self.g_OFF
            
        H0 = qt.Qobj(np.zeros((self.dim, self.dim)))
        for j in range(1, self.n_dots):
            if g_rates[j] > 0:
                H0 += g_rates[j] * (self.jump(j, j+1) + self.jump(j+1, j))
                
        G_L_in = kappaL * self.fD(self.eps, self.muL, self.T)
        G_L_out = kappaL * (1.0 - self.fD(self.eps, self.muL, self.T))
        G_R_in = kappaR * self.fD(self.eps, self.muR, self.T)
        G_R_out = kappaR * (1.0 - self.fD(self.eps, self.muR, self.T))
        
        c_ops = [
            np.sqrt(G_L_in) * self.jump(1, 0),
            np.sqrt(G_L_out) * self.jump(0, 1),
            np.sqrt(G_R_in) * self.jump(self.n_dots, 0),
            np.sqrt(G_R_out) * self.jump(0, self.n_dots)
        ]
        
        P = [np.real(self.rho[j,j]) for j in range(self.dim)]
        I_R_out = G_R_out * P[self.n_dots] - G_R_in * P[0] 
        W_dot = (self.muR - self.muL) * I_R_out
        reward = W_dot * self.dt
        self.extracted_work += reward
        
        L_rho = -1j * (H0 * self.rho - self.rho * H0)
        for c in c_ops:
            L_rho += c * self.rho * c.dag() - 0.5 * (c.dag() * c * self.rho + self.rho * c.dag() * c)
            
        L_rho += self.Lm * self.rho * self.Lm.dag() - 0.5 * (self.Lm.dag() * self.Lm * self.rho + self.rho * self.Lm.dag() * self.Lm)
        
        dW = np.random.normal(0, np.sqrt(self.dt))
        exp_Lm = qt.expect(self.Lm + self.Lm.dag(), self.rho)
        dy = exp_Lm * self.dt + dW
        dy_dt = dy / self.dt
        
        innov = self.Lm * self.rho + self.rho * self.Lm.dag() - exp_Lm * self.rho
        
        rho_new = self.rho + L_rho * self.dt + innov * dW
        rho_new = rho_new / rho_new.tr()
        self.rho = rho_new
        
        self.current_step += 1
        terminated = False
        truncated = bool(self.current_step >= self.max_steps)
        
        obs = self._get_obs(dy_dt)
        
        return obs, float(reward), terminated, truncated, {}
