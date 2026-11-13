"""Figure 7 - carbon-price ranking pivot, regret, and NPV curves."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from feature007_common import blocked_main, load_table, parser, require_ready


OUT_DIR = Path(__file__).parent
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
PURPLES = ["#D9CBEE", "#B79BDB", "#9271C4", "#6C4E9E"]
GOLD = "#8A6D00"

# Compact display labels for the regret-matrix ticks so long scenario ids do not
# bleed across panels; unknown ids fall back to themselves.
PRICE_SHORT = {
    "current_idx": "IDX",
    "domestic_maturing": "$20",
    "article6_jcm": "JCM",
    "aspirational": "$50",
}


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


def generate() -> None:
    args = parser(7, __doc__).parse_args()
    manifest, _ = require_ready(args.bundle, args.figure_number)
    rankings = load_table(args.bundle, manifest, "carbon_price_rankings")
    regret = load_table(args.bundle, manifest, "carbon_price_regret")
    curves = load_table(args.bundle, manifest, "npv_vs_carbon_price")

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
    fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.85), gridspec_kw={"wspace": 0.62})

    ax = axes[0]
    plans = sorted({row["scenario_id"] for row in rankings})
    prices = sorted({float(row["carbon_price_usd_per_tonne"]) for row in rankings})
    for index, plan in enumerate(plans):
        rows = sorted(
            (row for row in rankings if row["scenario_id"] == plan),
            key=lambda row: float(row["carbon_price_usd_per_tonne"]),
        )
        x_rank = np.array([
            float(row["carbon_price_usd_per_tonne"]) for row in rows
        ])
        ranks = np.array([float(row["rank"]) for row in rows])
        rank_low = np.array([
            float(row["independent_rank_p10"]) for row in rows
        ])
        rank_high = np.array([
            float(row["independent_rank_p90"]) for row in rows
        ])
        correlated_rank = np.array([
            float(row["correlated_rank"]) for row in rows
        ])
        color = PURPLES[index % len(PURPLES)]
        ax.fill_between(
            x_rank,
            rank_low,
            rank_high,
            color=color,
            alpha=0.10,
            lw=0,
        )
        ax.plot(x_rank, ranks, lw=1.35, color=color)
        ax.plot(
            x_rank,
            correlated_rank,
            lw=0.9,
            ls="--",
            alpha=0.9,
            color=color,
        )
    ax.invert_yaxis()
    ax.set_xlabel("carbon price (USD/t)")
    ax.set_ylabel("rank (1 = best)")
    ax.set_title("(a)  Policy pivot", loc="left", fontweight="bold")
    _style(ax)

    ax = axes[1]
    chosen = sorted({row["chosen_price_scenario"] for row in regret})
    realised = sorted({row["realized_price_scenario"] for row in regret})
    matrix = np.full((len(realised), len(chosen)), np.nan)
    for row in regret:
        matrix[realised.index(row["realized_price_scenario"]), chosen.index(row["chosen_price_scenario"])] = (
            float(row["regret_usd"]) / 1e6
        )
    image = ax.imshow(matrix, cmap="Purples", origin="lower", aspect="auto")
    ax.set_xticks(range(len(chosen)), [PRICE_SHORT.get(c, c) for c in chosen],
                  rotation=0, fontsize=7.5)
    ax.set_yticks(range(len(realised)), [PRICE_SHORT.get(r, r) for r in realised],
                  fontsize=7.5)
    ax.set_xlabel("plan chosen at")
    ax.set_ylabel("price realized")
    ax.set_title("(b)  Regret (MUSD)", loc="left", fontweight="bold")
    fig.colorbar(image, ax=ax, pad=0.02)

    ax = axes[2]
    curve_plans = sorted({row["scenario_id"] for row in curves})
    for index, plan in enumerate(curve_plans):
        rows = sorted((row for row in curves if row["scenario_id"] == plan),
                      key=lambda row: float(row["carbon_price_usd_per_tonne"]))
        x = np.array([float(row["carbon_price_usd_per_tonne"]) for row in rows])
        mean = np.array([float(row["npv_usd"]) / 1e6 for row in rows])
        low = np.array([float(row["npv_low_usd"]) / 1e6 for row in rows])
        high = np.array([float(row["npv_high_usd"]) / 1e6 for row in rows])
        correlated = np.array([
            (
                float(row["correlated_npv_usd"]) / 1e6
                if row.get("correlated_npv_usd", "") not in {"", None}
                else np.nan
            )
            for row in rows
        ])
        color = PURPLES[index % len(PURPLES)]
        label = plan.removeprefix("chosen:")
        ax.fill_between(x, low, high, color=color, alpha=0.12, lw=0)
        ax.plot(x, mean, color=color, lw=1.6, label=label)
        if np.isfinite(correlated).any():
            ax.plot(x, correlated, color=color, lw=1.0, ls="--", alpha=0.9)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xlabel("carbon price (USD/t)")
    ax.set_ylabel("NPV (MUSD)")
    ax.set_title("(c)  NPV curves", loc="left", fontweight="bold")
    ax.legend(
        title="chosen price",
        frameon=False,
        fontsize=6.4,
        title_fontsize=6.4,
        loc="lower left",
    )
    _style(ax)

    fig.text(0.5, 0.02,
             "Arm C: solid = independent mean; band = independent p10–p90; "
             "dashed = correlated-limit median.",
             ha="center", fontsize=8.4, color=SUB_INK)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.2)
    fig.savefig(OUT_DIR / "fig07_carbon_price_pivot.pdf")
    fig.savefig(OUT_DIR / "fig07_carbon_price_pivot.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT_DIR / "fig07_carbon_price_pivot.pdf")


if __name__ == "__main__":
    raise SystemExit(blocked_main(generate))
