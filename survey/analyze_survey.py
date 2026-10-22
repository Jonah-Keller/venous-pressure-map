"""Analyse the Venous Sinus Stenting Patient Education survey (Group A vs B).

Usage
-----
    python survey/analyze_survey.py path/to/responses.csv --out survey/results/

Input is the CSV downloaded from the response Google Sheet
(File -> Download -> Comma-separated values). Column headers are the question
titles plus "Timestamp". Columns are matched to question codes through the
exact titles in survey/answer_key.json, which must stay in sync with
survey/build_form.gs.

Pre-declared analysis plan (decided before looking at any data)
---------------------------------------------------------------
Population: responses with consent = "Yes, I agree to take part" and a
clinic code of A or B. Non-consenters are counted and dropped.

Composites (one score per respondent; mean of the available items, so a
skipped item does not drop the person; missing only if every item is missing):
  * Understanding = mean(und_why, und_what, und_after, und_risks)   range 1-5
  * Confidence    = mean(conf_clear, conf_risks, conf_explain)       range 1-5
  * Satisfaction  = mean(sat_clear, sat_time, sat_overall)           range 1-5
  * Knowledge     = mean of four item scores, range 0-1:
      - k_reason, k_after, k_followup: 1 if the correct option is picked,
        0 otherwise ("I'm not sure" scores 0).
      - k_symptoms (select all that apply; 3 correct options, 1 wrong):
        (correct ticked - wrong ticked) / 3, floored at 0. If "I'm not sure"
        is ticked the item scores 0 whatever else is ticked.
    The rule lives in score_knowledge_item() only.
All 1-5 scales point the same way: 5 = best.

Primary comparison, A vs B, for each composite: n, median and IQR per group,
two-sided Mann-Whitney U, rank-biserial correlation (positive = A higher).
The four composites are ONE multiple-testing family; p-values are adjusted
with Benjamini-Hochberg FDR. If either group has fewer than 3 respondents the
tests are skipped and only descriptives are reported.

Secondary (descriptive only, no p-values): per-item medians / means for every
1-5 item and % correct / % "I'm not sure" for each knowledge item.

Outputs in --out: summary_by_group.csv, item_level.csv, open_text.csv,
report.md, composites_by_group.png and composites_by_group.pdf.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from scipy.stats import mannwhitneyu  # noqa: E402
from statsmodels.stats.multitest import multipletests  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_KEY = HERE / "answer_key.json"
SEED = 42
MIN_N_FOR_TEST = 3
GROUPS = ("A", "B")
# Neutral two-colour palette (grey-blue / sand). Change here only.
GROUP_COLOURS = {"A": "#4C6A8A", "B": "#B59A6A"}


class SurveyFormatError(ValueError):
    """The CSV does not match answer_key.json."""


# --------------------------------------------------------------------------- key
def load_key(path: Path = DEFAULT_KEY) -> dict:
    key = json.loads(Path(path).read_text(encoding="utf-8"))
    key["by_code"] = {q["code"]: q for q in key["questions"]}
    return key


# ------------------------------------------------------------------ loading CSV
def load_responses(csv_path: Path, key: dict, ignore_extra: bool = False) -> pd.DataFrame:
    """Read the Sheets CSV and rename title columns to question codes."""
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda s: s.str.strip())
    df = df.replace("", np.nan)

    ts = key["timestamp_column"]
    expected = [ts] + [q["title"] for q in key["questions"]]
    missing = [c for c in expected if c not in df.columns]
    extra = [c for c in df.columns if c not in expected]
    if missing or (extra and not ignore_extra):
        lines = ["The CSV columns do not match survey/answer_key.json."]
        if missing:
            lines.append("Missing columns (expected but not found):")
            lines += [f"  - {c!r}" for c in missing]
        if extra:
            lines.append("Unexpected columns (found but not in answer_key.json):")
            lines += [f"  - {c!r}" for c in extra]
        lines.append(
            "Likely causes: a question title was edited in the form or the Sheet but not in "
            "answer_key.json (or vice versa), or the wrong CSV was downloaded. Titles must "
            "match word for word. Use --ignore-extra to skip unexpected columns."
        )
        raise SurveyFormatError("\n".join(lines))

    rename = {q["title"]: q["code"] for q in key["questions"]}
    rename[ts] = "timestamp"
    return df[expected].rename(columns=rename)


# --------------------------------------------------------------------- scoring
def split_checkbox(cell, options: list[str]) -> list[str]:
    """Split a Google Sheets checkbox cell ("opt1, opt2") against the known options.

    Matching is done against the known option list (longest first) rather than
    a naive split on ", ", so options that contain commas still work. Raises
    SurveyFormatError if anything is left over.
    """
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    rest = ", " + str(cell).strip() + ", "
    found = []
    for opt in sorted(options, key=len, reverse=True):
        token = ", " + opt + ", "
        if token in rest:
            found.append(opt)
            rest = rest.replace(token, ", ", 1)
    if rest.strip(", ").strip():
        raise SurveyFormatError(
            f"Checkbox answer contains unknown text {rest.strip(', ')!r}; "
            f"known options are {options}."
        )
    return [o for o in options if o in found]  # form order


def score_knowledge_item(q: dict, answer) -> float:
    """Score one knowledge item (0-1). NaN if unanswered. See module docstring."""
    if q["type"] == "checkbox":
        ticked = split_checkbox(answer, q["options"])
        if not ticked:
            return np.nan
        if q["not_sure"] in ticked:
            return 0.0
        correct = set(q["correct"])
        n_right = sum(o in correct for o in ticked)
        n_wrong = sum(o not in correct for o in ticked)
        return max(0.0, (n_right - n_wrong) / len(correct))
    if answer is None or (isinstance(answer, float) and np.isnan(answer)):
        return np.nan
    if answer not in q["options"]:
        raise SurveyFormatError(f"{q['code']}: unknown answer {answer!r}")
    return 1.0 if answer in q["correct"] else 0.0


def is_not_sure(q: dict, answer) -> float:
    if answer is None or (isinstance(answer, float) and np.isnan(answer)):
        return np.nan
    if q["type"] == "checkbox":
        return float(q["not_sure"] in split_checkbox(answer, q["options"]))
    return float(answer == q["not_sure"])


def prepare(df: pd.DataFrame, key: dict) -> tuple[pd.DataFrame, dict]:
    """Filter to consenters with a valid group, score items, add composites."""
    c = key["consent"]
    counts = {"rows": len(df)}
    counts["declined"] = int((df[c["code"]] == c["no"]).sum())
    consent_ok = df[c["code"]] == c["yes"]
    counts["consent_blank_or_other"] = int((~consent_ok).sum()) - counts["declined"]
    df = df[consent_ok].copy()
    counts["consented"] = len(df)

    g = key["groups"]["code"]
    bad_group = ~df[g].isin(GROUPS)
    counts["no_valid_group"] = int(bad_group.sum())
    df = df[~bad_group].copy()
    counts["analysed"] = len(df)
    counts["by_group"] = {grp: int((df[g] == grp).sum()) for grp in GROUPS}

    for q in key["questions"]:
        code = q["code"]
        if q["type"] == "scale":
            vals = pd.to_numeric(df[code], errors="coerce")
            bad = df[code].notna() & ~vals.between(q["scale"]["min"], q["scale"]["max"])
            if bad.any():
                raise SurveyFormatError(f"{code}: values outside 1-5: {sorted(df.loc[bad, code].unique())}")
            df[code] = vals
        elif "correct" in q:
            df[code + "_score"] = [score_knowledge_item(q, a) for a in df[code]]
            df[code + "_notsure"] = [is_not_sure(q, a) for a in df[code]]

    for name, codes in key["composites"].items():
        cols = [c_ + "_score" if "correct" in key["by_code"][c_] else c_ for c_ in codes]
        df[name] = df[cols].mean(axis=1, skipna=True)
    return df, counts


# ------------------------------------------------------------------- statistics
def rank_biserial(u_a: float, n_a: int, n_b: int) -> float:
    """Rank-biserial correlation from U of group A; +1 = every A above every B."""
    return 2.0 * u_a / (n_a * n_b) - 1.0


def compare_composites(df: pd.DataFrame, key: dict) -> tuple[pd.DataFrame, bool]:
    g = key["groups"]["code"]
    rows = []
    for name in key["composites"]:
        row = {"composite": name}
        xs = {}
        for grp in GROUPS:
            x = df.loc[df[g] == grp, name].dropna().to_numpy()
            xs[grp] = x
            row[f"n_{grp}"] = len(x)
            row[f"median_{grp}"] = np.median(x) if len(x) else np.nan
            row[f"q1_{grp}"] = np.percentile(x, 25) if len(x) else np.nan
            row[f"q3_{grp}"] = np.percentile(x, 75) if len(x) else np.nan
            row[f"mean_{grp}"] = x.mean() if len(x) else np.nan
        if min(len(xs["A"]), len(xs["B"])) >= MIN_N_FOR_TEST:
            res = mannwhitneyu(xs["A"], xs["B"], alternative="two-sided")
            row["U_A"] = float(res.statistic)
            row["p"] = float(res.pvalue)
            row["rank_biserial"] = rank_biserial(res.statistic, len(xs["A"]), len(xs["B"]))
        else:
            row["U_A"] = row["p"] = row["rank_biserial"] = np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    tested = out["p"].notna()
    out["p_fdr"] = np.nan
    if tested.any():
        out.loc[tested, "p_fdr"] = multipletests(out.loc[tested, "p"], method="fdr_bh")[1]
    return out, bool(tested.all())


def item_level(df: pd.DataFrame, key: dict) -> pd.DataFrame:
    """Secondary, descriptive per-item table (no p-values)."""
    g = key["groups"]["code"]
    rows = []
    for q in key["questions"]:
        if q["type"] != "scale" and "correct" not in q:
            continue
        for grp in GROUPS:
            sub = df[df[g] == grp]
            row = {"code": q["code"], "title": q["title"], "group": grp}
            if q["type"] == "scale":
                x = sub[q["code"]].dropna()
                row.update(n=len(x), median=x.median(), q1=x.quantile(0.25),
                           q3=x.quantile(0.75), mean=x.mean())
            else:
                s = sub[q["code"] + "_score"].dropna()
                ns = sub[q["code"] + "_notsure"].dropna()
                row.update(n=len(s), mean_score=s.mean(),
                           pct_fully_correct=100 * (s == 1).mean() if len(s) else np.nan,
                           pct_not_sure=100 * ns.mean() if len(ns) else np.nan)
            rows.append(row)
    return pd.DataFrame(rows)


def demographics_table(df: pd.DataFrame, key: dict) -> pd.DataFrame:
    g = key["groups"]["code"]
    rows = []
    for code in ("respondent", "age", "prior_proc", "familiarity"):
        q = key["by_code"][code]
        for opt in q["options"] + ["(blank)"]:
            row = {"question": q["title"], "answer": opt}
            for grp in GROUPS:
                col = df.loc[df[g] == grp, code]
                row[grp] = int(col.isna().sum() if opt == "(blank)" else (col == opt).sum())
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------- figure
def _font_family() -> str:
    names = {f.name for f in font_manager.fontManager.ttflist}
    return "Arial" if "Arial" in names else "DejaVu Sans"


def plot_composites(df: pd.DataFrame, key: dict, out_dir: Path) -> None:
    g = key["groups"]["code"]
    labels = key["groups"]["labels"]
    rng = np.random.default_rng(SEED)
    with plt.rc_context({"font.family": _font_family(), "font.size": 8,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42}):
        fig, axes = plt.subplots(2, 2, figsize=(6.0, 5.0))
        for ax, name in zip(axes.ravel(), key["composites"]):
            data = [df.loc[df[g] == grp, name].dropna().to_numpy() for grp in GROUPS]
            pos = np.arange(1, len(GROUPS) + 1)
            nonempty = [i for i, d in enumerate(data) if len(d)]
            if nonempty:
                ax.boxplot([data[i] for i in nonempty], positions=pos[nonempty], widths=0.5,
                           showfliers=False, medianprops={"color": "black"},
                           boxprops={"color": "0.3"}, whiskerprops={"color": "0.3"},
                           capprops={"color": "0.3"})
            for i, grp in enumerate(GROUPS):
                x = pos[i] + rng.uniform(-0.12, 0.12, size=len(data[i]))
                ax.scatter(x, data[i], s=14, alpha=0.8, color=GROUP_COLOURS[grp],
                           edgecolor="white", linewidth=0.4, zorder=3)
            ax.set_xticks(pos)
            ax.set_xticklabels([f"{grp}\n{labels.get(grp, '')}\n(n={len(d)})"
                                for grp, d in zip(GROUPS, data)])
            ax.set_title(name, fontsize=9)
            if name == "Knowledge":
                ax.set_ylim(-0.05, 1.05)
                ax.set_ylabel("Score (0-1)")
            else:
                ax.set_ylim(0.8, 5.2)
                ax.set_yticks([1, 2, 3, 4, 5])
                ax.set_ylabel("Mean rating (1-5, 5 = best)")
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(out_dir / f"composites_by_group.{ext}", dpi=300)
        plt.close(fig)


# ---------------------------------------------------------------------- report
def _fmt(x, nd=2):
    return "–" if pd.isna(x) else f"{x:.{nd}f}"


def _fmt_p(p):
    if pd.isna(p):
        return "not tested"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def write_report(path: Path, counts: dict, summary: pd.DataFrame, items: pd.DataFrame,
                 demo: pd.DataFrame, all_tested: bool, key: dict, n_open: int) -> None:
    labels = key["groups"]["labels"]
    nA, nB = counts["by_group"]["A"], counts["by_group"]["B"]
    L = ["# Patient education survey: Group A vs Group B", ""]
    L += [f"- Group A = {labels['A']}; Group B = {labels['B']}.",
          f"- Responses in file: {counts['rows']}. Declined consent: {counts['declined']}. "
          f"Consent blank/other: {counts['consent_blank_or_other']}. "
          f"Consented but no valid clinic code: {counts['no_valid_group']}.",
          f"- **Analysed: {counts['analysed']} (A = {nA}, B = {nB}).**", ""]
    L += ["## Main results (pre-declared composites)", "",
          "Median [IQR] per group. Understanding, Confidence and Satisfaction are 1-5 "
          "(5 = best); Knowledge is 0-1 (share of the key facts answered correctly). "
          "p = Mann-Whitney U, two-sided; p (FDR) = Benjamini-Hochberg across the 4 "
          "composites; effect = rank-biserial correlation (positive = A higher; "
          "about 0.1 small, 0.3 medium, 0.5 large).", "",
          "| Composite | A | B | Effect | p | p (FDR) |", "|---|---|---|---|---|---|"]
    for _, r in summary.iterrows():
        L.append(f"| {r['composite']} | {_fmt(r['median_A'])} [{_fmt(r['q1_A'])}–{_fmt(r['q3_A'])}] "
                 f"(n={r['n_A']}) | {_fmt(r['median_B'])} [{_fmt(r['q1_B'])}–{_fmt(r['q3_B'])}] "
                 f"(n={r['n_B']}) | {_fmt(r['rank_biserial'])} | {_fmt_p(r['p'])} | {_fmt_p(r['p_fdr'])} |")
    L.append("")
    if not all_tested:
        L += [f"**Statistical tests were skipped for at least one composite because a group "
              f"had fewer than {MIN_N_FOR_TEST} responses.** Only descriptives are shown.", ""]
    L += ["Figure: `composites_by_group.png` / `.pdf` (box = IQR, line = median, dots = people).", ""]

    L += ["## Knowledge questions (descriptive)", "",
          "| Question | Group | n | Fully correct | Picked \"I'm not sure\" |", "|---|---|---|---|---|"]
    for _, r in items[items["code"].str.startswith("k_")].iterrows():
        L.append(f"| {r['code']} | {r['group']} | {r['n']} | {_fmt(r['pct_fully_correct'], 0)}% "
                 f"| {_fmt(r['pct_not_sure'], 0)}% |")
    L += ["", "Per-item ratings for every 1-5 question are in `item_level.csv` "
          "(descriptive only, no p-values).", ""]

    L += ["## Who answered (optional questions)", "", "| Question | Answer | A | B |", "|---|---|---|---|"]
    for _, r in demo.iterrows():
        L.append(f"| {r['question']} | {r['answer']} | {r['A']} | {r['B']} |")
    L += ["", f"Open-text answers: {n_open} non-blank, saved in `open_text.csv`. Read them "
          "before sharing: patients sometimes type names or other identifying details.", ""]

    L += ["## How to read this (caveats)", "",
          "- This is a quality-improvement survey, not a trial. Patients were not randomised: "
          "which discussion they got depended on the clinic visit, so groups may differ in "
          "other ways (diagnosis, prior procedures, who they saw, family present).",
          "- Numbers are small. A non-significant p-value does not show the two approaches "
          "are equal; look at the effect size and the spread of the dots.",
          "- Answers are self-reported and given right after the discussion; they show "
          "short-term understanding, not long-term recall.",
          "- Staff chose the A or B link. If the wrong QR code was used, that response is "
          "in the wrong group and cannot be fixed afterwards (the survey is anonymous).",
          "- Some forms may have been filled in by a family member (see 'Who is filling "
          "out this form?').",
          "- Knowledge scoring rule (decided in advance): one point per correct single "
          "answer; the symptoms question scores (correct ticked - wrong ticked) / 3, "
          "floored at 0, and 0 if \"I'm not sure\" is ticked.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------------ main
def run(csv_path: Path, out_dir: Path, key_path: Path = DEFAULT_KEY,
        ignore_extra: bool = False) -> dict:
    key = load_key(key_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = load_responses(csv_path, key, ignore_extra=ignore_extra)
    df, counts = prepare(raw, key)

    summary, all_tested = compare_composites(df, key)
    items = item_level(df, key)
    demo = demographics_table(df, key)
    g = key["groups"]["code"]
    open_text = df.melt(id_vars=[g], value_vars=["open_help", "open_feedback"],
                        var_name="question", value_name="answer").dropna(subset=["answer"])

    summary.to_csv(out_dir / "summary_by_group.csv", index=False)
    items.to_csv(out_dir / "item_level.csv", index=False)
    open_text.to_csv(out_dir / "open_text.csv", index=False)
    plot_composites(df, key, out_dir)
    write_report(out_dir / "report.md", counts, summary, items, demo, all_tested, key, len(open_text))
    return {"counts": counts, "summary": summary, "all_tested": all_tested, "data": df}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv", type=Path, help="CSV downloaded from the response Google Sheet")
    ap.add_argument("--out", type=Path, default=HERE / "results", help="output folder")
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY, help="answer_key.json")
    ap.add_argument("--ignore-extra", action="store_true",
                    help="ignore CSV columns that are not in answer_key.json")
    args = ap.parse_args(argv)
    try:
        res = run(args.csv, args.out, args.key, args.ignore_extra)
    except SurveyFormatError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    c = res["counts"]
    print(f"Rows {c['rows']} | declined {c['declined']} | analysed {c['analysed']} "
          f"(A={c['by_group']['A']}, B={c['by_group']['B']})")
    for _, r in res["summary"].iterrows():
        print(f"  {r['composite']:<13} median A {_fmt(r['median_A'])} vs B {_fmt(r['median_B'])}"
              f"  r_rb {_fmt(r['rank_biserial'])}  p_FDR {_fmt_p(r['p_fdr'])}")
    if not res["all_tested"]:
        print(f"  Tests skipped where a group had < {MIN_N_FOR_TEST} responses.")
    print(f"Outputs written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
