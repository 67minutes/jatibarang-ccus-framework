"""Figure 1 — Integrated framework and two-pass data flow.

Renders at true print size (6.3 in = A4 text width at 2.5 cm side margins), so
font point sizes in this script are the sizes the reader sees. Visual system:
warm gold = framework modules, purple ramp = carbon-price scenarios, neutral
gray = inputs/outputs, ink text only (color never carries text).

Output: fig01_framework.pdf (paper) and fig01_framework.png (review).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle
from feature007_common import parser, require_ready

OUT_DIR = Path(__file__).parent

args = parser(1, __doc__).parse_args()
manifest, _ = require_ready(args.bundle, args.figure_number)
screening = manifest["experiment_design"]["screening"]

# ---------------------------------------------------------------- visual system
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
GOLD_EDGE = "#8A6D00"
GOLD_FILL = "#FAF3DF"
GOLD_SHADOW = "#C4B071"
PURPLE_EDGE = "#6C4E9E"
PURPLE_FILL = "#F1EBF8"
PURPLE_RAMP = ["#D9CBEE", "#B79BDB", "#9271C4", "#6C4E9E"]
GRAY_EDGE = "#8C8C8C"
GRAY_FILL = "#F5F5F4"
ARROW = "#3A3A3A"
TEAL = "#2E8F8A"
TEAL_LIGHT = "#BFE3E0"

F_TITLE = 12.0  # module titles
F_SUB = 9.5     # box sublines
F_LBL = 9.5     # arrow labels
F_BADGE = 10.5  # numbered badges

HALO = [pe.withStroke(linewidth=2.6, foreground="white")]

plt.rcParams.update(
    {
        "font.family": "Arial",
        "mathtext.default": "regular",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "text.color": INK,
    }
)

# ------------------------------------------------------------------- canvas
W_IN = 6.3
XMAX, YMAX = 100.0, 84.0
fig = plt.figure(figsize=(W_IN, W_IN * YMAX / XMAX))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, XMAX)
ax.set_ylim(0, YMAX)
ax.set_aspect("equal")
ax.axis("off")

# column x-extents (3 columns) and row y-extents
COL = {"A": (2, 24), "B": (39, 61), "C": (76, 98)}
ROW_TOP = (63, 81)
ROW_MID = (41, 55)
ROW_BOT = (19, 37)
BAR = (3, 13)


# ------------------------------------------------------------------ helpers
def box(x0, x1, y0, y1, edge, fill, lw=1.3, shadow=False, z=3):
    if shadow:
        for off in (2.4, 1.2):
            ax.add_patch(
                FancyBboxPatch(
                    (x0 + off, y0 - off),
                    x1 - x0,
                    y1 - y0,
                    boxstyle="round,pad=0,rounding_size=1.4",
                    fc=fill,
                    ec=GOLD_SHADOW,
                    lw=1.0,
                    zorder=z - 1,
                )
            )
    ax.add_patch(
        FancyBboxPatch(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            boxstyle="round,pad=0,rounding_size=1.4",
            fc=fill,
            ec=edge,
            lw=lw,
            zorder=z,
        )
    )


def badge(x, y, num):
    ax.add_patch(Circle((x, y), 2.0, fc=GOLD_EDGE, ec="white", lw=1.0, zorder=6))
    ax.text(x, y, num, ha="center", va="center", fontsize=F_BADGE,
            fontweight="bold", color="white", zorder=7)


def txt(x, y, s, size=F_SUB, weight="normal", color=INK, ha="center",
        va="center", halo=False, z=5, ls=1.15):
    t = ax.text(x, y, s, ha=ha, va=va, fontsize=size, fontweight=weight,
                color=color, zorder=z, linespacing=ls)
    if halo:
        t.set_path_effects(HALO)
    return t


def arrow(p0, p1, color=ARROW, lw=1.4, style="-", z=4):
    ax.add_patch(
        FancyArrowPatch(
            p0, p1, arrowstyle="-|>", mutation_scale=10, lw=lw, color=color,
            linestyle=style, shrinkA=0, shrinkB=0, zorder=z,
        )
    )


def elbow(points, color=ARROW, lw=1.4, style="-", z=4):
    xs = [p[0] for p in points[:-1]]
    ys = [p[1] for p in points[:-1]]
    ax.plot(xs, ys, color=color, lw=lw, linestyle=style,
            solid_capstyle="round", zorder=z)
    arrow(points[-2], points[-1], color=color, lw=lw, style=style, z=z)


# ------------------------------------------------------------------- glyphs
def glyph_plume(cx, cy):
    """Three tiny frames with a growing teal plume."""
    for i, (dx, r) in enumerate([(-7.2, 0.7), (0.0, 1.15), (7.2, 1.6)]):
        ax.add_patch(Rectangle((cx + dx - 2.6, cy - 2.2), 5.2, 4.4, fc="white",
                               ec=GRAY_EDGE, lw=0.7, zorder=5))
        ax.add_patch(Circle((cx + dx, cy), r, fc=TEAL_LIGHT, ec=TEAL, lw=0.8,
                            zorder=6))
        if i < 2:
            ax.annotate("", (cx + dx + 4.4, cy), (cx + dx + 2.8, cy),
                        arrowprops=dict(arrowstyle="-|>", color=SUB_INK, lw=0.7),
                        zorder=6)


def glyph_route(cx, cy):
    """Terrain patch showing the per-well mode choice: a solid A*-routed
    pipeline trunk and a dashed road-trucking leg, the two supply modes the
    MILP selects between per well."""
    ax.add_patch(Rectangle((cx - 9, cy - 2.2), 18, 4.4, fc="#EDEAE3",
                           ec=GRAY_EDGE, lw=0.7, zorder=5))
    # Solid pipeline trunk with booster/well nodes.
    xs = [cx - 8, cx - 4.5, cx - 1, cx + 3, cx + 8]
    ys = [cy - 1.2, cy + 0.6, cy - 0.5, cy + 1.2, cy + 0.2]
    ax.plot(xs, ys, color=INK, lw=1.1, zorder=6)
    for x, y in [(xs[0], ys[0]), (xs[2], ys[2]), (xs[4], ys[4])]:
        ax.add_patch(Circle((x, y), 0.55, fc=GOLD_EDGE, ec="white", lw=0.5,
                            zorder=7))
    # Dashed road-trucking leg to an off-trunk well (the other mode).
    ax.plot([xs[2], cx + 1.5], [ys[2], cy - 1.7], color=SUB_INK, lw=0.9,
            ls=(0, (2.2, 1.6)), zorder=6)
    ax.add_patch(Rectangle((cx + 1.0, cy - 2.2), 1.4, 1.0, fc="white",
                           ec=SUB_INK, lw=0.7, zorder=7))


def glyph_skid(cx, cy):
    """Separator triangle -> compressor circles -> pump square."""
    ax.plot([cx - 8, cx + 8], [cy, cy], color=SUB_INK, lw=0.8, zorder=5)
    tri_x = [cx - 8, cx - 5.4, cx - 8]
    tri_y = [cy + 1.7, cy, cy - 1.7]
    ax.fill(tri_x, tri_y, fc="white", ec=INK, lw=0.9, zorder=6)
    for dx in (-1.6, 2.2):
        ax.add_patch(Circle((cx + dx, cy), 1.5, fc="white", ec=INK, lw=0.9,
                            zorder=6))
    ax.add_patch(Rectangle((cx + 6.0, cy - 1.4), 2.8, 2.8, fc=GOLD_FILL,
                           ec=INK, lw=0.9, zorder=6))


def glyph_cash(cx, cy):
    """Year-0 CAPEX bar below the line, recurring bars above."""
    ax.plot([cx - 8.5, cx + 8.5], [cy - 0.6, cy - 0.6], color=SUB_INK, lw=0.8,
            zorder=5)
    ax.add_patch(Rectangle((cx - 7.6, cy - 2.6), 2.2, 2.0, fc="#B9B4A8",
                           ec=SUB_INK, lw=0.6, zorder=6))
    for i, h in enumerate([1.2, 1.7, 2.2, 2.6]):
        ax.add_patch(Rectangle((cx - 3.4 + i * 3.0, cy - 0.6), 2.2, h,
                               fc=GOLD_FILL, ec=GOLD_EDGE, lw=0.8, zorder=6))


# ------------------------------------------------------------------- boxes
yt0, yt1 = ROW_TOP
yb0, yb1 = ROW_BOT

# Inputs (top-left, neutral)
x0, x1 = COL["A"]
box(x0, x1, yt0, yt1, GRAY_EDGE, GRAY_FILL)
txt((x0 + x1) / 2, yt1 - 3.2, "Screening inputs", size=F_TITLE, weight="bold")
txt((x0 + x1) / 2, yt0 + 6.6,
    f"{screening['surrogate_training_proxy_geologies']} proxy geologies\n"
    f"{screening['candidate_geologies']} wells · Subang\n"
    f"{screening['schedules_per_geology']}-schedule HnP grid",
    size=F_SUB, color=SUB_INK)

# Module 1 — surrogate (top-middle)
x0, x1 = COL["B"]
box(x0, x1, yt0, yt1, GOLD_EDGE, GOLD_FILL)
badge(x0, yt1, "1")
txt((x0 + x1) / 2, yt1 - 3.2, "Subsurface\nsurrogate", size=F_TITLE,
    weight="bold", va="center", ls=1.0)
txt((x0 + x1) / 2, yt1 - 8.6, "ConvLSTM rollout", size=F_SUB, color=SUB_INK)
glyph_plume((x0 + x1) / 2, yt0 + 4.0)

# Module 4 — economics pass 1 (top-right)
x0, x1 = COL["C"]
box(x0, x1, yt0, yt1, GOLD_EDGE, GOLD_FILL)
badge(x0, yt1, "4")
txt((x0 + x1) / 2, yt1 - 3.2, "Economics", size=F_TITLE, weight="bold")
txt((x0 + x1) / 2, yt1 - 8.0, "pass 1 · flat\ndelivered cost", size=F_SUB,
    color=SUB_INK)
glyph_cash((x0 + x1) / 2, yt0 + 4.2)

# Carbon-price scenarios (middle, purple)
x0, x1 = COL["B"]
ym0, ym1 = ROW_MID
box(x0, x1, ym0, ym1, PURPLE_EDGE, PURPLE_FILL)
txt((x0 + x1) / 2, ym1 - 3.0, "Carbon-price\nscenarios", size=F_TITLE,
    weight="bold", ls=1.0)
chip_y = ym0 + 3.6
chip_w = 3.4
gap = (x1 - x0 - 4 * chip_w - 4) / 3
cx = x0 + 2
for i, c in enumerate(PURPLE_RAMP):
    ax.add_patch(Rectangle((cx, chip_y), chip_w, 2.6, fc=c, ec=PURPLE_EDGE,
                           lw=0.6, zorder=6))
    cx += chip_w + gap
txt(x0 + 2 + chip_w / 2, chip_y - 2.0, "IDX", size=F_LBL, color=SUB_INK)
txt(x1 - 2 - chip_w / 2, chip_y - 2.0, "JCM", size=F_LBL, color=SUB_INK)

# Module 2 — logistics mode-choice MILP (bottom-right, stacked per price)
x0, x1 = COL["C"]
box(x0, x1, yb0, yb1, GOLD_EDGE, GOLD_FILL, shadow=True)
badge(x0, yb1, "2")
txt((x0 + x1) / 2, yb1 - 3.2, "Logistics MILP", size=F_TITLE, weight="bold")
txt((x0 + x1) / 2, yb1 - 8.0, "pipe vs. truck\nA* routes · CBC",
    size=F_SUB, color=SUB_INK)
glyph_route((x0 + x1) / 2, yb0 + 4.0)

# Module 3 — facilities (bottom-middle)
x0, x1 = COL["B"]
box(x0, x1, yb0, yb1, GOLD_EDGE, GOLD_FILL)
badge(x0, yb1, "3")
txt((x0 + x1) / 2, yb1 - 3.2, "Facility sizing", size=F_TITLE, weight="bold")
txt((x0 + x1) / 2, yb1 - 8.0, "CoolProp skids\nDWSIM-calibrated", size=F_SUB,
    color=SUB_INK)
glyph_skid((x0 + x1) / 2, yb0 + 4.0)

# Module 4 — economics pass 2 (bottom-left)
x0, x1 = COL["A"]
box(x0, x1, yb0, yb1, GOLD_EDGE, GOLD_FILL)
badge(x0, yb1, "4")
txt((x0 + x1) / 2, yb1 - 3.2, "Economics", size=F_TITLE, weight="bold")
txt((x0 + x1) / 2, yb1 - 8.0, "pass 2 · raw costs\n+ uncertainty",
    size=F_SUB, color=SUB_INK)
glyph_cash((x0 + x1) / 2, yb0 + 4.2)

# Outputs bar (bottom, neutral, three cells)
box(2, 98, BAR[0], BAR[1], GRAY_EDGE, GRAY_FILL)
for xr in (34, 66):
    ax.plot([xr, xr], [BAR[0] + 1.2, BAR[1] - 1.2], color="#CFCFCC", lw=0.9,
            zorder=5)
by = (BAR[0] + BAR[1]) / 2
txt(18, by, "Ranked plans\nNPV · IRR per price\n× fiscal case",
    size=F_LBL, color=INK, ls=1.05)
txt(50, by, "Audits\nselection discrepancy\nplume interference",
    size=F_LBL, color=INK, ls=1.05)
txt(82, by, "Top-K shortlist\n→ MRST / DWSIM\nconfirmation",
    size=F_LBL, color=INK, ls=1.05)

# ------------------------------------------------------------------- arrows
ymid_top = (yt0 + yt1) / 2  # 72
ymid_bot = (yb0 + yb1) / 2  # 28

# Inputs -> M1
arrow((COL["A"][1], ymid_top), (COL["B"][0], ymid_top))
txt((COL["A"][1] + COL["B"][0]) / 2, ymid_top + 3.4,
    "warm seeds\n+ schedules", size=F_LBL, color=SUB_INK, halo=True)

# M1 -> pass-1 economics
arrow((COL["B"][1], ymid_top), (COL["C"][0], ymid_top))
txt((COL["B"][1] + COL["C"][0]) / 2, ymid_top + 4.4,
    "Δoil · Δgas\nCO$_2$ inventory\nflags", size=F_LBL,
    color=SUB_INK, halo=True)

# pass 1 -> M2 (vertical, right side)
elbow([(90, yt0), (90, yb1)])
txt(88.5, 52.5, "preliminary\nwell value", size=F_LBL, color=SUB_INK,
    ha="right", halo=True)

# carbon price -> M2 selection objective (bold purple)
elbow([(COL["B"][1], 48), (80, 48), (80, yb1)], color=PURPLE_EDGE, lw=2.2)
txt(78.5, 44.4, "selection\nobjective", size=F_LBL, color=PURPLE_EDGE,
    weight="bold", ha="right", halo=True)

# carbon price -> pass-2 economics revenue scenarios (thin purple)
elbow([(COL["B"][0], 48), (13, 48), (13, yb1)], color=PURPLE_EDGE, lw=1.2)
txt(26, 50.6, "revenue scenarios", size=F_LBL, color=PURPLE_EDGE, halo=True)

# M2 -> M3
arrow((COL["C"][0], ymid_bot), (COL["B"][1], ymid_bot))
txt((COL["C"][0] + COL["B"][1]) / 2, ymid_bot + 4.4,
    "selected wells\ndelivery P\npeak flow", size=F_LBL, color=SUB_INK,
    halo=True)

# M3 -> pass 2
arrow((COL["B"][0], ymid_bot), (COL["A"][1], ymid_bot))
txt((COL["B"][0] + COL["A"][1]) / 2, ymid_bot + 3.4,
    "facility costs\n& losses", size=F_LBL, color=SUB_INK, halo=True)

# M2 -> pass 2 bypass: raw pipeline & trucking costs (below bottom row)
elbow([(87, yb0), (87, 16), (18, 16), (18, yb0)])
txt(52.5, 17.3, "raw pipeline & trucking costs", size=F_LBL, color=SUB_INK,
    halo=True)

# pass 2 -> outputs bar
arrow((8, yb0), (8, BAR[1]))

fig.savefig(OUT_DIR / "fig01_framework.pdf")
fig.savefig(OUT_DIR / "fig01_framework.png", dpi=300)
print("wrote", OUT_DIR / "fig01_framework.pdf")
