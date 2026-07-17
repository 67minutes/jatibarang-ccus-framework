"""Figure 5 - real Arm C network, continuous pressure, and cost crossover."""

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
BLUE = "#3E6FA8"
RED = "#B0413E"


def _values(rows, name: str) -> np.ndarray:
    try:
        return np.array([float(row[name]) for row in rows])
    except KeyError as exc:
        raise ValueError(f"pipeline table lacks required column {name}") from exc


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


def generate() -> None:
    args = parser(5, __doc__).parse_args()
    manifest, _ = require_ready(args.bundle, args.figure_number)
    route = load_table(args.bundle, manifest, "pipeline_route_final")
    pressure = load_table(args.bundle, manifest, "pipeline_pressure_final")
    crossover = load_table(args.bundle, manifest, "pipeline_cost_crossover_final")

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
    fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.75), gridspec_kw={"wspace": 0.48})

    ax = axes[0]
    ordered = sorted(route, key=lambda row: (row.get("route_id", ""), float(row["point_order"])))
    groups = {}
    for row in ordered:
        groups.setdefault(row.get("route_id", "selected"), []).append(row)
    for route_id, group in groups.items():
        ax.plot(_values(group, "longitude"), _values(group, "latitude"), color=INK, lw=1.4)
    endpoint_rows = [row for row in ordered if row.get("node_type") in {"source", "well", "booster"}]
    colors = {"source": BLUE, "well": GOLD, "booster": RED}
    for row in endpoint_rows:
        ax.scatter(float(row["longitude"]), float(row["latitude"]), s=25,
                   color=colors[row["node_type"]], zorder=3)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title("(a)  Selected route", loc="left", fontweight="bold")
    _style(ax)

    ax = axes[1]
    distance = _values(pressure, "distance_km")
    p_bar = _values(pressure, "pressure_bar")
    floor = _values(pressure, "dense_phase_floor_bar")
    maop = _values(pressure, "maop_bar")
    ax.plot(distance, p_bar, color=GOLD, lw=1.8, label="pressure")
    ax.plot(distance, floor, color=RED, lw=1.0, ls="--", label="dense floor")
    ax.plot(distance, maop, color=SUB_INK, lw=0.9, ls=":", label="MAOP")
    ax.set_xlabel("route distance (km)")
    ax.set_ylabel("pressure (bar)")
    ax.set_title("(b)  Pressure audit", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7.5)
    _style(ax)

    ax = axes[2]
    throughput = _values(crossover, "annual_tonnes")
    pipeline = _values(crossover, "pipeline_usd_per_tonne")
    trucking = _values(crossover, "trucking_usd_per_tonne")
    order = np.argsort(throughput)
    ax.plot(throughput[order], pipeline[order], color=GOLD, lw=1.8, label="pipeline")
    ax.plot(throughput[order], trucking[order], color=BLUE, lw=1.5, ls="--", label="trucking")
    ax.set_xscale("log")
    ax.set_xlabel("annual CO$_2$ (t/y)")
    ax.set_ylabel("delivered cost (USD/t)")
    ax.set_title("(c)  Cost crossover", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7.5)
    _style(ax)

    fig.text(0.5, 0.02, "Route and portfolio: Arm C MILP; hydraulics: CoolProp; costs: screening proxy.",
             ha="center", fontsize=8.4, color=SUB_INK)
    fig.subplots_adjust(left=0.085, right=0.98, top=0.88, bottom=0.25)
    fig.savefig(OUT_DIR / "fig05_pipeline.pdf")
    fig.savefig(OUT_DIR / "fig05_pipeline.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT_DIR / "fig05_pipeline.pdf")


if __name__ == "__main__":
    raise SystemExit(blocked_main(generate))
