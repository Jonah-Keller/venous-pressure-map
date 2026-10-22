"""Records of a case: one flat row (for the study sheet and CSV) and an Excel file.

`long_format` uses the same column names and vocabulary as the NeuroVERT
venous_pressure pipeline (location, side, sub_location, phase, value, unit), so
app records can be stacked onto the report-derived data.
"""
from __future__ import annotations

import io

import pandas as pd

from .anatomy import CANONICAL, LOCATIONS, MIDLINE, Measurement, find_stenosis

APP_VERSION = "2026-10"


def _unit_ascii(unit: str) -> str:
    return unit.replace("₂", "2")


def record(measurements: list[Measurement], unit: str, side: str, study_id: str,
           date: str) -> dict:
    """One flat row per case. No names or MRNs: the study ID is mapped to the MRN
    in a separate, secure key file."""
    vals = {m.location: m for m in measurements}
    before = find_stenosis(measurements, unit)
    after = find_stenosis(measurements, unit, after=True)
    row = {"study_id": study_id, "procedure_date": date, "unit": _unit_ascii(unit),
           "side": side.lower()}
    for loc in LOCATIONS:
        key = "_".join(filter(None, CANONICAL[loc]))
        m = vals.get(loc)
        row[f"{key}_pre"] = None if m is None else m.pressure
        row[f"{key}_post"] = None if m is None else m.post
    row.update({
        "narrowing_between": f"{before.up} -> {before.down}" if before else None,
        "gradient_pre": before.drop if before else None,
        "gradient_post": after.drop if after else None,
        "app_version": APP_VERSION,
    })
    return row


def long_format(measurements: list[Measurement], unit: str) -> pd.DataFrame:
    rows = []
    for m in measurements:
        loc, sub = CANONICAL[m.location]
        side = m.side.lower() if m.side else ("midline" if m.location in MIDLINE else "unknown")
        for phase, value in (("pre_stent", m.pressure), ("post_stent", m.post)):
            if value is not None:
                rows.append({"location": loc, "side": side, "sub_location": sub or None,
                             "phase": phase, "value": value, "unit": _unit_ascii(unit)})
    return pd.DataFrame(rows, columns=["location", "side", "sub_location", "phase", "value", "unit"])


def csv_bytes(row: dict) -> bytes:
    return pd.DataFrame([row]).to_csv(index=False).encode()


def excel_bytes(measurements: list[Measurement], unit: str, row: dict) -> bytes:
    table = pd.DataFrame([{"Location": m.location, "Side": m.side,
                           f"Before stent ({unit})": m.pressure,
                           f"After stent ({unit})": m.post} for m in measurements])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        table.to_excel(xw, sheet_name="Readings", index=False)
        pd.DataFrame([row]).T.reset_index().set_axis(["Field", "Value"], axis=1).to_excel(
            xw, sheet_name="Record", index=False)
        long_format(measurements, unit).to_excel(xw, sheet_name="Long format", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col) + 2
                ws.column_dimensions[col[0].column_letter].width = min(width, 45)
    return buf.getvalue()
