"""Figure 6 - real DWSIM parity and facility screening-cost curve."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from feature007_common import blocked_main, load_table, parser, require_ready


OUT_DIR = Path(__file__).parent
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
GOLD = "#8A6D00"
GOLD_LIGHT = "#E3D39A"
GRAY = "#8C8C8C"


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=3, colors=SUB_INK)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


def generate() -> None:
    args = parser(6, __doc__).parse_args()
    manifest, _ = require_ready(args.bundle, args.figure_number)
    parity = load_table(args.bundle, manifest, "facility_validation")
    curve = load_table(args.bundle, manifest, "facility_cost_curve")

    dwsim = np.array([float(row["dwsim_total_power_kw"]) for row in parity])
    runtime = np.array([float(row["runtime_total_power_kw"]) for row in parity])
    errors = np.array([float(row["total_absolute_percentage_error"]) for row in parity])
    flow = np.array([float(row["injection_rate_std_m3_day"]) for row in curve])
    capex = np.array([float(row["capex_usd"]) / 1e3 for row in curve])
    opex = np.array([float(row["annual_opex_usd"]) / 1e3 for row in curve])

    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 9.5,
            "axes.labelsize": 9.5,
            "axes.titlesize": 12.0,
            "legend.fontsize": 9.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "text.color": INK,
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.9), gridspec_kw={"wspace": 0.42})

    ax = axes[0]
    low = min(dwsim.min(), runtime.min()) * 0.94
    high = max(dwsim.max(), runtime.max()) * 1.04
    ax.plot([low, high], [low, high], color="black", lw=1.2, label="1:1")
    ax.scatter(dwsim, runtime, s=38, c=GOLD, edgecolors="white", linewidths=0.6, zorder=3)
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("DWSIM total power (kW)")
    ax.set_ylabel("runtime correlation (kW)")
    ax.set_title("(a)  DWSIM parity", loc="left", fontweight="bold")
    ax.text(0.04, 0.94, f"8/8 converged\nmax error {errors.max():.5f}%",
            transform=ax.transAxes, va="top", color=SUB_INK)
    _style(ax)

    ax = axes[1]
    ax.plot(flow, capex, color=GOLD, lw=2.0, marker="o", ms=4, label="CAPEX")
    ax.fill_between(flow, capex, color=GOLD_LIGHT, alpha=0.28)
    ax.set_xlabel(r"injection rate (std m$^3$/day)")
    ax.set_ylabel("CAPEX (thousand USD)", color=GOLD)
    ax.tick_params(axis="y", labelcolor=GOLD)
    ax.set_title("(b)  Screening cost curve", loc="left", fontweight="bold")
    _style(ax)
    twin = ax.twinx()
    twin.plot(flow, opex, color=GRAY, lw=1.6, ls="--", marker="s", ms=3.5, label="annual OPEX")
    twin.set_ylabel("annual OPEX (thousand USD)", color=SUB_INK)
    twin.tick_params(axis="y", colors=SUB_INK, length=3)
    twin.spines["top"].set_visible(False)

    fig.text(
        0.5,
        0.015,
        "DWSIM: pinned offline truth; runtime: CoolProp correlation; costs: screening proxy, not FEED.",
        ha="center",
        fontsize=8.5,
        color=SUB_INK,
    )
    fig.subplots_adjust(left=0.095, right=0.91, top=0.88, bottom=0.24)
    fig.savefig(OUT_DIR / "fig06_facility.pdf")
    fig.savefig(OUT_DIR / "fig06_facility.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT_DIR / "fig06_facility.pdf")


if __name__ == "__main__":
    raise SystemExit(blocked_main(generate))
