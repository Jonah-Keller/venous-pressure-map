"""Tests for the patient-education survey (survey/).

Run: .venv/bin/python -m pytest tests/test_survey_analysis.py -q
"""
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SURVEY_DIR = Path(__file__).resolve().parents[1] / "survey"
sys.path.insert(0, str(SURVEY_DIR))
import analyze_survey as az  # noqa: E402

GS = SURVEY_DIR / "build_form.gs"
SYNTHETIC = SURVEY_DIR / "example_responses_SYNTHETIC.csv"


@pytest.fixture(scope="module")
def key():
    return az.load_key()


def gs_items():
    """Read the SURVEY block out of build_form.gs (it is kept as valid JSON)."""
    src = GS.read_text(encoding="utf-8")
    m = re.search(r"const SURVEY = (\{.*?\});\s*// =+ END SURVEY", src, re.S)
    assert m, "Could not find the SURVEY block (keep the BEGIN/END SURVEY markers)."
    try:
        survey = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        pytest.fail(f"SURVEY block in build_form.gs is not valid JSON ({e}). "
                    "Use double quotes, no trailing commas, no comments inside it.")
    return [it for sec in survey["sections"] for it in sec["items"]]


# ----------------------------------------------------------------- sync guards
def test_build_form_and_answer_key_in_sync(key):
    gs = [(i["code"], i["title"], i["type"], i.get("options")) for i in gs_items()]
    ak = [(q["code"], q["title"], q["type"], q.get("options")) for q in key["questions"]]
    assert gs == ak, "build_form.gs and answer_key.json differ (code/title/type/options, in order)."


def test_titles_unique_and_codes_known(key):
    titles = [q["title"] for q in key["questions"]]
    assert len(titles) == len(set(titles)), "Question titles must be unique (they are CSV headers)."
    for codes in key["composites"].values():
        assert set(codes) <= set(key["by_code"])


def test_correct_answers_are_real_options(key):
    for q in key["questions"]:
        if "correct" in q:
            assert set(q["correct"]) <= set(q["options"]), q["code"]
            assert q["not_sure"] in q["options"] and q["not_sure"] == q["options"][-1]
            assert q["not_sure"] not in q["correct"]


def test_group_meaning_not_in_form():
    src = GS.read_text(encoding="utf-8").lower()
    for leak in ("diagram", "visual", "verbal"):
        assert leak not in src, f"'{leak}' appears in build_form.gs; group meaning must stay out of the form."


def test_consent_no_ends_form():
    consent = next(i for i in gs_items() if i["code"] == "consent")
    assert consent["endFormOn"] == "No, I do not want to take part"


def test_checkbox_options_have_no_commas(key):
    for q in key["questions"]:
        if q["type"] == "checkbox":
            assert not any("," in o for o in q["options"])


# ---------------------------------------------------------------------- scoring
def test_single_choice_scoring(key):
    q = key["by_code"]["k_reason"]
    assert az.score_knowledge_item(q, q["correct"][0]) == 1.0
    wrong = next(o for o in q["options"] if o not in q["correct"] and o != q["not_sure"])
    assert az.score_knowledge_item(q, wrong) == 0.0
    assert az.score_knowledge_item(q, q["not_sure"]) == 0.0
    assert math.isnan(az.score_knowledge_item(q, np.nan))
    with pytest.raises(az.SurveyFormatError):
        az.score_knowledge_item(q, "Something not in the form")


@pytest.mark.parametrize("ticked, expected", [
    (["Headaches or pressure in the head", "A whooshing sound in the ear", "Blurry vision or other vision problems"], 1.0),
    (["Headaches or pressure in the head", "A whooshing sound in the ear", "Blurry vision or other vision problems",
      "Stomach pain"], 2 / 3),
    (["Blurry vision or other vision problems"], 1 / 3),
    (["Blurry vision or other vision problems", "Stomach pain"], 0.0),
    (["Stomach pain"], 0.0),
    (["I'm not sure"], 0.0),
    (["Headaches or pressure in the head", "I'm not sure"], 0.0),
])
def test_symptoms_checkbox_rule(key, ticked, expected):
    q = key["by_code"]["k_symptoms"]
    cell = ", ".join(ticked)
    assert az.score_knowledge_item(q, cell) == pytest.approx(expected)


