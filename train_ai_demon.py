import os
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback
from stable_baselines3.common.monitor import Monitor
import matplotlib.pyplot as plt
import numpy as np

from quantum_demon_env import QuantumDemonEnv

print("Initializing AI-Demon Training Pipeline...")

# Create environments
env = Monitor(QuantumDemonEnv())
eval_env = Monitor(QuantumDemonEnv())

# Define model
model = PPO("MlpPolicy", env, verbose=1, learning_rate=3e-4, n_steps=2048, batch_size=64, device="cpu")

# Setup evaluation callback
os.makedirs("models", exist_ok=True)
eval_callback = EvalCallback(eval_env, best_model_save_path='./models/',
                             log_path='./models/', eval_freq=5000,
                             deterministic=True, render=False)

print("Starting PPO Training...")
# Train model
total_timesteps = 50000
model.learn(total_timesteps=total_timesteps, callback=eval_callback)

print("Training finished. Saving final model...")
model.save("models/ai_demon_model_final")

# Plot learning curve if monitor logs exist
try:
    from stable_baselines3.common.results_plotter import load_results, ts2xy
    x, y = ts2xy(load_results("models"), 'timesteps')
    plt.figure()
    plt.plot(x, y)
    plt.xlabel('Timesteps')
    plt.ylabel('Episodic Reward (Extracted Work)')
    plt.title('AI Demon Learning Curve')
    plt.savefig('models/learning_curve.png')
    print("Saved learning curve to models/learning_curve.png")
except Exception as e:
    print(f"Could not plot learning curve: {e}")
