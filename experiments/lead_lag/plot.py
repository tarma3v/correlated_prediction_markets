"""Plot matched next-day MAE changes relative to both reference forecasts."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent
results = pd.read_csv(root / "results" / "forecast_metrics.csv").query("sample == 'all'")
order = [("fomc", "kalshi"), ("fomc", "polymarket"), ("senate", "kalshi"), ("senate", "polymarket")]
results = results.set_index(["cohort", "target"]).loc[order]
labels = ["ФРС · Kalshi", "ФРС · Polymarket", "Сенат · Kalshi", "Сенат · Polymarket"]
fig, axes = plt.subplots(1, 2, figsize=(9.3, 3.3), layout="constrained", sharey=True)
y = np.arange(len(results))
for ax, name, low, high, title in [
    (axes[0], "gain_pp", "ci_low_pp", "ci_high_pp", "Модель своей площадки"),
    (axes[1], "gain_vs_persist_pp", "ci_vs_persist_low_pp", "ci_vs_persist_high_pp", "Последняя цена"),
]:
    values = results[name]
    ax.axvline(0, color="#68717a", lw=1, zorder=0)
    ax.errorbar(values, y, xerr=[values - results[low], results[high] - values],
                fmt="o", ms=6, color="#155b75", capsize=4, lw=2)
    ax.set(yticks=y, yticklabels=labels, ylim=(3.6, -.6), title=title)
    ax.margins(x=.1)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.grid(axis="x", alpha=.18)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
fig.suptitle("Улучшает ли цена другой площадки прогноз на следующий день?", weight="bold")
fig.supxlabel("MAE базы минус MAE межплощадочной модели, п.п. Выигрыш при значении выше нуля.", fontsize=10)
fig.savefig(root / "results" / "mae_gain.png", dpi=180, bbox_inches="tight")
