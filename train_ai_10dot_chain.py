import os
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.callbacks import EvalCallback
from stable_baselines3.common.monitor import Monitor
import matplotlib.pyplot as plt

from quantum_10dot_env import Quantum10DotEnv

print("Initializing 10-Dot AI-Demon Training Pipeline...")

env = Monitor(Quantum10DotEnv())
eval_env = Monitor(Quantum10DotEnv())

# Define model (using CPU for QuTiP stability)
# Recurrent PPO uses an LSTM hidden state to track history and solve POMDP
model = RecurrentPPO("MlpLstmPolicy", env, verbose=1, learning_rate=3e-4, n_steps=4000, batch_size=64, device="cpu")

os.makedirs("models", exist_ok=True)
eval_callback = EvalCallback(eval_env, best_model_save_path='./models/',
                             log_path='./models/', eval_freq=12000,
                             deterministic=True, render=False)

print("Starting PPO Training for 10-Dot Chain...")
# Large-scale training to discover conveyor belt strategy
total_timesteps = 1000000 
model.learn(total_timesteps=total_timesteps, callback=eval_callback)

print("Training finished. Saving final model...")
model.save("models/ai_10dot_rnn_model_final")
