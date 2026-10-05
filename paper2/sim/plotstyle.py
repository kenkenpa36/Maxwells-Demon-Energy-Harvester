"""共通の作図設定 (日本語フォント)。各スクリプトの先頭で import する。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.family": ["Noto Sans CJK JP", "DejaVu Sans"],
    "mathtext.fontset": "dejavusans",
    "axes.unicode_minus": False,
    "font.size": 10,
    "pdf.fonttype": 42,
})
