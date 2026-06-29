import os

paper_file = "Quantum_Energy_Harvesting_Paper.md"
with open(paper_file, "r", encoding="utf-8") as f:
    content = f.read()

# Make it more formal by adding frontmatter and keywords if not present
if "---" not in content[:10]:
    formal_header = """---
title: "Breaking the Second Law Limits: From Autonomous Maxwell's Demons to Quantum Landauer Energy Harvesters"
author: "Imaken et al."
date: "2026-06-21"
keywords: ["Quantum Thermodynamics", "Maxwell's Demon", "Deep Reinforcement Learning", "Energy Harvesting", "Quantum Entanglement", "POMDP"]
---

# Breaking the Second Law Limits: From Autonomous Maxwell's Demons to Quantum Landauer Energy Harvesters

**Authors**: Imaken et al.

**Keywords**: Quantum Thermodynamics, Maxwell's Demon, Deep Reinforcement Learning, Energy Harvesting, Quantum Entanglement

"""
    # Replace the old title
    old_title = "# Breaking the Second Law Limits: From Autonomous Maxwell's Demons to Quantum Landauer Energy Harvesters\n\n**Authors**: Imaken et al.\n"
    content = content.replace(old_title, formal_header)

files_to_append = [
    "quantum_10dot_env.py",
    "train_ai_10dot_chain.py",
    "evaluate_ai_10dot_chain.py",
    "simulate_macroscopic_quantum_engine.py",
    "quantum_demon_env.py"
]

appendix = "\n\n---\n\n## Appendix: Simulation Source Code\n\n本論文のシミュレーションおよび強化学習環境の構築に用いた主要なソースコード（Python / QuTiP / Stable Baselines 3）を以下に添付する。\n\n"

for fname in files_to_append:
    if os.path.exists(fname):
        with open(fname, "r", encoding="utf-8") as code_f:
            code_str = code_f.read()
        appendix += f"### Appendix: `{fname}`\n\n```python\n{code_str}\n```\n\n"

with open(paper_file, "w", encoding="utf-8") as f:
    f.write(content + appendix)

print(f"Successfully updated {paper_file} with formal formatting and appended source code.")
