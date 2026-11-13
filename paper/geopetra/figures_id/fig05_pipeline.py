"""Figure 5 - logistics mode choice across scale (reframed 2026-07-19).

Three panels under one argument: the supply-mode answer is throughput-dependent,
and the same optimizer produces both the pilot-scale trucking selection and the
commercial-scale trunk design.

  (a) Pilot-scale terrain result: A*-routed candidate corridors, the optimizer's
      hydraulic rejection audit (`below_minimum_hydraulic_flow`, six diameters
      evaluated), and the selected road-trucking supply legs. The honest
      pilot-scale "network" is the trucked one.  [Arm C pilot result]
  (b) Commercial-scale design at the sweep's upper branch: the A*-routed trunk
      the MILP builds once aggregated demand clears the admissibility floor, with
      its continuous CoolProp pressure profile (dense-phase floor, MAOP, booster
      lifts). Labeled a scale-sweep design point, not the pilot development.
      [commercial-scale MILP result]
  (c) Delivered cost vs annual throughput (log-log, 10 kt/yr -> 1 Mt/yr): three
      modes -- trucking, direct pipeline, hybrid trunk+truck -- each with a
      low/base/high band and hydraulic admissibility marked. Pilot scale
      (~30 kt/yr) and the hybrid admissibility takeover annotated.
      [screening cost proxy -- real now]

Panels (a) and (b) consume the final Arm C route/pressure tables and stay blocked
until those land; panel (c) reads the real three-mode crossover already staged.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from feature007_common import localize
import numpy as np

from feature007_common import FigureBlockedError, blocked_main, load_table, parser, require_ready


OUT_DIR = Path(__file__).parent
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
GOLD = "#8A6D00"
BLUE = "#3E6FA8"
RED = "#B0413E"

# Panel (c) mode styling: (legend label, color).
MODE_STYLE = {
    "trucking": ("truk", BLUE),
    "pipeline_direct": ("pipa langsung", GOLD),
    "hybrid_trunk_truck": ("hibrida trunk+truk", RED),
}


def _values(rows, name: str) -> np.ndarray:
    try:
        return np.array([float(row[name]) for row in rows])
    except KeyError as exc:
        raise ValueError(f"pipeline table lacks required column {name}") from exc


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


def _panel_pilot(ax, route) -> None:
    """(a) Pilot terrain map: candidate corridors + rejected wells + trucked legs.

    Expected columns on the `pipeline_route_final` table (Arm C pilot result):
    route_id, point_order, longitude, latitude, node_type in
    {source, well, junction, booster}, and mode in {pipeline, trucking} on the
    supply legs (defaults to pipeline when the column is absent). Rejected
    candidates carry selected=false with reason=below_minimum_hydraulic_flow.
    """
    ordered = sorted(route, key=lambda row: (row.get("route_id", ""), float(row["point_order"])))
    groups: dict[str, list] = {}
    for row in ordered:
        groups.setdefault(row.get("route_id", "selected"), []).append(row)
    for group in groups.values():
        mode = group[0].get("mode", "pipeline")
        lon = _values(group, "longitude")
        lat = _values(group, "latitude")
        if mode == "trucking":
            ax.plot(lon, lat, color=BLUE, lw=1.3, ls=(0, (2.4, 1.6)), zorder=2)
        else:
            ax.plot(lon, lat, color=INK, lw=1.4, zorder=2)
    colors = {"source": BLUE, "well": GOLD, "booster": RED, "junction": "#B8B4AC"}
    for row in ordered:
        node_type = row.get("node_type")
        if node_type not in colors:
            continue
        selected = row.get("selected")
        rejected = selected is not None and not _truthy(selected)
        ax.scatter(
            float(row["longitude"]), float(row["latitude"]),
            s=26 if node_type != "junction" else 10,
            facecolor="white" if rejected else colors[node_type],
            edgecolor=colors[node_type], lw=1.0, zorder=3,
        )
    ax.set_xlabel("bujur")
    ax.set_ylabel("lintang")
    ax.set_title("(a)  Pilot: pasokan truk", loc="left",
                 fontweight="bold", fontsize=9.5)
    _style(ax)


def _panel_pressure(ax, pressure) -> None:
    """(b) Commercial-scale trunk continuous pressure with floor and MAOP.

    Expected columns on `pipeline_pressure_final`: distance_km, pressure_bar,
    dense_phase_floor_bar, maop_bar.
    """
    distance = _values(pressure, "distance_km")
    p_bar = _values(pressure, "pressure_bar")
    floor = _values(pressure, "dense_phase_floor_bar")
    maop = _values(pressure, "maop_bar")
    ax.plot(distance, p_bar, color=GOLD, lw=1.8, label="pressure")
    ax.plot(distance, floor, color=RED, lw=1.0, ls="--", label="dense floor")
    ax.plot(distance, maop, color=SUB_INK, lw=0.9, ls=":", label="MAOP")
    ax.set_xlabel("jarak trunk (km)")
    ax.set_ylabel("tekanan (bar)")
    ax.set_title("(b)  Trunk komersial", loc="left", fontweight="bold",
                 fontsize=9.5)
    ax.legend(frameon=False, fontsize=7.5, loc="lower left")
    _style(ax)


def _panel_crossover(ax, crossover) -> None:
    """(c) Three-mode delivered-cost crossover with low/base/high bands.

    Columns: cost_case in {low, base, high}, annual_tonnes, mode,
    levelized_usd_per_tonne, hydraulically_admissible.
    """
    series: dict[tuple[str, str], list[tuple[float, float, bool]]] = {}
    for row in crossover:
        key = (row["mode"], row.get("cost_case", "base"))
        series.setdefault(key, []).append((
            float(row["annual_tonnes"]),
            float(row["levelized_usd_per_tonne"]),
            _truthy(row.get("hydraulically_admissible", "true")),
        ))
    for points in series.values():
        points.sort()

    for mode, (label, color) in MODE_STYLE.items():
        base = series.get((mode, "base"))
        if not base:
            continue
        x = np.array([t for t, _, _ in base])
        y = np.array([c for _, c, _ in base])
        admissible = np.array([a for _, _, a in base])
        low = series.get((mode, "low"))
        high = series.get((mode, "high"))
        if low and high:
            ax.fill_between(
                x,
                [c for _, c, _ in low],
                [c for _, c, _ in high],
                color=color, alpha=0.13, lw=0,
            )
        # Faint line over the full range; bold solid only where admissible.
        ax.plot(x, y, color=color, lw=1.5, alpha=0.45, label=label)
        if admissible.any():
            ax.plot(x, np.where(admissible, y, np.nan), color=color, lw=2.6)
            onset = int(np.argmax(admissible))
            ax.scatter([x[onset]], [y[onset]], s=30, color=color, zorder=6,
                       edgecolor="white", lw=0.9)
            # Annotate only the hybrid admissibility takeover, placed inward so
            # it never clips the panel edge.
            if mode == "hybrid_trunk_truck":
                ax.annotate(
                    "hibrida\nlayak", (x[onset], y[onset]),
                    textcoords="offset points", xytext=(-6, 10), ha="right",
                    fontsize=6.8, color=color, linespacing=0.95,
                )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.axvline(30_000.0, color=SUB_INK, lw=0.9, ls=":")
    ax.annotate("pilot\n~30 kt/thn", (30_000.0, ax.get_ylim()[1]),
                textcoords="offset points", xytext=(3, -16), fontsize=6.8,
                color=SUB_INK)
    ax.set_xlabel("CO$_2$ tahunan (t/tahun)")
    ax.set_ylabel("biaya kirim (USD/t)")
    ax.set_title("(c)  Persilangan biaya", loc="left", fontweight="bold",
                 fontsize=9.5)
    ax.legend(frameon=False, fontsize=6.8, loc="upper right", handlelength=1.4)
    _style(ax)


def generate() -> None:
    args = parser(5, __doc__).parse_args()
    manifest, _ = require_ready(args.bundle, args.figure_number)
    route = load_table(args.bundle, manifest, "pipeline_route_final")
    try:
        pressure = load_table(args.bundle, manifest, "pipeline_pressure_final")
    except FigureBlockedError:
        pressure = None
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
    if pressure is None:
        fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.75), gridspec_kw={"wspace": 0.38})
        _panel_pilot(axes[0], route)
        _panel_crossover(axes[1], crossover)
        axes[1].set_title("(b)  Persilangan biaya", loc="left", fontweight="bold", fontsize=9.5)
    else:
        fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.75), gridspec_kw={"wspace": 0.48})
        _panel_pilot(axes[0], route)
        _panel_pressure(axes[1], pressure)
        _panel_crossover(axes[2], crossover)

    fig.text(0.5, 0.02,
             "Garis tebal = layak secara hidraulika. Seleksi pilot: MILP Arm C; "
             "hidraulika: CoolProp; biaya: proksi penapisan.",
             ha="center", fontsize=8.0, color=SUB_INK)
    fig.subplots_adjust(left=0.11, right=0.985, top=0.88, bottom=0.25)
    localize(fig)
    fig.savefig(OUT_DIR / "fig05_pipeline.pdf")
    fig.savefig(OUT_DIR / "fig05_pipeline.png", dpi=300)
    plt.close(fig)
    print("wrote", OUT_DIR / "fig05_pipeline.pdf")


if __name__ == "__main__":
    raise SystemExit(blocked_main(generate))
