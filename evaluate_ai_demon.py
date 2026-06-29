import numpy as np
import matplotlib.pyplot as plt
import qutip as qt
from stable_baselines3 import PPO

from quantum_demon_env import QuantumDemonEnv

print("Evaluating AI Demon vs Baselines...")

# Load Model
model_path = "models/ai_demon_model_final"
try:
    model = PPO.load(model_path, device="cpu")
except Exception as e:
    print(f"Error loading model: {e}")
    exit(1)

# Initialize Env
env = QuantumDemonEnv()

# Function to run an episode and collect stats
def evaluate_policy(env, policy_type="ai", n_steps=3000):
    obs, _ = env.reset()
    extracted_work_list = []
    prob_list = []
    
    for i in range(n_steps):
        if policy_type == "ai":
            action, _states = model.predict(obs, deterministic=True)
            action = int(action)
        elif policy_type == "bayesian":
            P_N = obs[0] + obs[1] * 2  # Not exactly correct but we can re-extract from env
            exp_N = qt.expect(env.N_op, env.rho)
            if exp_N < 0.5:
                action = 1 # R ON, L OFF
            else:
                action = 2 # L ON, R OFF
        else: # no feedback
            action = 3 # L ON, R ON
            
        obs, reward, terminated, truncated, _ = env.step(action)
        
        extracted_work_list.append(env.extracted_work)
        exp_N = qt.expect(env.N_op, env.rho)
        prob_list.append(exp_N)
        
        if terminated or truncated:
            break
            
    return extracted_work_list, prob_list

# Run evaluations
print("Running AI Policy...")
w_ai, p_ai = evaluate_policy(env, policy_type="ai")
print("Running Classical Bayesian Policy...")
w_bayes, p_bayes = evaluate_policy(env, policy_type="bayesian")
print("Running No Feedback...")
w_none, p_none = evaluate_policy(env, policy_type="none")

print(f"Total Work (No Feedback) : {w_none[-1]:.4f}")
print(f"Total Work (Bayesian)    : {w_bayes[-1]:.4f}")
print(f"Total Work (AI Demon)    : {w_ai[-1]:.4f}")

# Plotting
t_axis = np.arange(len(w_ai)) * env.dt

plt.figure(figsize=(10, 8))

plt.subplot(2, 1, 1)
plt.plot(t_axis, p_ai, color='green', linewidth=1.5, label='AI Policy State $\langle N \\rangle$')
plt.plot(t_axis, p_bayes, color='blue', linewidth=1.5, alpha=0.6, label='Bayesian Policy State $\langle N \\rangle$')
plt.ylabel('Expectation $\langle N \\rangle$')
plt.title('System Dynamics under AI vs Classical Feedback')
plt.legend(loc='upper right')

plt.subplot(2, 1, 2)
plt.plot(t_axis, w_ai, color='green', linewidth=2, label=f'AI Demon (Total: {w_ai[-1]:.2f})')
plt.plot(t_axis, w_bayes, color='blue', linewidth=2, label=f'Bayesian (Total: {w_bayes[-1]:.2f})')
plt.plot(t_axis, w_none, color='orange', linewidth=2, label=f'No Feedback (Total: {w_none[-1]:.2f})')
plt.axhline(0, color='k', linestyle='-')
plt.xlabel('Time')
plt.ylabel('Accumulated Work')
plt.title('Performance Comparison: Work Extraction')
plt.legend(loc='upper left')

plt.tight_layout()
plt.savefig('ai_demon_results.png', dpi=300)
print("Saved ai_demon_results.png")
