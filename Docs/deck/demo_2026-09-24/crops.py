"""Deck crops from the raw screenshots (idempotent; originals untouched).
Boxes are in 2000x1250 display coordinates of the 3200x2000 full shots."""
from PIL import Image
from pathlib import Path
D = Path(r"C:\Users\thiba\vol-fitter\Docs\deck\assets\shots_demo")

def crop(name, box, out, full=True):
    p = D / f"{name}.png"
    if not p.exists():
        print("missing", name); return
    im = Image.open(p); W, H = im.size
    sx, sy = (W / 2000, H / 1250) if full else (1, 1)
    b = (int(box[0]*sx), int(box[1]*sy), int(box[2]*sx), int(box[3]*sy))
    out_im = im.crop(b); out_im.save(D / f"{out}.png"); print(out, out_im.size)

DIALOG = (282, 104, 1720, 1146)
for n in ["dialog_options_parametric", "dialog_options_calibration", "dialog_options_prior", "dialog_options_prior_evidence",
          "dialog_options_filter", "dialog_options_events", "dialog_options_graph", "dialog_options_dynamics", "filter_panel_timeline"]:
    crop(n, DIALOG, n + "_crop")
crop("dialog_options_prior", (523, 505, 1700, 620), "options_prior_operators_crop")
crop("dialog_options_calibration", (523, 245, 1700, 640), "options_calibration_target_crop")
crop("smile_compare", (488, 975, 1600, 1152), "smile_compare_table")
crop("graph_dark_smile", (78, 172, 1612, 1195), "graph_dark_smile_card")
crop("quality_dashboard", (478, 102, 1992, 242), "quality_tiles_crop")
crop("graph_coupling_pane", (0, 0, 624, 900), "graph_coupling_pane_crop", full=False)
crop("graph_inspector_dark", (0, 0, 688, 1188), "graph_inspector_dark_crop", full=False)
# --- second pass: the live desk's Data sources card, the two Fit-switch chart cards
crop("live_datasources_card", (1285, 258, 1714, 988), "live_datasources_card_crop")
crop("smile_fit_switch_prior", (480, 168, 1612, 1195), "smile_fit_switch_prior_card")
crop("smile_fit_switch_free", (480, 168, 1612, 1195), "smile_fit_switch_free_card")
