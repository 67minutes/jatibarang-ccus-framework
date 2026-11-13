"""Figure 8 - A/B/C economics, coverage, and top-five MRST confirmation."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from feature007_common import localize
import numpy as np

from feature007_common import blocked_main, load_table, parser, require_ready


OUT_DIR = Path(__file__).parent
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
COLORS = {"A": "#8C8C8C", "B": "#3E6FA8", "C": "#8A6D00"}


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


def generate() -> None:
    args = parser(8, __doc__).parse_args()
    manifest, _ = require_ready(args.bundle, args.figure_number)
    economics = load_table(args.bundle, manifest, "abc_economics")
    runtime = load_table(args.bundle, manifest, "abc_runtime")
    confirmation = load_table(args.bundle, manifest, "topk_confirmation")

    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 9.5,
            "axes.titlesize": 12,
            "axes.labelsize": 9.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "text.color": INK,
        }
    )
    fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.85), gridspec_kw={"wspace": 0.48})

    ax = axes[0]
    prices = sorted({float(row["carbon_price_usd_per_tonne"]) for row in economics})
    arms = [arm for arm in ("A", "B", "C") if any(row["arm"] == arm for row in economics)]
    width = 0.72 / len(arms)
    x = np.arange(len(prices))
    for offset, arm in enumerate(arms):
        rows = {float(row["carbon_price_usd_per_tonne"]): row for row in economics if row["arm"] == arm}
        values = np.array([float(rows[price]["npv_usd"]) / 1e6 for price in prices])
        low = np.array([float(rows[price]["npv_low_usd"]) / 1e6 for price in prices])
        high = np.array([float(rows[price]["npv_high_usd"]) / 1e6 for price in prices])
        ax.bar(x + (offset - (len(arms) - 1) / 2) * width, values, width=width, color=COLORS[arm], label=f"Arm {arm}",
               yerr=np.vstack([values - low, high - values]), capsize=2, linewidth=0)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xticks(x, [f"{price:.2f}".rstrip("0").rstrip(".").replace(".", ",") for price in prices])
    ax.set_xlabel("harga karbon (USD/t)")
    ax.set_ylabel("NPV (juta USD)")
    ax.set_title("(a)  Keekonomian", loc="left", fontweight="bold")
    top = max(float(row["npv_high_usd"]) for row in economics) / 1e6
    ax.set_ylim(0, top * 1.35)
    ax.legend(loc="upper left", ncol=len(arms), fontsize=7.0, frameon=False,
              handletextpad=0.4, columnspacing=0.8)
    _style(ax)

    ax = axes[1]
    for row in runtime:
        arm = row["arm"]
        ax.scatter(float(row["wall_clock_seconds"]) / 60,
                   float(row["scenarios_evaluated"]),
                   color=COLORS[arm], s=48, label=f"Arm {arm}")
        ax.annotate(f"{int(float(row['scenarios_evaluated']))}",
                    (float(row["wall_clock_seconds"]) / 60, float(row["scenarios_evaluated"])),
                    xytext=(4, 3), textcoords="offset points", fontsize=7.5)
    ax.set_yscale("log")
    ax.set_xlim(0, max(float(row["wall_clock_seconds"]) for row in runtime) / 60 * 1.45)
    ax.set_ylim(1, 3240 * 4)
    ax.set_xlabel("waktu terukur (menit)")
    ax.set_ylabel("skenario dievaluasi")
    ax.set_title("(b)  Cakupan", loc="left", fontweight="bold")
    _style(ax)

    ax = axes[2]
    surrogate = np.array([float(row["surrogate_value"]) for row in confirmation]) / 1e6
    mrst = np.array([float(row["mrst_value"]) for row in confirmation]) / 1e6
    low = min(surrogate.min(), mrst.min())
    high = max(surrogate.max(), mrst.max())
    ax.plot([low, high], [low, high], color=INK, lw=1.0)
    ax.scatter(surrogate, mrst, color=COLORS["C"], s=38, edgecolors="white", linewidths=0.5)
    ax.set_xlabel("nilai surrogate (juta USD)")
    ax.set_ylabel("nilai MRST (juta USD)")
    ax.set_title("(c)  Uji MRST", loc="left", fontweight="bold")
    mape = float(np.mean(np.abs(surrogate - mrst) / np.abs(mrst))) * 100
    ax.text(0.96, 0.05, f"MAPE {mape:.1f}%".replace(".", ","), transform=ax.transAxes, fontsize=7.5, ha="right", va="bottom")
    _style(ax)

    fig.text(0.5, 0.02, "Konfirmasi Arm A dan nilai lima rencana terbaik berasal dari MRST; nilai pencarian Arm C dari surrogate.",
             ha="center", fontsize=8.4, color=SUB_INK)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.88, bottom=0.27)
    localize(fig)
    fig.savefig(OUT_DIR / "fig08_abc_economics.pdf")
    fig.savefig(OUT_DIR / "fig08_abc_economics.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT_DIR / "fig08_abc_economics.pdf")


if __name__ == "__main__":
    raise SystemExit(blocked_main(generate))
