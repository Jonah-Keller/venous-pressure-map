# Handoff guide

The project compares two ways of explaining venous sinus stenting before the
procedure. **Group A** is shown the app's 3D picture. **Group B** has the same
talk without it. Afterwards every patient fills out the same anonymous survey.

You have three jobs: run it in clinic, keep the records, and analyse the survey.

---

## 1. In clinic (Group A)

Open the website, or run `streamlit run app.py` on your laptop. Then work down
the page:

1. **Enter the pressures.** Click the unit (our reports are usually cm H₂O) and
   the side measured. Type each reading from the venogram report into the
   table; leave a box empty if it wasn't measured. **After stent** is optional.
   The app finds the narrowing itself: it's where the pressure drops the most
   between two neighbouring readings. The box on the right shows it.
2. **Show the patient.** Click **Full screen**. Use **Before stent / After
   stent** and **Blood flow** while you explain. The panel on the right walks
   through cause and effect. Drag to spin. **More** has other views, the skull,
   CT slices and **Save picture**. **Handout** saves a printable page in the
   same style, with before and after side by side from the angle you're
   looking at. **More → Print handout** opens it ready to print.
3. **Save.** Type a new **study ID** (`VP-0001`, `VP-0002`, …) and the procedure
   date, then click **Save to study records**. Write the study ID next to the
   MRN in the secure key file, which lives only in the team folder.

Then click **Patient survey ↗** (top right of the app), tap clinic code **A**,
and hand the screen to the patient. Answers go straight to the study sheet.

**Group B:** have the usual talk, save the readings the same way, open the
survey and tap **B**.

Practise once with **Fill in example values**.

## 2. Records

- Readings (tab **Readings**) and survey answers (tab **Survey**) are saved in
  the same study Google Sheet. Setup is in
  [storage/README.md](../storage/README.md).
- Never type names or MRNs into the app, the sheet, or the survey.
- The 3D anatomy is an example scan from open data, not the patient's own.
  The credit is in the app sidebar and the README.

## 3. Survey

The survey is a page on the same website (`survey.html`). Answers land in the
**Survey** tab of the study sheet. To analyse, download that tab as CSV
(**File → Download → CSV**) and run:

```bash
python survey/analyze_survey.py responses.csv --out survey/results/
```

---

## Changing things

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                  # all tests should pass
streamlit run app.py
```

| I want to… | Edit |
|---|---|
| Change wording on the page | `app.py` |
| Change the 3D picture or its buttons | `venous/viewer3d.html` |
| Change the cause-and-effect text or the handout layout | `CHAIN` and `handoutCanvas()` in `venous/viewer3d.html` |
| Add or rename a location | `LOCATIONS`, `CANONICAL`, `PLAIN` in `venous/anatomy.py`, and `ANCHORS` in `venous/sinus3d.py` |
| Change how big a drop counts as a narrowing | `MIN_DROP_MMHG` in `venous/anatomy.py` |
| Change a survey question | `survey/build_form.gs` (SURVEY block) **and** `survey/answer_key.json`, then `pytest` |
| Change the survey page's look | `survey.html` |
| Change the colour scale | top of `venous/render.py` |
| Rebuild the 3D anatomy | `tools/build_example_scan.py` (instructions at the top) |

Run `pytest -q` after any change.

### Publishing the website

The site is GitHub Pages. `index.html` runs the same app inside the visitor's
browser, so readings never leave the computer unless someone clicks Save.

- **Update the site:** merge into the branch Pages serves (repo **Settings →
  Pages**). It updates within 1–2 minutes.
- **Add a new file:** if it's a new `.py` or `.html` file, also add it to the
  `FILES` list in `index.html`.
- **Add a package:** add it to `requirements.txt` and to the `requirements`
  list in `index.html`.
- **Test the website version locally:** run `python -m http.server 8000` and
  open http://localhost:8000.
- **Keep `.nojekyll`** in the repo root.
- **First visit:** loads in about 20 seconds, and the 3D view loads three.js
  from cdn.jsdelivr.net.

Ask Jonah to add you as a collaborator on the GitHub repo and the study sheet.
