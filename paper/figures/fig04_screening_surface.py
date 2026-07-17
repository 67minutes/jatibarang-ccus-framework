"""Figure 4 - real surrogate screening surface and Arm A reference."""

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
TEAL = "#2E8F8A"


def _float(rows, name: str) -> np.ndarray:
    try:
        return np.array([float(row[name]) for row in rows])
    except KeyError as exc:
        raise ValueError(f"screening_surface.csv lacks required column {name}") from exc


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


def generate() -> None:
    args = parser(4, __doc__).parse_args()
    manifest, _ = require_ready(args.bundle, args.figure_number)
    rows = load_table(args.bundle, manifest, "screening_surface")
    permeability = _float(rows, "mean_permeability_md")
    injection = _float(rows, "injection_rate_m3_day")
    oil = _float(rows, "incremental_oil_m3")
    retention = _float(rows, "co2_retention_fraction")
    cycles = _float(rows, "cycles")

    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 9.5,
            "axes.titlesize": 12.0,
            "axes.labelsize": 9.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "text.color": INK,
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 3.05), gridspec_kw={"wspace": 0.34})
    panels = [
        (axes[0], oil, "incremental oil (m$^3$)", "viridis"),
        (axes[1], retention, "CO$_2$ retention fraction", "YlGnBu"),
    ]
    for index, (ax, values, label, cmap) in enumerate(panels):
        scatter = ax.scatter(
            permeability,
            injection,
            c=values,
            cmap=cmap,
            s=20,
            alpha=0.78,
            linewidths=0,
            rasterized=True,
        )
        ax.set_xscale("log")
        ax.set_xlabel("mean effective permeability (mD)")
        ax.set_ylabel(r"injection rate (m$^3$/day)")
        ax.set_title(
            f"({'ab'[index]})  {'Oil response' if index == 0 else 'CO$_2$ retention'}",
            loc="left",
            fontweight="bold",
        )
        cb = fig.colorbar(scatter, ax=ax, pad=0.02)
        cb.set_label(label)
        # Arm A is a schedule reference, not a claimed result at a fabricated geology.
        ax.axhline(9000, color=GOLD, lw=1.2, ls="--")
        ax.text(0.98, 0.04, "Arm A rate", transform=ax.transAxes, ha="right", color=GOLD)
        _style(ax)

    inset = axes[0].inset_axes([0.08, 0.58, 0.36, 0.30])
    for cycle in sorted(set(cycles)):
        mask = cycles == cycle
        inset.scatter(cycle, np.median(oil[mask]), color=TEAL, s=22)
    inset.plot(sorted(set(cycles)), [np.median(oil[cycles == c]) for c in sorted(set(cycles))],
               color=TEAL, lw=1.0)
    inset.set_xlabel("cycles", fontsize=7.5)
    inset.set_ylabel("median oil", fontsize=7.5)
    inset.tick_params(labelsize=7.0, length=2)
    inset.spines[["top", "right"]].set_visible(False)

    fig.text(
        0.5,
        0.018,
        "All points are frozen-checkpoint surrogate predictions; Arm A line marks the fixed-rate reference.",
        ha="center",
        fontsize=8.4,
        color=SUB_INK,
    )
    fig.subplots_adjust(left=0.09, right=0.96, top=0.89, bottom=0.23)
    fig.savefig(OUT_DIR / "fig04_screening_surface.pdf")
    fig.savefig(OUT_DIR / "fig04_screening_surface.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT_DIR / "fig04_screening_surface.pdf")


if __name__ == "__main__":
    raise SystemExit(blocked_main(generate))
