"""Venous Pressure Map — Streamlit app.

Three steps: (1) type the venous manometry readings into a table, (2) show the
patient the 3D view (pressure colours, before/after stent, blood flow, and a
printable handout drawn in the same style), (3) save the case to the study sheet.

The narrowing is found from the readings (the largest drop between neighbouring
spots), not entered by hand.

Run locally:   streamlit run app.py      (website: index.html, see docs/HANDOFF.md)
Logic lives in venous/; this file is only the page. Nothing is kept after the
tab closes except what is saved to the study sheet.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from venous import anatomy, demo, export, sinus3d
from venous.anatomy import MIDLINE, PLAIN, Measurement, find_stenosis

st.set_page_config(page_title="Venous Pressure Map", page_icon=":material/vital_signs:",
                   layout="wide")

ROOT = Path(__file__).parent
CSS = """
<style>
.block-container {padding-top: 1.2rem; max-width: 1280px;}
/* No Streamlit header bar (Deploy / menu / sidebar arrow): the page has its own banner. */
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stDecoration"], [data-testid="stSidebar"] {display: none !important;}
.foot {color: #7a889b; font-size: .8rem; margin: 18px 4px 6px; line-height: 1.5;}
.hero {background: linear-gradient(120deg, #13294b 0%, #1f4e79 60%, #2c7bb6 100%);
  color: #fff; border-radius: 14px; padding: 20px 26px; margin-bottom: 16px;}
.hero h1 {color: #fff; font-size: 1.7rem; margin: 0 0 4px; padding: 0; font-weight: 700;}
.hero p {margin: 0; opacity: .88; font-size: .98rem;}
.sec {display: flex; align-items: center; gap: 10px; font-size: 1.15rem; font-weight: 700;
  color: #13294b; margin: 0 0 2px;}
.sec .n {width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center;
  background: #1f4e79; color: #fff; font-size: .9rem; flex: none;}
.hint {color: #5b6b7f; font-size: .92rem; margin: 2px 0 12px 38px;}
.th {font-size: .78rem; font-weight: 700; color: #5b6b7f; text-transform: uppercase;
  letter-spacing: .03em;}
.loc {font-size: .98rem; color: #1b2533; line-height: 1.2;}
.tag {display: inline-block; font-size: .72rem; font-weight: 700; color: #1f4e79;
  background: #e6eef8; border-radius: 6px; padding: 1px 6px; margin-right: 6px;}
.big {font-size: 2.1rem; font-weight: 800; color: #13294b; line-height: 1.1;}
.muted {color: #5b6b7f; font-size: .88rem;}
</style>
"""


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def init_state() -> None:
    for k, v in {"unit": "cm H₂O", "unit_choice": "cm H₂O", "side": "Right",
                 "side_choice": "Right", "vals": {}, "form_v": 0}.items():
        st.session_state.setdefault(k, v)


def change_unit() -> None:
    s = st.session_state
    if s.unit_choice is None:               # clicking the selected box again keeps it
        s.unit_choice = s.unit
        return
    s.vals = {loc: {k: anatomy.convert(v, s.unit, s.unit_choice) for k, v in d.items()}
              for loc, d in s.vals.items()}
    s.unit = s.unit_choice
    s.form_v += 1


def change_side() -> None:
    s = st.session_state
    if s.side_choice is None:
        s.side_choice = s.side
    else:
        s.side = s.side_choice


def load_example() -> None:
    s = st.session_state
    s.vals = demo.example_values(s.unit)
    s.side = s.side_choice = demo.SIDE
    s.form_v += 1


def clear_all() -> None:
    s = st.session_state
    s.vals = {}
    s.form_v += 1


def measurements() -> list[Measurement]:
    s = st.session_state
    return [Measurement(loc, "" if loc in MIDLINE else s.side, v["pre"], v.get("post"))
            for loc in anatomy.LOCATIONS
            if (v := s.vals.get(loc) or {}).get("pre") is not None]


def key_of(ms: list[Measurement]) -> tuple:
    return tuple((m.location, m.side, m.pressure, m.post) for m in ms)


def from_key(k: tuple) -> list[Measurement]:
    return [Measurement(*row) for row in k]


@st.cache_data(show_spinner="Building the 3D view…", max_entries=16)
def viewer(k: tuple, unit: str, side: str) -> str:
    return sinus3d.viewer_html(sinus3d.viewer_payload(from_key(k), unit, side))


def storage_endpoint() -> str:
    try:
        return json.loads((ROOT / "storage.json").read_text()).get("endpoint", "")
    except (OSError, ValueError):
        return ""


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def section(n: int, title: str, hint: str) -> None:
    st.markdown(f'<div class="sec"><span class="n">{n}</span>{title}</div>'
                f'<p class="hint">{hint}</p>', unsafe_allow_html=True)


def reading_row(loc: str, lo: float, hi: float) -> None:
    s = st.session_state
    c0, c1, c2 = st.columns([3, 1.4, 1.4], vertical_alignment="center")
    tag = "" if loc in MIDLINE else f'<span class="tag">{s.side}</span>'
    c0.markdown(f'<div class="loc">{tag}{loc}</div>', unsafe_allow_html=True)
    v = s.vals.get(loc, {})
    common = dict(min_value=float(lo), max_value=float(hi), step=1.0, format="%g",
                  label_visibility="collapsed")
    pre = c1.number_input(f"{loc} before", value=v.get("pre"), placeholder="—",
                          key=f"pre|{loc}|{s.form_v}", **common)
    post = c2.number_input(f"{loc} after", value=v.get("post"), placeholder="optional",
                           key=f"post|{loc}|{s.form_v}", **common)
    s.vals[loc] = {"pre": pre, "post": post}


def step_readings() -> None:
    s = st.session_state
    with st.container(border=True):
        section(1, "Enter the pressures",
                "Type each reading from the venogram report. Leave a box empty if it wasn't "
                "measured. The narrowing is found from the readings automatically.")
        c1, c2, c3, c4 = st.columns([1.3, 1.1, 1.5, 0.8], vertical_alignment="bottom")
        c1.segmented_control("Unit", anatomy.UNITS, key="unit_choice", on_change=change_unit)
        c2.segmented_control("Side measured", ["Right", "Left"], key="side_choice",
                             on_change=change_side)
        c3.button("Fill in example values", icon=":material/science:", on_click=load_example,
                  width="stretch")
        c4.button("Clear", icon=":material/restart_alt:", on_click=clear_all, width="stretch")

        left, right = st.columns([3, 1.3], gap="large")
        with left:
            h0, h1, h2 = st.columns([3, 1.4, 1.4])
            h0.markdown('<span class="th">Location (blood-flow order)</span>', unsafe_allow_html=True)
            h1.markdown('<span class="th">Before stent</span>', unsafe_allow_html=True)
            h2.markdown('<span class="th">After stent</span>', unsafe_allow_html=True)
            lo, hi = anatomy.valid_range(s.unit)
            for loc in anatomy.MAIN_ROWS:
                reading_row(loc, lo, hi)
            with st.expander("More locations"):
                for loc in anatomy.EXTRA_ROWS:
                    reading_row(loc, lo, hi)
        with right:
            summary_card()


def summary_card() -> None:
    s = st.session_state
    ms = measurements()
    before = find_stenosis(ms, s.unit)
    after = find_stenosis(ms, s.unit, after=True)
    with st.container(border=True):
        st.markdown('<span class="th">Narrowing</span>', unsafe_allow_html=True)
        if before:
            st.markdown(f'<div class="big">{before.drop:g} <span style="font-size:1rem">'
                        f'{s.unit}</span></div><div class="muted">drop between the '
                        f'<b>{before.up.lower()}</b> and the <b>{before.down.lower()}</b> '
                        f'({before.pre:g} → {before.post:g})</div>', unsafe_allow_html=True)
            if after:
                st.markdown(f'<div class="muted" style="margin-top:8px">After stent: '
                            f'<b>{after.drop:g} {s.unit}</b></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="muted">None found yet. It appears when two neighbouring '
                        f'readings differ by at least {anatomy.convert(anatomy.MIN_DROP_MMHG, "mmHg", s.unit):g} '
                        f'{s.unit}.</div>', unsafe_allow_html=True)
        n = len(ms)
        st.markdown(f'<div class="muted" style="margin-top:12px">{n} reading'
                    f'{"" if n == 1 else "s"} entered</div>', unsafe_allow_html=True)


def step_show(ms: list[Measurement]) -> None:
    s = st.session_state
    with st.container(border=True):
        section(2, "Show the patient",
                "Use the buttons on the picture: Before / After stent, Blood flow, Full screen. "
                "Drag to spin, scroll to zoom. **Handout** saves a printable page in the same "
                "style, from the angle you're looking at.")
        components.html(viewer(key_of(ms), s.unit, s.side), height=660)


def step_save(ms: list[Measurement]) -> None:
    s = st.session_state
    with st.container(border=True):
        section(3, "Save and download",
                "Save the readings under a study ID (never a name or MRN). The study ID ↔ MRN "
                "key is kept only in the secure team folder.")
        c1, c2, c3 = st.columns([1.2, 1, 2.2], vertical_alignment="bottom")
        study_id = c1.text_input("Study ID", placeholder="e.g. VP-0001").strip()
        date = c2.date_input("Procedure date", value=dt.date.today(), format="YYYY-MM-DD")
        ok_id = bool(re.fullmatch(r"[A-Za-z]{1,6}-?\d{1,6}", study_id))
        row = export.record(ms, s.unit, s.side, study_id, date.isoformat())
        with c3:
            save = {"endpoint": storage_endpoint(), "record": row, "ready": ok_id,
                    "why": "Enter a study ID like VP-0001 to save." if study_id == "" else
                           "Study IDs look like VP-0001 (letters, then numbers; no MRNs)."}
            html = (ROOT / "venous" / "save.html").read_text().replace("__SAVE__", json.dumps(save))
            components.html(html, height=90)
        name = study_id or "case"
        d2, d3, _ = st.columns(3)
        d2.download_button("Readings (CSV)", export.csv_bytes(row), f"venous_{name}_{date}.csv",
                           "text/csv", icon=":material/download:", width="stretch")
        d3.download_button("Readings (Excel)", export.excel_bytes(ms, s.unit, row),
                           f"venous_{name}_{date}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           icon=":material/table_view:", width="stretch")


def footer() -> None:
    st.markdown(
        '<div class="foot"><b>Privacy:</b> no names or MRNs. The app keeps nothing after the '
        "tab closes; only <b>Save</b> sends the readings, study ID and date to the team's study "
        "sheet.<br><b>Anatomy:</b> " + sinus3d.credit() + "</div>", unsafe_allow_html=True)


def main() -> None:
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero"><h1>Venous Pressure Map</h1>'
                '<p>Show a patient where the pressure builds up, where the vein narrows, '
                'and what a stent changes.</p></div>', unsafe_allow_html=True)
    step_readings()
    ms = measurements()
    if not ms:
        st.info("Enter at least one reading, or click **Fill in example values**.",
                icon=":material/arrow_upward:")
    else:
        step_show(ms)
        step_save(ms)
    footer()


main()
