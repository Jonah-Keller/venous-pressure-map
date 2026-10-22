> **Use the website survey.** Patients now fill out the survey on the project
> website (`survey.html`, linked as **Patient survey ↗** in the app). Answers go
> to the **Survey** tab of the study sheet (see `storage/README.md`). The page
> reads its questions from the SURVEY block in `build_form.gs`, so that block
> plus `answer_key.json` are still the one place to change questions. The
> Google Form route below is a backup, for example for a clinic that wants a
> Forms link or QR code instead.

# Patient education survey (venous sinus stenting QI project)

Patients considering venous sinus stenting (usually for idiopathic intracranial
hypertension) have a pre-procedure discussion either:

| Clinic code | What happened in the discussion |
|---|---|
| **A** | Shown the diagram (annotated venogram with venous pressures, made by the Streamlit app in this repo) |
| **B** | Verbal discussion only, no diagram |

Afterwards they fill out a short, anonymous Google Form. No names, dates of
birth, MRNs or emails are collected.

**This table is the only place the A/B meaning is written down.** The form
shows staff a neutral "Clinic code: A / B" item so patients are not told
which group they are in. Keep it that way.

## Files

| File | Purpose |
|---|---|
| `build_form.gs` | Google Apps Script. Builds the form, its response Sheet and the two pre-filled links (A and B). |
| `answer_key.json` | Question codes, exact titles, options and correct answers. Single source of truth for scoring. |
| `analyze_survey.py` | Reads the downloaded CSV and writes the A vs B results (tables, report, figure). |
| `example_responses_SYNTHETIC.csv` | 32 made-up responses for testing. Not real patients. |
| `../tests/test_survey_analysis.py` | Checks that the form and answer key match, the scoring rules, and a full run. |

## 1. Build the form (once)

1. Go to <https://script.google.com> with the study/clinic Google account → **New project**.
2. Delete the `function myFunction() {}` stub, paste all of `build_form.gs`, click **Save**.
3. Choose `buildSurvey` in the function drop-down → **Run**.
4. Approve the permission prompt: *Review permissions* → pick the account →
   *Advanced* → *Go to (project) (unsafe)* → *Allow*. ("Unsafe" just means
   Google hasn't reviewed your own script; it only creates a Form and a Sheet
   in your Drive.)
5. When it says *Execution completed*, open the **Execution log**. It lists the
   form editor link, the response Sheet link, and the two patient links.
6. Open the form editor once and check: under **Settings**, "Collect email
   addresses" is off and sign-in is not required; at the top, the form is
   **Published / accepting responses**. Fill in a test response through the
   A link, check it lands in the Sheet, then delete that test row.

Running the script again does **not** change the old form: it makes a new
form, a new Sheet and new links (see "Changing a question" below).

## 2. Give each patient the right link

The response Sheet has a **Links** tab with two pre-filled links. Each one
opens the form with "Clinic code" already set to A or B.

Suggested set-up:

- Make a QR code from each link (Chrome: open the link → right-click →
  *Create QR code*; or any QR generator).
- Print them on two cards kept at the clinic, labelled for **staff** in a way
  patients won't decode (e.g. a small staff-only key on the back, or two
  differently coloured cards with the meaning on a staff cheat-sheet).
- After the discussion, staff hand over the card that matches **what was
  actually done** (diagram shown → A; no diagram → B). A clinic tablet works
  too: open the right A or B link fresh for every patient. Don't use the
  form's "Submit another response" link for the next patient: it opens the
  plain form without the clinic code.
- Never hand out the plain form link: it has no clinic code, so those answers
  can't be analysed.

A wrong card puts a patient in the wrong group and can't be fixed later, because
the survey is anonymous.

## 3. Export and analyse

1. In the response Sheet: **File → Download → Comma-separated values (.csv)**
   while the "Form Responses 1" tab is selected.
2. Save it somewhere **outside git** (real responses must not be committed;
   `survey/.gitignore` ignores CSVs and `results/` here as a safety net).
3. From the `Stenting-Code` folder:

   ```bash
   .venv/bin/python survey/analyze_survey.py path/to/responses.csv --out survey/results/
   ```

   Try it first on the synthetic file:
   `.venv/bin/python survey/analyze_survey.py survey/example_responses_SYNTHETIC.csv --out /tmp/survey_test/`

Outputs:

