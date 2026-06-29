import re

with open("Quantum_Energy_Harvesting_Paper.md", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Frontmatter and general wrapping
latex_header = r"""\documentclass[a4paper,11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{listings}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{CJKutf8}

\lstset{
    backgroundcolor=\color{gray!10},
    basicstyle=\ttfamily\footnotesize,
    breaklines=true,
    keywordstyle=\color{blue},
    commentstyle=\color{green!50!black},
    stringstyle=\color{red}
}

\title{Breaking the Second Law Limits: From Autonomous Maxwell's Demons to Quantum Landauer Energy Harvesters}
\author{Imaken et al.}
\date{2026-06-21}

\begin{document}
\begin{CJK*}{UTF8}{min}
\maketitle

"""

latex_footer = r"""
\end{CJK*}
\end{document}
"""

# Strip yaml header
if text.startswith("---"):
    text = text.split("---", 2)[2]

# Remove Abstract bold text and standard title since maketitle handles it
text = re.sub(r'# Breaking the Second Law Limits: From Autonomous Maxwell\'s Demons to Quantum Landauer Energy Harvesters\n*', '', text)
text = re.sub(r'\*\*Authors\*\*: Imaken et al.\n*', '', text)
text = re.sub(r'\*\*Keywords\*\*:.*?\n*', '', text)

# Bold: **bold** -> \textbf{bold}
text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)

# Code blocks
def code_repl(m):
    lang = m.group(1) if m.group(1) else ""
    code = m.group(2)
    return r"\begin{lstlisting}[language=Python]" + "\n" + code + r"\end{lstlisting}"

text = re.sub(r'```([a-zA-Z]*)\n(.*?)```', code_repl, text, flags=re.DOTALL)

# Math display: $$ ... $$ -> \begin{equation} ... \end{equation}
def math_repl(m):
    return r"\begin{equation}" + m.group(1) + r"\end{equation}"
text = re.sub(r'\$\$(.*?)\$\$', math_repl, text, flags=re.DOTALL)

# Images: ![caption](path) -> figure
def img_repl(m):
    cap = m.group(1)
    path = m.group(2)
    return r"""
\begin{figure}[h]
\centering
\includegraphics[width=0.8\textwidth]{""" + path + r"""}
\caption{""" + cap + r"""}
\end{figure}
"""
text = re.sub(r'!\[([^\]]+)\]\(([^)]+)\)', img_repl, text)

# Headers
text = re.sub(r'^### (.*?)$', r'\\subsubsection{\1}', text, flags=re.MULTILINE)
text = re.sub(r'^## (.*?)$', r'\\subsection{\1}', text, flags=re.MULTILINE)
text = re.sub(r'^# (.*?)$', r'\\section{\1}', text, flags=re.MULTILINE)

# Horizontal lines
text = re.sub(r'^---$', r'\\vspace{1em}\\hrule\\vspace{1em}', text, flags=re.MULTILINE)

# Items (Numbered lists)
text = re.sub(r'^(\d+)\.\s+(.*)$', r'\\begin{enumerate}\n\\item \2\n\\end{enumerate}', text, flags=re.MULTILINE)
# Combine multiple enumerate
text = re.sub(r'\\end\{enumerate\}\n\\begin\{enumerate\}', '', text)

# Escape percentages not inside equations (very naive approach)
text = text.replace("%", r"\%")

# Undo escaping inside lstlisting
def unescape_lst(m):
    return m.group(0).replace(r"\%", "%")
text = re.sub(r'\\begin\{lstlisting\}.*?\\end\{lstlisting\}', unescape_lst, text, flags=re.DOTALL)

final_tex = latex_header + text + latex_footer

with open("Quantum_Energy_Harvesting_Paper.tex", "w", encoding="utf-8") as f:
    f.write(final_tex)
print("Saved to Quantum_Energy_Harvesting_Paper.tex")
