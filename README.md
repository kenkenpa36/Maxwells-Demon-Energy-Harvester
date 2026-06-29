# Macroscopic Quantum Entanglement Engine

This repository contains the source code, numerical simulations, and the research paper for the **Macroscopic Quantum Entanglement Engine** project. The project explores the theoretical and practical limits of autonomous information engines (Maxwell's Demons) and demonstrates macroscopic energy harvesting through quantum information thermodynamics, Bayesian inference, and quantum entanglement.

## Key Features

1. **Autonomous Quantum Demon Simulation**: Rigorous master equation simulations (Partial-Secular Semilocal Lindblad approach) of a 3-body quantum dot system using QuTiP.
2. **Macroscopic Scale-up via Circuit QED**: Implementation of an "Information Conveyor Belt" in a 10-dot chain using continuous measurement and Quantum Bayesian Inference (Kalman Filter).
3. **Beating the Landauer Limit**: Simulation of the "Quantum Landauer Loophole", achieving negative erasure costs and net-positive power generation via maximum quantum entanglement at room temperature.
4. **Autonomous Strategy Discovery (DRL)**: Gymnasium-compatible environments for quantum engines, optimized using Deep Reinforcement Learning (Recurrent PPO via Stable Baselines 3) to autonomously discover robust energy-harvesting strategies.

## System Requirements & Environment

To run the quantum thermodynamic simulations and train the Deep Reinforcement Learning models (Recurrent PPO), the following environment is recommended:

### Hardware Requirements
- **OS**: Linux (Ubuntu 20.04/22.04 recommended), macOS, or Windows (WSL2)
- **CPU**: Multi-core processor (4+ cores recommended for parallel QuTiP master equation simulations)
- **RAM**: 16 GB minimum (32 GB recommended for the macroscopic 10-dot chain Bayesian simulations)
- **GPU**: NVIDIA GPU (Optional, but highly recommended for accelerating PyTorch / Stable Baselines 3 training)

### Software & Dependencies
- **Python**: 3.8 or higher

Main libraries required:
- `qutip` (Quantum Toolbox in Python - for core quantum dynamics)
- `torch` (PyTorch - for neural network backend)
- `gymnasium` (RL environment API)
- `stable-baselines3` (PPO implementation)
- `sb3-contrib` (RecurrentPPO implementation)
- `numpy`, `matplotlib`, `scipy`

### Installation

You can install all dependencies via pip:
```bash
pip install qutip numpy scipy matplotlib gymnasium stable-baselines3 sb3-contrib torch
```

## Repository Structure

### Simulation Scripts
- `simulate_engine.py`: Basic 3-dot autonomous demon simulation.
- `simulate_realistic_engine.py` / `simulate_noise_cycle.py`: Noise and breakdown threshold analysis.
- `simulate_bayesian_demon.py` / `simulate_10dot_chain.py`: Bayesian inference feedback control on a 10-dot chain.
- `simulate_quantum_loophole.py`: Simulation of negative erasure cost using entangled states.
- `simulate_macroscopic_quantum_engine.py`: Integrated macroscopic energy harvester simulation.

### Reinforcement Learning (AI Demon)
- `quantum_demon_env.py`: Gymnasium environment for a 2-dot AI Demon.
- `quantum_10dot_env.py`: Gymnasium environment for the 10-dot Conveyor Belt (POMDP).
- `train_ai_demon.py` / `evaluate_ai_demon.py`: Training and evaluation scripts for the basic AI demon.
- `train_ai_10dot_chain.py` / `evaluate_ai_10dot_chain.py`: Training and evaluation scripts using Recurrent PPO for the 10-dot chain.

### Research Paper
- `Quantum_Energy_Harvesting_Paper_English.tex`: The full research paper in English.
- `Quantum_Energy_Harvesting_Paper_Revised.tex`: The full research paper in Japanese (Revised version).
- `images/`: Directory containing generated plots and phase diagrams used in the paper.

## Running the Code

### 1. Run Simulations
Execute any of the simulation scripts directly to generate dynamics and thermodynamic balance plots:
```bash
python simulate_macroscopic_quantum_engine.py
```

### 2. Train the AI Demon
To train the 10-dot chain AI using Recurrent PPO:
```bash
python train_ai_10dot_chain.py
```
This will save the models into the `models/` directory. You can then evaluate the policy:
```bash
python evaluate_ai_10dot_chain.py
```

### 3. Compile the Paper
Ensure you have `latexmk` and a TeX distribution (like TeX Live) installed.
```bash
latexmk -pdf -interaction=nonstopmode Quantum_Energy_Harvesting_Paper_English.tex
```

## Authors
- Kengo Imai et al.

## Citation

If you use this code or data in your research, please cite our work. (Please update the arXiv ID and URL once published):

```bibtex
@misc{imai2026maxwell,
  author = {Imai, Kengo and others},
  title = {Breaking the Second Law Limits: From Autonomous Maxwell's Demons to Quantum Landauer Energy Harvesters},
  year = {2026},
  howpublished = {\url{https://github.com/kenkenpa36/Maxwells-Demon-Energy-Harvester}},
}
```

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0).

This means you are free to share and adapt the material for non-commercial purposes, provided you give appropriate credit. **Commercial use is strictly prohibited.** 
For details, see the [LICENSE](LICENSE) file.
