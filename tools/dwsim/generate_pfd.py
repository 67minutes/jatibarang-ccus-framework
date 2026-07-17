from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def _box(ax, x: float, y: float, width: float, height: float, label: str, color: str) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.03",
            facecolor=color,
            edgecolor="#233142",
            linewidth=1.2,
        )
    )
    ax.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=8.5)


def _arrow(ax, start: tuple[float, float], end: tuple[float, float], label: str = "") -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=1.2,
            color="#233142",
        )
    )
    if label:
        ax.text(
            (start[0] + end[0]) / 2,
            (start[1] + end[1]) / 2 + 0.04,
            label,
            ha="center",
            va="bottom",
            fontsize=7.5,
            color="#334155",
        )


def generate(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(13.2, 5.5), constrained_layout=True)
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 5.4)
    ax.axis("off")

    process = "#dbeafe"
    rotating = "#dcfce7"
    cooling = "#fef3c7"
    boundary = "#f1f5f9"

    _box(ax, 0.25, 3.45, 1.25, 0.65, "Produced-fluid\nboundary", boundary)
    _box(ax, 1.85, 3.45, 1.15, 0.65, "SEP-01\n3-phase separator", process)
    _box(ax, 3.35, 3.45, 1.05, 0.65, "DEHY-01\nboundary", process)
    _arrow(ax, (1.5, 3.78), (1.85, 3.78))
    _arrow(ax, (3.0, 3.78), (3.35, 3.78), "recovered CO2")

    x = 4.75
    for stage in range(1, 4):
        _box(ax, x, 3.45, 1.0, 0.65, f"COMP-0{stage}\nstage {stage}", rotating)
        _arrow(ax, (x - 0.35, 3.78), (x, 3.78))
        _box(ax, x + 1.25, 3.45, 1.0, 0.65, f"COOL-0{stage}\n" + ("27 °C final" if stage == 3 else "35 °C"), cooling)
        _arrow(ax, (x + 1.0, 3.78), (x + 1.25, 3.78))
        x += 2.6

    _box(ax, 8.25, 1.15, 1.25, 0.65, "Feature 002\nfresh dense CO2", boundary)
    _box(ax, 10.05, 1.15, 1.05, 0.65, "MIX-01", process)
    _box(ax, 11.55, 1.15, 1.05, 0.65, "PUMP-01", rotating)
    _arrow(ax, (9.5, 1.48), (10.05, 1.48), "fresh")
    _arrow(ax, (11.1, 1.48), (11.55, 1.48))
    _arrow(ax, (12.6, 1.48), (13.05, 1.48), "wellhead")
    _arrow(ax, (12.55, 3.45), (10.58, 1.82), "dense recycle")

    _arrow(ax, (2.45, 3.45), (2.45, 2.7), "oil + water")
    ax.text(2.45, 2.52, "separate handling boundary", ha="center", va="top", fontsize=7.5, color="#334155")
    ax.text(0.25, 4.75, "Feature 003 DWSIM validation flowsheet", fontsize=15, weight="bold", color="#0f172a")
    ax.text(
        0.25,
        4.38,
        "CoolProp property package • recycle-only compression • final dense-phase cooling • combined-stream wellhead pumping",
        fontsize=9.5,
        color="#334155",
    )
    ax.text(
        0.25,
        0.25,
        "DWSIM validates thermodynamic duties and mass balance. Screening equipment costs and separator vessel sizing are applied in Python from tracked correlations.",
        fontsize=8.2,
        color="#475569",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Feature 003 process-flow diagram.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