def test_symptoms_blank_is_missing(key):
    assert math.isnan(az.score_knowledge_item(key["by_code"]["k_symptoms"], np.nan))


def test_split_checkbox_handles_commas_inside_options():
    opts = ["Red, dark", "Red", "Blue"]
    assert az.split_checkbox("Red, dark, Blue", opts) == ["Red, dark", "Blue"]
    assert az.split_checkbox("Red, Blue", opts) == ["Red", "Blue"]
    with pytest.raises(az.SurveyFormatError):
        az.split_checkbox("Red, Green", opts)


def test_rank_biserial_bounds():
    assert az.rank_biserial(9, 3, 3) == 1.0
    assert az.rank_biserial(0, 3, 3) == -1.0
    assert az.rank_biserial(4.5, 3, 3) == 0.0


# --------------------------------------------------------------- input checking
def test_missing_column_message(tmp_path, key):
    df = pd.read_csv(SYNTHETIC, dtype=str)
    bad = df.rename(columns={key["by_code"]["und_why"]["title"]: "I understand why (edited)"})
    p = tmp_path / "bad.csv"
    bad.to_csv(p, index=False)
    with pytest.raises(az.SurveyFormatError) as e:
        az.load_responses(p, key)
    msg = str(e.value)
    assert "Missing columns" in msg and "Unexpected columns" in msg and "(edited)" in msg


def test_small_group_skips_tests(tmp_path, key):
    df = pd.read_csv(SYNTHETIC, dtype=str, keep_default_na=False)
    grp = key["by_code"]["group"]["title"]
    keep_b = df.index[df[grp] == "B"][:2]
    small = df[(df[grp] != "B") | df.index.isin(keep_b)]
    p = tmp_path / "small.csv"
    small.to_csv(p, index=False)
    res = az.run(p, tmp_path / "out")
    assert res["counts"]["by_group"]["B"] == 2
    assert not res["all_tested"]
    assert res["summary"]["p"].isna().all()
    assert "skipped" in (tmp_path / "out" / "report.md").read_text()


# ------------------------------------------------------------------ end to end
def test_end_to_end_synthetic(tmp_path):
    out = tmp_path / "results"
    assert az.main([str(SYNTHETIC), "--out", str(out)]) == 0
    for f in ("summary_by_group.csv", "item_level.csv", "open_text.csv", "report.md",
              "composites_by_group.png", "composites_by_group.pdf"):
        assert (out / f).exists(), f
    summary = pd.read_csv(out / "summary_by_group.csv")
    assert list(summary["composite"]) == ["Understanding", "Knowledge", "Confidence", "Satisfaction"]
    assert summary["p_fdr"].notna().all()
    assert ((summary["p_fdr"] >= summary["p"] - 1e-12)).all()
    assert summary["rank_biserial"].between(-1, 1).all()
    res = az.run(SYNTHETIC, tmp_path / "again")
    c = res["counts"]
    assert c["declined"] == 2 and c["analysed"] == c["rows"] - 2
    k = res["data"]["Knowledge"]
    assert k.between(0, 1).all()


def test_survey_page_can_render_every_question():
    """survey.html reads the SURVEY block of build_form.gs; it supports these types."""
    import json
    gs = (Path(__file__).resolve().parents[1] / "survey" / "build_form.gs").read_text()
    a = gs.index("const SURVEY = ") + len("const SURVEY = ")
    survey = json.loads(gs[a:gs.index("// ===== END SURVEY =====")].strip().rstrip(";"))
    items = [it for sec in survey["sections"] for it in sec["items"]]
    assert {it["type"] for it in items} <= {"multiple_choice", "dropdown", "scale", "checkbox", "paragraph"}
    assert any(it["code"] == "group" for it in items)                  # staff pick A/B
    assert all("lowLabel" in it and "highLabel" in it for it in items if it["type"] == "scale")
    html = (Path(__file__).resolve().parents[1] / "survey.html").read_text()
    assert "survey/build_form.gs" in html and "Timestamp" in html
