# Venous Pressure Map

A quality-improvement project on patient education before venous sinus stenting.
It has two parts:

1. **The app** (`app.py`). Type the venous manometry readings into a table. It
   finds the narrowing from the pressures and shows it on a 3D model of real
   sinus anatomy, with before/after stent and a blood-flow simulation. It then
   saves the case under a study ID to the study sheet.
2. **The survey** (`survey/`). An anonymous Google Form that patients fill out
   after the discussion, plus the script that compares Group A (shown the 3D picture)
   with Group B (verbal only).

**Live site:** https://jonah-keller.github.io/venous-pressure-map/ (runs entirely in your
browser; the first load takes about 20 s).

**New to the project? Read [docs/HANDOFF.md](docs/HANDOFF.md) first.**

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
streamlit run app.py          # opens http://localhost:8501
pytest -q                     # all tests should pass
```

Click **Fill in example values** in the app to see everything working.

## Layout

| Path | What it is |
|---|---|
| `app.py` | The Streamlit page (UI only) |
| `venous/anatomy.py` | Locations, units, and finding the narrowing from the pressures |
| `venous/sinus3d.py` | Paints the readings onto the real sinus anatomy for the 3D viewer |
| `venous/viewer3d.html` | The 3D viewer (three.js): before/after, blood flow, CT slices, full screen, handout |
| `venous/save.html`, `storage/`, `storage.json` | **Save to study records** → Google Sheet ([storage/README.md](storage/README.md)) |
| `venous/export.py` | The saved record, CSV and Excel |
| `venous/render.py` | Shared colour scale and fonts |
| `venous/demo.py` | Example readings (typical published values, not a patient) |
| `venous/data/example_scan.npz` | Sinus surface, skull and CT volume built from an open-data scan |
| `tools/build_example_scan.py` | Rebuilds that file from the source CT (segmentation + meshing) |
| `.streamlit/config.toml` | Theme colours and upload limit (local runs) |
| `index.html`, `.nojekyll` | GitHub Pages site (stlite runs the app in the browser) |
| `survey/` | Google Form builder, answer key, analysis script ([survey/README.md](survey/README.md)) |
| `tests/` | pytest suite for the app logic and the survey analysis |
| `deprecated/` | Old prototypes, kept for reference only |

## Privacy

No names or MRNs anywhere. The app runs in the browser and keeps nothing after
the tab closes. **Save** sends only the study ID, procedure date and readings to
the team's study sheet. The study ID ↔ MRN key stays in the secure team folder.
The survey collects no identifiers.

## Credits

The 3D anatomy is derived from the TopBrain 2025 challenge data (University
Hospital Zurich), case `topcow_ct_012`, Zenodo record
[16878417](https://zenodo.org/records/16878417). Terms: open non-commercial use
with attribution. Please also cite the TopBrain and TopCoW
([arXiv:2312.17670](https://arxiv.org/abs/2312.17670)) challenge papers.
