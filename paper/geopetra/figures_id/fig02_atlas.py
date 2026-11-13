"""Figure 2 — Case-study atlas.

Four panels, all from the selected hash-verified Feature 007 bundle (no
synthetic placeholders):
  (a) SRTM 30 m terrain over the Subang -> Jatibarang corridor with the CO2
      source, the 20 candidate wells, and the routing exclusion features
      (data/terrain + data/jatibarang/pipeline_exclusions.geojson).
  (b) Three proxy-geology permeability realizations chosen by a declared
      rule: min / median / max mean log-permeability of the five curated
      MRST validation cases (data/validation_cases/*.mat). Shared log scale.
  (c) The HnP operating grid actually screened (case_study_assumptions.json):
      3 x 3 x 3 x 3 x 2 = 162 schedules per well.
  (d) The four Indonesian carbon-price scenarios (economic_basis.json),
      distinguishing the observed IDX price from labeled assumptions.

Renders at true print size (6.3 in wide); 12 pt panel titles, >= 9.5 pt text.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from feature007_common import localize
import numpy as np
from matplotlib.colors import LightSource, LinearSegmentedColormap, Normalize
from matplotlib.patches import FancyBboxPatch, Polygon as MplPolygon, Rectangle
from feature007_common import FigureBlockedError, parser, require_ready

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).parent

# ---------------------------------------------------------------- visual system
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
GOLD_EDGE = "#8A6D00"
GOLD_FILL = "#FAF3DF"
PURPLE_EDGE = "#6C4E9E"
PURPLE_RAMP = ["#D9CBEE", "#B79BDB", "#9271C4", "#5E4488"]
GRAY_EDGE = "#8C8C8C"
TEAL = "#2E8F8A"
TEAL_FILL = "#BFE3E0"
RIVER = "#4C7699"

F_TITLE = 12.0
F_SUB = 9.5

HALO = [pe.withStroke(linewidth=2.4, foreground="white")]

TERRAIN_CMAP = LinearSegmentedColormap.from_list(
    "muted_earth", ["#F2EFE6", "#E4DCC4", "#CBBD97", "#A18C63", "#6E5B3E"]
)
PERM_CMAP = LinearSegmentedColormap.from_list(
    "perm_brown", ["#F7F1E3", "#E2CFA4", "#C3A166", "#8F6D33", "#5C4114"]
)

plt.rcParams.update(
    {
        "font.family": "Arial",
        "mathtext.default": "regular",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "text.color": INK,
        "axes.edgecolor": GRAY_EDGE,
        "axes.linewidth": 0.8,
        "xtick.color": SUB_INK,
        "ytick.color": SUB_INK,
        "xtick.labelsize": F_SUB,
        "ytick.labelsize": F_SUB,
    }
)

# ----------------------------------------------------------- canonical bundle data
args = parser(2, __doc__).parse_args()
manifest, _ = require_ready(args.bundle, args.figure_number)
record = manifest.get("figure_data", {}).get("2")
if not record or not record.get("available"):
    raise FigureBlockedError("Figure 2 canonical atlas payload is unavailable")
payload_path = args.bundle / record["path"]
payload = json.loads(payload_path.read_text(encoding="utf-8"))

wells = payload["candidate_wells"]
src_pt = payload["co2_source"]
gj = {"features": payload["routing_exclusions"]}
selection = payload["geology_selection"]
sel = selection["selected_case_ids"]
sel_tag = selection["tags"]
TAG_ID = {"low": "rendah", "median": "median", "high": "tinggi"}
fields = {
    cid: (
        np.asarray(
            selection["fields"][cid]["permeability_log10_md"]["values"],
            dtype=float,
        ),
        np.argwhere(
            np.asarray(selection["fields"][cid]["well_mask"]["values"]) > 0
        ),
    )
    for cid in sel
}
terrain = payload["terrain"]
LON0, LON1, LAT0, LAT1 = terrain["extent_lon_lat"]
dem = np.asarray(terrain["elevation_m"]["values"], dtype=float)
screening_grid = payload["screening_grid"]

# -------------------------------------------------------------------- figure
fig = plt.figure(figsize=(6.3, 7.05))
gs = fig.add_gridspec(
    3, 1, height_ratios=[2.45, 1.95, 1.62], hspace=0.58,
    left=0.075, right=0.975, top=0.967, bottom=0.072,
)


def panel_title(ax, s):
    ax.set_title(s, fontsize=F_TITLE, fontweight="bold", loc="left", pad=5)


# ================================================================== (a) terrain
axA = fig.add_subplot(gs[0])
ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(
    np.nan_to_num(dem, nan=0.0), cmap=TERRAIN_CMAP, blend_mode="soft",
    vert_exag=1.0,
    dx=terrain["rendered_cell_spacing_m"],
    dy=terrain["rendered_cell_spacing_m"],
    vmin=0,
    vmax=1100,
)
axA.imshow(rgb, extent=(LON0, LON1, LAT0, LAT1), origin="upper", zorder=1,
           aspect="equal")

# rivers (penalty corridors) and hard exclusion polygon
cimanuk_anchor = None
for feat in gj["features"]:
    geom, props = feat["geometry"], feat["properties"]
    if geom["type"] == "LineString":
        xy = np.array(geom["coordinates"])
        axA.plot(xy[:, 0], xy[:, 1], color=RIVER, lw=1.4, alpha=0.95, zorder=3)
        if "cimanuk" in props["zone_id"]:
            cimanuk_anchor = xy[np.argmax(xy[:, 1])]  # northernmost point
    elif geom["type"] == "Polygon":
        xy = np.array(geom["coordinates"][0])
        axA.add_patch(MplPolygon(xy, closed=True, fc=INK, ec=INK, zorder=4))
        hx, hy = xy[:, 0].mean(), xy[:, 1].mean()
        axA.annotate(
            "eksklusi mutlak\n(permukiman + 75 m)", (hx, hy), (107.97, -6.625),
            fontsize=F_SUB, color=INK, ha="center",
            arrowprops=dict(arrowstyle="-", color=SUB_INK, lw=0.8),
            path_effects=HALO, zorder=6,
        )

# CO2 source and candidate wells
axA.plot(src_pt["longitude"], src_pt["latitude"], marker="*", ms=15,
         mfc=PURPLE_EDGE, mec="white", mew=0.9, ls="none", zorder=6)
axA.annotate("Sumber CO$_2$ Subang", (src_pt["longitude"], src_pt["latitude"]),
             (src_pt["longitude"] - 0.005, src_pt["latitude"] + 0.032),
             fontsize=F_SUB, fontweight="bold", color=PURPLE_EDGE,
             path_effects=HALO, ha="center", zorder=6)
wlon = [c["longitude"] for c in wells]
wlat = [c["latitude"] for c in wells]
axA.plot(wlon, wlat, marker="o", ms=4.6, mfc=GOLD_EDGE, mec="white", mew=0.7,
         ls="none", zorder=6)
axA.annotate("W01", (wlon[0], wlat[0]), (wlon[0] - 0.014, wlat[0] + 0.022),
             fontsize=F_SUB, color=INK, path_effects=HALO, ha="center")
axA.annotate("W20", (wlon[-1], wlat[-1]), (wlon[-1] + 0.032, wlat[-1] - 0.018),
             fontsize=F_SUB, color=INK, path_effects=HALO, ha="center")
axA.annotate("sumur kandidat\nW01–W20", (wlon[10], wlat[10]),
             (108.30, -6.645), fontsize=F_SUB, fontweight="bold",
             color=GOLD_EDGE, ha="center", path_effects=HALO,
             arrowprops=dict(arrowstyle="-", color=SUB_INK, lw=0.8), zorder=6)
if cimanuk_anchor is not None:
    axA.annotate("S. Cimanuk (penalti ×8)",
                 tuple(cimanuk_anchor), (108.02, -6.385),
                 fontsize=F_SUB, color=RIVER, ha="center", path_effects=HALO,
                 arrowprops=dict(arrowstyle="-", color=RIVER, lw=0.8,
                                 shrinkB=2), zorder=6)

# scale bar: 20 km at this latitude
km20 = 20.0 / (111.32 * np.cos(np.radians(6.55)))
sbx, sby = 107.685, -6.700
axA.plot([sbx, sbx + km20], [sby, sby], color=INK, lw=2.2,
         solid_capstyle="butt", zorder=6)
axA.text(sbx + km20 / 2, sby + 0.012, "20 km", fontsize=F_SUB, ha="center",
         color=INK, path_effects=HALO, zorder=6)

# slim elevation colorbar inside the panel
cax = axA.inset_axes([0.795, 0.11, 0.185, 0.05])
fig.colorbar(
    plt.cm.ScalarMappable(norm=Normalize(0, 1100), cmap=TERRAIN_CMAP),
    cax=cax, orientation="horizontal",
)
cax.set_xticks([0, 1100])
cax.set_xticklabels(["0", "1100"], fontsize=F_SUB - 0.5)
cax.tick_params(axis="x", pad=1.5)
cax.tick_params(length=2, pad=1.5)
cax.set_title("elevasi (m)", fontsize=F_SUB - 0.5, pad=1.5, color=SUB_INK)

axA.set_xlim(LON0, LON1)
axA.set_ylim(LAT0, LAT1)
axA.set_xticks([107.8, 108.0, 108.2, 108.4])
axA.set_xticklabels(["107,8°BT", "108,0°BT", "108,2°BT", "108,4°BT"])
axA.set_yticks([-6.7, -6.5])
axA.set_yticklabels(["6,7°LS", "6,5°LS"])
axA.tick_params(length=2.5, pad=2)
panel_title(axA, f"(a)  Koridor Subang → Jatibarang ({terrain['source']})")

# ============================================================ (b) geology trio
gsB = gs[1].subgridspec(2, 3, height_ratios=[1.0, 0.09], wspace=0.10,
                        hspace=0.28)
vmin, vmax = 1.0, 3.5  # log10(mD)
imB = None
axB_first = None
for k, (cid, tag) in enumerate(zip(sel, sel_tag)):
    axB = fig.add_subplot(gsB[0, k])
    if k == 0:
        axB_first = axB
    perm, wpos = fields[cid]
    imB = axB.imshow(perm, cmap=PERM_CMAP, vmin=vmin, vmax=vmax,
                     origin="lower", interpolation="nearest")
    if len(wpos):
        r, c = wpos.mean(axis=0)
        axB.plot(c, r, marker="^", ms=6.5, mfc="white", mec=INK, mew=1.1)
    gmean = 10 ** perm.mean()
    axB.set_title(f"kasus {cid} — {TAG_ID.get(tag, tag)}\nrerata geometrik {gmean:.0f} mD",
                  fontsize=F_SUB, pad=3, color=SUB_INK, linespacing=1.05)
    axB.set_xticks([])
    axB.set_yticks([])
    if k == 0:
        axB.set_ylabel("64 × 64 sel", fontsize=F_SUB, color=SUB_INK)
caxB = fig.add_subplot(gsB[1, :])
pos = caxB.get_position()
caxB.set_position([pos.x0 + pos.width * 0.25, pos.y0 + pos.height * 0.45,
                   pos.width * 0.50, pos.height * 0.55])
cb = fig.colorbar(imB, cax=caxB, orientation="horizontal")
cb.set_ticks([1, 2, 3])
cb.set_ticklabels(["10", "100", "1000"])
cb.ax.tick_params(labelsize=F_SUB, length=2.5, pad=1.5)
cb.set_label("permeabilitas (mD)", fontsize=F_SUB, color=SUB_INK, labelpad=2)
axB_first.text(0.0, 1.30,
               "(b)  Realisasi geologi — skala permeabilitas bersama",
               transform=axB_first.transAxes, fontsize=F_TITLE,
               fontweight="bold", va="bottom")

# ===================================================== (c) HnP operating grid
gsC = gs[2].subgridspec(1, 2, width_ratios=[1.25, 1.0], wspace=0.40)
axC = fig.add_subplot(gsC[0])
axC.set_xlim(0, 100)
axC.set_ylim(0, 100)
axC.axis("off")
panel_title(axC, "(c)  Grid operasi HnP")

BAR_Y, BAR_H = 74, 20
segs = [  # (width, fill, edge, name)
    (23, TEAL_FILL, TEAL, "injeksi"),
    (18, "#EBE9E4", GRAY_EDGE, "soak"),
    (39, GOLD_FILL, GOLD_EDGE, "produksi"),
]
x = 2
seg_colors = {}
for wseg, fc, ec, name in segs:
    axC.add_patch(FancyBboxPatch(
        (x, BAR_Y), wseg - 3.0, BAR_H, boxstyle="round,pad=0,rounding_size=1.5",
        fc=fc, ec=ec, lw=1.2,
    ))
    axC.text(x + (wseg - 3.0) / 2, BAR_Y + BAR_H / 2, name, fontsize=F_SUB,
             fontweight="bold", ha="center", va="center", color=INK)
    seg_colors[name] = (fc, ec)
    x += wseg
# faded repeats: "x 3 or 4 cycles"
for rep, alpha in [(0, 0.45), (1, 0.22)]:
    axC.add_patch(Rectangle((86 + rep * 4.6, BAR_Y + 2), 3.4, BAR_H - 4,
                            fc="#C9C2B0", ec=GRAY_EDGE, lw=0.8, alpha=alpha))
cycle_label = " atau ".join(str(int(value)) for value in screening_grid["cycles"])
axC.text(90.5, BAR_Y - 4.5, f"× {cycle_label} siklus", fontsize=F_SUB, ha="center",
         va="top", color=SUB_INK)

rows = [
    (
        "injeksi",
        "laju  "
        + " · ".join(
            f"{value / 1000:g}k"
            for value in screening_grid["injection_rate_m3_day"]
        )
        + " m³/hari",
    ),
    (
        "soak",
        " · ".join(f"{value:g}" for value in screening_grid["soak_days"])
        + " hari",
    ),
    (
        "produksi",
        " · ".join(f"{value:g}" for value in screening_grid["production_days"])
        + " hari",
    ),
    (
        "produksi",
        "BHP  "
        + " · ".join(
            f"{value:g}" for value in screening_grid["production_bhp_psi"]
        )
        + " psi",
    ),
]
ry = 56
for i, (seg, label) in enumerate(rows):
    if i != 3:
        fc, ec = seg_colors[seg]
        axC.add_patch(Rectangle((2, ry - 3.2), 5.2, 6.4, fc=fc, ec=ec, lw=1.0))
    axC.text(10.5, ry, label, fontsize=F_SUB, va="center", color=INK)
    ry -= 12.5
dimension_order = (
    "injection_rate_m3_day",
    "soak_days",
    "production_days",
    "production_bhp_psi",
    "cycles",
)
dimension_text = " · ".join(
    str(len(screening_grid[name])) for name in dimension_order
)
axC.text(2, 3, f"{dimension_text}  =  {payload['schedules_per_well']} jadwal per sumur",
         fontsize=F_SUB + 0.5, fontweight="bold", color=INK)

# ================================================= (d) carbon-price scenarios
axD = fig.add_subplot(gsC[1])
panel_title(axD, "(d)  Skenario harga karbon")
scen = payload["carbon_price_scenarios"]
names = {
    "current_idx": "IDX saat ini",
    "domestic_maturing": "domestik\nmatang",
    "article6_jcm": "Artikel 6\n/ JCM",
    "aspirational": "aspiratif",
}
for i, s in enumerate(scen):
    p = s["carbon_price_usd_per_tonne"]
    observed = s["source_type"] == "market_observation"
    color = PURPLE_RAMP[i]
    axD.plot([0, p], [i, i], color=color, lw=2.2, zorder=3,
             solid_capstyle="butt")
    axD.plot(p, i, marker="o", ms=8, mfc=color if observed else "white",
             mec=color, mew=1.8, zorder=4)
    tag = f"USD {p:.0f}" if p >= 10 else f"USD {p:.2f}".replace(".", ",")
    if observed:
        tag += " (teramati)"
    axD.text(p + 1.8, i, tag, fontsize=F_SUB, va="center", color=INK,
             fontweight="bold")
axD.set_yticks(range(len(scen)))
axD.set_yticklabels([names[s["scenario_id"]] for s in scen], fontsize=F_SUB,
                    linespacing=0.95)
axD.set_xlim(0, 72)
axD.set_ylim(-0.6, 3.6)
axD.set_xlabel("harga karbon (USD / tCO$_2$)", fontsize=F_SUB, color=SUB_INK)
axD.spines[["top", "right", "left"]].set_visible(False)
axD.tick_params(axis="y", length=0)
axD.tick_params(axis="x", length=2.5)
axD.grid(axis="x", color="#E3E1DB", lw=0.7, zorder=0)
axD.set_axisbelow(True)

localize(fig)

fig.savefig(OUT_DIR / "fig02_atlas.pdf")
fig.savefig(OUT_DIR / "fig02_atlas.png", dpi=300)
print("wrote", OUT_DIR / "fig02_atlas.pdf")
