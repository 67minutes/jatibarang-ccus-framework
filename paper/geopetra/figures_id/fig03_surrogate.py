"""Figure 3 — Surrogate credibility (showpiece).

  (a) Plume gallery on the median-error validation case (case_0016, median
      cumulative-oil error of the five curated cases): MRST truth / surrogate
      free rollout / residual at stage-diverse horizons, including the 24-step
      validation boundary and the extended horizon.
  (b) Cumulative oil and gas for the gallery case, truth vs rollout, with the
      eight-frame seed region marked.
  (c) Cumulative-oil error vs rollout horizon for all five validation cases.
  (d) Seed -> free-rollout transition: gas plume area, truth vs rollout.

All numerical arrays are read from the selected, hash-verified Feature 007
bundle. The bundle builder is the only component allowed to ingest the
derived MRST case and frozen surrogate cache. Renders at true print size
(6.3 in wide); 12 pt panel titles, >= 9.5 pt text.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from feature007_common import localize
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from feature007_common import FigureBlockedError, parser, require_ready

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).parent

# ---------------------------------------------------------------- visual system
INK = "#1F1F1F"
SUB_INK = "#4A4A4A"
GOLD = "#8A6D00"
GRAY_EDGE = "#8C8C8C"
TEAL_CMAP = LinearSegmentedColormap.from_list(
    "plume_teal", ["#FFFFFF", "#DCEEEC", "#9ED4D0", "#57AFA9", "#2E8F8A", "#17544F"]
)
DIV_CMAP = LinearSegmentedColormap.from_list(
    "resid_div", ["#3E6FA8", "#FFFFFF", "#B0413E"]
)

F_TITLE = 12.0
F_SUB = 9.5
HALO = [pe.withStroke(linewidth=2.4, foreground="white")]

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
        "axes.labelsize": F_SUB,
        "legend.fontsize": F_SUB,
    }
)

args = parser(3, __doc__).parse_args()
manifest, _ = require_ready(args.bundle, args.figure_number)
record = manifest.get("reservoirs", {}).get("case_0016")
if not record or not record.get("available"):
    raise FigureBlockedError("Figure 3 case_0016 reservoir payload is unavailable")
payload_path = args.bundle / record["path"]
payload = json.loads(payload_path.read_text(encoding="utf-8"))

GALLERY = payload["case_id"]
CASES = list(payload["selection"]["candidate_cases"])
COLS = [int(step) for step in payload["comparison_steps"]]
dynamic = payload["dynamic"]
gas_pred = np.asarray(dynamic["surrogate_free_rollout"]["values"], dtype=np.float32)
gas_forecast_truth = np.asarray(dynamic["mrst_truth"]["values"], dtype=np.float32)
gas_warm_start = np.asarray(
    payload["warm_start"]["gas_saturation"]["values"], dtype=np.float32
)
gas_true = np.concatenate([gas_warm_start, gas_forecast_truth], axis=0)
stages = np.array(
    [0] * len(gas_warm_start)
    + [int(frame["stage_code"]) for frame in payload["frame_metadata"]]
)

data: dict[str, np.ndarray] = {}
for case_id, case in payload["validation_cohort"]["cases"].items():
    data[f"{case_id}/horizon"] = np.array(case["horizon_steps"])
    data[f"{case_id}/cum_oil_true"] = np.asarray(case["oil_m3_mrst"])
    data[f"{case_id}/cum_oil_pred"] = np.asarray(case["oil_m3_surrogate"])
    data[f"{case_id}/cum_gas_true"] = np.asarray(case["gas_m3_mrst"])
    data[f"{case_id}/cum_gas_pred"] = np.asarray(case["gas_m3_surrogate"])

STAGE_NAME = {1: "injeksi", 2: "soak", 3: "produksi"}

# -------------------------------------------------------------------- figure
fig = plt.figure(figsize=(6.3, 6.65))
gs = fig.add_gridspec(
    2, 1, height_ratios=[2.45, 1.0], hspace=0.34,
    left=0.095, right=0.925, top=0.885, bottom=0.075,
)

# ================================================================ (a) gallery
# shared zoom window around the plume (union of shown truth+pred, padded)
show_fields = [gas_true[7 + t] for t in COLS] + [gas_pred[t - 1] for t in COLS]
mask = np.any(np.stack(show_fields) >= 0.01, axis=0)
rows_any, cols_any = np.where(mask)
pad = 5
r0, r1 = max(rows_any.min() - pad, 0), min(rows_any.max() + pad, 63)
c0, c1 = max(cols_any.min() - pad, 0), min(cols_any.max() + pad, 63)
side = max(r1 - r0, c1 - c0)  # square crop
r1, c1 = min(r0 + side, 63), min(c0 + side, 63)
r0, c0 = r1 - side, c1 - side


def crop(a: np.ndarray) -> np.ndarray:
    return a[r0:r1 + 1, c0:c1 + 1]


gsA = gs[0].subgridspec(3, 5, width_ratios=[1, 1, 1, 1, 0.07],
                        wspace=0.07, hspace=0.07)
VMAX_GAS = 0.72
res_all = [gas_pred[t - 1] - gas_true[7 + t] for t in COLS]
VMAX_RES = float(np.ceil(max(np.abs(r).max() for r in res_all) * 10) / 10)

row_labels = ["kebenaran MRST", "surrogate\n(rollout bebas)", "residu\n(prediksi − MRST)"]
im_gas = im_res = None
for j, t in enumerate(COLS):
    frame = 7 + t
    truth = gas_true[frame]
    pred = gas_pred[t - 1]
    for i, field in enumerate([truth, pred, pred - truth]):
        ax = fig.add_subplot(gsA[i, j])
        if i < 2:
            im_gas = ax.imshow(crop(field), cmap=TEAL_CMAP, vmin=0,
                               vmax=VMAX_GAS, origin="lower",
                               interpolation="nearest")
        else:
            im_res = ax.imshow(crop(field), cmap=DIV_CMAP, vmin=-VMAX_RES,
                               vmax=VMAX_RES, origin="lower",
                               interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        if j == 0:
            ax.set_ylabel(row_labels[i], fontsize=F_SUB, color=SUB_INK,
                          linespacing=1.05)
        if i == 0:
            extra = ""
            if t == 24:
                extra = "\n(batas validasi)"
            elif t == 40:
                extra = "\n(horizon diperluas)"
            ax.set_title(f"t+{t} · {STAGE_NAME[stages[frame]]}{extra}",
                         fontsize=F_SUB, pad=3, color=SUB_INK, linespacing=1.05)
        if i == 0 and j == 0:
            ax.text(0.03, 0.04, f"jendela {side + 1}×{side + 1} sel",
                    transform=ax.transAxes, fontsize=F_SUB - 0.5,
                    color=SUB_INK, path_effects=HALO)

cax_gas = fig.add_subplot(gsA[0:2, 4])
cb1 = fig.colorbar(im_gas, cax=cax_gas)
cb1.set_ticks([0, 0.2, 0.4, 0.6])
cb1.set_label("saturasi gas", fontsize=F_SUB, color=SUB_INK)
cb1.ax.tick_params(labelsize=F_SUB, length=2.5)
cax_res = fig.add_subplot(gsA[2, 4])
cb2 = fig.colorbar(im_res, cax=cax_res)
cb2.set_ticks([-VMAX_RES, 0, VMAX_RES])
cb2.ax.tick_params(labelsize=F_SUB, length=2.5)
for cax in (cax_gas, cax_res):
    pos = cax.get_position()
    cax.set_position([pos.x0, pos.y0 + pos.height * 0.06,
                      pos.width, pos.height * 0.88])

fig.text(0.095, 0.993,
         "(a)  Galeri plume — kasus 0016 (kasus validasi bergalat median)",
         fontsize=F_TITLE, fontweight="bold", va="top")

# =========================================================== bottom row (b-d)
gsBot = gs[1].subgridspec(1, 3, width_ratios=[1.0, 1.0, 1.0], wspace=0.46)


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=2.5)
    ax.grid(color="#ECEAE4", lw=0.7)
    ax.set_axisbelow(True)


# ---- (b) cumulative production, gallery case
gsB = gsBot[0].subgridspec(2, 1, hspace=0.16)
t_axis = np.arange(48) - 7  # forecast step index; seed is t <= 0
for k, (species, label) in enumerate([("oil", "minyak"), ("gas", "gas")]):
    ax = fig.add_subplot(gsB[k])
    true = data[f"{GALLERY}/cum_{species}_true"] / 1e3
    pred = data[f"{GALLERY}/cum_{species}_pred"] / 1e3
    ax.axvspan(t_axis[0], 0, color="#EFEDE7", zorder=0)
    ax.plot(t_axis, true, color="black", lw=1.6, label="kebenaran MRST")
    ax.plot(t_axis[8:], pred[8:], color=GOLD, lw=1.6, ls="--",
            label="surrogate")
    ax.set_ylabel(f"kum. {label}\n(10³ m³)", fontsize=F_SUB, color=SUB_INK,
                  linespacing=1.0)
    ax.set_xlim(t_axis[0], 40)
    style(ax)
    if k == 0:
        ax.set_xticklabels([])
        ax.legend(frameon=False, loc="upper left", handlelength=1.2, fontsize=6.3,
                  borderaxespad=0.15, labelspacing=0.2)
        ax.set_title("(b)  Produksi", fontsize=F_TITLE, fontweight="bold",
                     loc="left", pad=5)
    else:
        ax.set_xlabel("langkah prakiraan t", fontsize=F_SUB, color=SUB_INK)
        ax.text(-6.8, ax.get_ylim()[1] * 0.92, "", fontsize=F_SUB,
                color=SUB_INK, va="top")

# ---- (c) cumulative-oil error vs horizon, all five cases
axC = fig.add_subplot(gsBot[1])
for cid in CASES:
    true = data[f"{cid}/cum_oil_true"]
    pred = data[f"{cid}/cum_oil_pred"]
    h = int(data[f"{cid}/horizon"])
    steps = np.arange(1, h + 1)
    err = np.abs(pred[8:8 + h] - true[8:8 + h]) / true[8:8 + h] * 100.0
    is_gallery = cid == GALLERY
    axC.plot(steps, err, color=GOLD, lw=1.8 if is_gallery else 1.0,
             alpha=1.0 if is_gallery else 0.45, zorder=3 if is_gallery else 2)
axC.axvline(24, color=SUB_INK, lw=0.9, ls="--", zorder=1)
axC.axvspan(24, 41, color="#F3F1EB", zorder=0)
axC.set_xlim(1, 41)
axC.set_ylim(0, 3.4)
tC = axC.text(23.0, axC.get_ylim()[1] * 0.97, "horizon tervalidasi", rotation=90, fontsize=F_SUB,
              color=SUB_INK, va="top", ha="right",
              bbox=dict(facecolor="white", edgecolor="none", pad=0.6))
tC.set_path_effects(HALO)
axC.set_xlabel("langkah prakiraan t", fontsize=F_SUB, color=SUB_INK)
axC.set_ylabel("galat minyak kumulatif (%)", fontsize=F_SUB, color=SUB_INK)
axC.set_title("(c)  Galat vs. horizon", fontsize=F_TITLE, fontweight="bold",
              loc="left", pad=5)
style(axC)

# ---- (d) seed -> free-rollout transition: plume area
axD = fig.add_subplot(gsBot[2])
area_true = (gas_true >= 0.01).mean(axis=(1, 2)) * 100.0
area_pred = (gas_pred >= 0.01).mean(axis=(1, 2)) * 100.0
axD.axvspan(t_axis[0], 0, color="#EFEDE7", zorder=0)
axD.plot(t_axis, area_true, color="black", lw=1.6)
axD.plot(np.arange(1, 41), area_pred, color=GOLD, lw=1.6, ls="--")
axD.axvline(0, color=SUB_INK, lw=0.9)
axD.axvline(24, color=SUB_INK, lw=0.9, ls="--")
axD.set_xlim(t_axis[0], 40)
axD.set_ylim(bottom=0)
axD.text(-6.8, axD.get_ylim()[1] * 0.92, "", fontsize=F_SUB,
         color=SUB_INK, va="top")
axD.set_xlabel("langkah prakiraan t", fontsize=F_SUB, color=SUB_INK)
axD.set_ylabel("luas plume (% sel)", fontsize=F_SUB, color=SUB_INK)
axD.set_title("(d)  Luas plume", fontsize=F_TITLE, fontweight="bold",
              loc="left", pad=5)
style(axD)

localize(fig)

fig.savefig(OUT_DIR / "fig03_surrogate.pdf")
fig.savefig(OUT_DIR / "fig03_surrogate.png", dpi=300)
print("wrote", OUT_DIR / "fig03_surrogate.pdf")