| File | Contents |
|---|---|
| `report.md` | Plain-language summary: N per group, main table, knowledge items, who answered, caveats. Start here. |
| `summary_by_group.csv` | The 4 composites: n, median, IQR, mean per group, Mann–Whitney U, p, BH-FDR p, rank-biserial effect. |
| `item_level.csv` | Every 1–5 question and knowledge question by group (descriptive only). |
| `open_text.csv` | Free-text answers by group. Read before sharing; patients sometimes type names. |
| `composites_by_group.png` / `.pdf` | 2×2 box-and-dot plot of the composites. Statistics are in `report.md`, not on the figure. |

If the script says columns are missing or unexpected, a question title was
changed in one place but not the other (or the wrong CSV was downloaded). The
error lists the exact titles.

### Analysis plan (decided before data collection)

- **Who is analysed:** said "Yes" to consent and has clinic code A or B.
  People who said "No" are counted, then dropped (the form ends right away for them).
- **Composites** (mean of the items a person answered):
  - *Understanding* = 4 "I understand…" items (1–5)
  - *Confidence* = 3 "How are you feeling" items (1–5)
  - *Satisfaction* = 3 "About today's visit" items (1–5)
  - *Knowledge* = mean of 4 item scores (0–1). The three single-answer
    questions score 1 if correct, else 0 ("I'm not sure" = 0). The symptoms
    question (select all that apply) scores (correct ticked − wrong ticked) / 3,
    floored at 0, and 0 if "I'm not sure" is ticked.
- **All 1–5 scales: 5 = best.**
- **Main test:** A vs B for each composite with Mann–Whitney U (two-sided),
  rank-biserial effect size, Benjamini–Hochberg FDR across the 4 composites as
  one family. If either group has fewer than 3 responses, tests are skipped.
- **Per-item results** are descriptive only.

## 4. Changing a question safely

1. Edit the question in **both** `build_form.gs` (the `SURVEY` block) and
   `answer_key.json`, word for word. If you change a knowledge question's
   options, update its `correct` answer too. Keep the `SURVEY` block valid
   JSON (double quotes, no trailing commas).
2. Run the tests from `Stenting-Code`:
   `.venv/bin/python -m pytest tests/test_survey_analysis.py -q`
   They fail if the two files disagree.
3. Re-run `buildSurvey()`. This makes a **new** form, Sheet and links. Reprint
   both QR codes, and turn off "Accepting responses" on the old form.
4. Responses from the old form stay in the old Sheet. Don't merge old and new
   CSVs unless the questions are identical; analyse them separately, or ask
   your supervisor.

Avoid commas in checkbox options (Google Sheets joins ticked boxes with ", ").
The script can cope, but it's simpler without them.

Editing a question directly in the Google Forms editor also changes the Sheet
header, so the analysis will stop matching until `answer_key.json` is updated
too. Prefer editing `build_form.gs` and rebuilding.

## What changed vs. the original form, and why

| Original form | Now | Why |
|---|---|---|
| Consent "No" skipped to question 3 | "No" ends the form; "Yes" continues | Someone who declines shouldn't be asked anything else. |
| "Group Assignment" showed "Group A: Discussion with visual diagram" | Staff-only page, dropdown "Clinic code" with just A / B, pre-filled by the link | Patients shouldn't see which group they're in; the labels could bias answers. |
| Q3–6: 1 = "Yes, I understand", 5 = confused; Q11–16: 5 = good | Every 1–5 scale has 5 = best | Mixed directions confuse patients and make scoring error-prone. |
| Q10 symptoms: pick one; typo "whoosing" | Checkbox, "Select all that apply"; "whooshing" | Three answers are correct; single choice forced patients to drop two of them. |
| Two sections numbered "Section 4" | No numbers in section titles | Duplicate numbering; numbers add nothing. |
| Q7–9: correct answer always first and noticeably longer | Correct answer in positions 2, 3 and 1; options of similar length and detail; "I'm not sure" always last | Patients could guess the answer from its position or length. |
| "Pick I'm not sure and we'll go over it with you" | "…the survey is anonymous, please ask your care team before you leave" | The team can't follow up an anonymous answer. |
| Age options "18 - 34" etc. | "18 to 34" etc. | Avoids spreadsheets reading the ranges as dates or numbers. |
| (none) | Optional "Who is filling out this form?" | Family members often fill these out; worth knowing. |
| Built by hand | Built by `build_form.gs` from one question list | Reproducible; analysis keyed to the same titles. |
