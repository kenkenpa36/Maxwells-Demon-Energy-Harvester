import numpy as np
import matplotlib.pyplot as plt
import qutip as qt
from sb3_contrib import RecurrentPPO

from quantum_10dot_env import Quantum10DotEnv

print("Evaluating 10-Dot AI Demon vs Baselines...")

model_path = "models/ai_10dot_rnn_model_final"
try:
    model = RecurrentPPO.load(model_path, device="cpu")
except Exception as e:
    print(f"Error loading model: {e}")
    exit(1)

env = Quantum10DotEnv()
n_dots = env.n_dots
n_steps = env.max_steps
dt = env.dt

def evaluate_policy(env, policy_type="ai", n_episodes=20):
    all_extracted_work = []
    all_P_matrix = []
    
    for ep in range(n_episodes):
        obs, _ = env.reset()
        extracted_work_list = []
        P_matrix = np.zeros((n_steps, env.dim))
        
        lstm_states = None
        episode_starts = np.ones((1,), dtype=bool)
        
        for i in range(n_steps):
            if policy_type == "ai":
                action, lstm_states = model.predict(obs, state=lstm_states, episode_start=episode_starts, deterministic=True)
                episode_starts = np.zeros((1,), dtype=bool)
                # action is a multi-binary array of shape (11,)
            elif policy_type == "bayesian":
                P = obs[:env.dim]
                action = np.zeros(11, dtype=np.int8)
                if P[0] > 0.5:
                    action[0] = 1 # kappaL
                else:
                    x = np.argmax(P[1:]) + 1
                    if x < n_dots:
                        action[x] = 1 # g_rates[x]
                    else:
                        action[10] = 1 # kappaR
            else: # no feedback
                action = np.ones(11, dtype=np.int8)
                
            obs, reward, terminated, truncated, _ = env.step(action)
            
            extracted_work_list.append(env.extracted_work)
            P = [np.real(env.rho[j,j]) for j in range(env.dim)]
            P_matrix[i, :] = P
            
            if terminated or truncated:
                break
                
        all_extracted_work.append(extracted_work_list)
        all_P_matrix.append(P_matrix)
        
    avg_extracted_work = np.mean(all_extracted_work, axis=0)
    std_extracted_work = np.std(all_extracted_work, axis=0)
    avg_P_matrix = np.mean(all_P_matrix, axis=0)
    
    return avg_extracted_work, std_extracted_work, avg_P_matrix

N_EPISODES = 20
print(f"Running {N_EPISODES} episodes per policy for robust evaluation...")

print("Running AI Policy...")
w_ai_mean, w_ai_std, P_mat_ai = evaluate_policy(env, policy_type="ai", n_episodes=N_EPISODES)
print("Running Classical Bayesian Policy...")
w_bayes_mean, w_bayes_std, P_mat_bayes = evaluate_policy(env, policy_type="bayesian", n_episodes=N_EPISODES)
print("Running No Feedback...")
w_none_mean, w_none_std, P_mat_none = evaluate_policy(env, policy_type="none", n_episodes=N_EPISODES)

print(f"Total Work (No Feedback) : {w_none_mean[-1]:.4f} +/- {w_none_std[-1]:.4f}")
print(f"Total Work (Bayesian)    : {w_bayes_mean[-1]:.4f} +/- {w_bayes_std[-1]:.4f}")
print(f"Total Work (AI Demon)    : {w_ai_mean[-1]:.4f} +/- {w_ai_std[-1]:.4f}")

plt.figure(figsize=(15, 10))

ax1 = plt.subplot(2, 3, 1)
im1 = ax1.imshow(P_mat_none[:, 1:].T, aspect='auto', origin='lower', cmap='inferno', interpolation='nearest',
                 extent=[0, n_steps*dt, 1, n_dots])
ax1.set_ylabel('Dot Position')
ax1.set_title('No Feedback')
plt.colorbar(im1, ax=ax1)

ax2 = plt.subplot(2, 3, 2)
im2 = ax2.imshow(P_mat_bayes[:, 1:].T, aspect='auto', origin='lower', cmap='inferno', interpolation='nearest',
                 extent=[0, n_steps*dt, 1, n_dots])
ax2.set_title('Classical Bayesian')
plt.colorbar(im2, ax=ax2)

ax3 = plt.subplot(2, 3, 3)
im3 = ax3.imshow(P_mat_ai[:, 1:].T, aspect='auto', origin='lower', cmap='inferno', interpolation='nearest',
                 extent=[0, n_steps*dt, 1, n_dots])
ax3.set_title('AI Demon (PPO MultiBinary)')
plt.colorbar(im3, ax=ax3)

ax4 = plt.subplot(2, 1, 2)
t_axis = np.arange(n_steps) * dt
ax4.plot(t_axis, w_ai_mean, color='green', linewidth=2, label=f'AI Demon (Total: {w_ai_mean[-1]:.2f}±{w_ai_std[-1]:.1f})')
ax4.fill_between(t_axis, w_ai_mean - w_ai_std, w_ai_mean + w_ai_std, color='green', alpha=0.2)

ax4.plot(t_axis, w_bayes_mean, color='blue', linewidth=2, label=f'Classical Bayesian (Total: {w_bayes_mean[-1]:.2f}±{w_bayes_std[-1]:.1f})')
ax4.fill_between(t_axis, w_bayes_mean - w_bayes_std, w_bayes_mean + w_bayes_std, color='blue', alpha=0.2)

ax4.plot(t_axis, w_none_mean, color='orange', linewidth=2, label=f'No Feedback (Total: {w_none_mean[-1]:.2f}±{w_none_std[-1]:.1f})')
ax4.fill_between(t_axis, w_none_mean - w_none_std, w_none_mean + w_none_std, color='orange', alpha=0.2)

ax4.axhline(0, color='k', linestyle='--')
ax4.set_xlabel('Time')
ax4.set_ylabel('Average Extracted Work')
ax4.set_title(f'Performance Comparison: 10-Dot Conveyor Belt (Averaged over {N_EPISODES} episodes)')
ax4.legend(loc='upper left')

plt.tight_layout()
plt.savefig('ai_10dot_dynamics.png', dpi=300)
print("Saved ai_10dot_dynamics.png")
