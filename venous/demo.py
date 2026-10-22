"""Example readings for training and demos: a right lateral transverse sinus
stenosis with typical values from published IIH series (not a real patient)."""
from __future__ import annotations

from .anatomy import MIDLINE, Measurement, convert

SIDE = "Right"

# location: (before stent, after stent), mmHg
EXAMPLE_MMHG = {
    "Superior sagittal sinus": (32, 15),
    "Torcula": (31, 15),
    "Transverse sinus (medial)": (31, 15),
    "Transverse sinus (mid)": (30, 14),
    "Transverse sinus (lateral)": (29, 14),
    "Transverse-sigmoid junction": (12, 13),
    "Sigmoid sinus": (11, 12),
    "Jugular bulb": (9, 10),
    "Internal jugular vein": (7, 8),
}


def _whole(v, unit):
    return None if v is None else float(round(convert(v, "mmHg", unit)))


def example_values(unit: str = "mmHg") -> dict[str, dict[str, float | None]]:
    """{location: {"pre": value, "post": value}} in the given unit (whole numbers)."""
    return {loc: {"pre": _whole(a, unit), "post": _whole(b, unit)}
            for loc, (a, b) in EXAMPLE_MMHG.items()}


def example_measurements(unit: str = "mmHg") -> list[Measurement]:
    return [Measurement(loc, "" if loc in MIDLINE else SIDE, v["pre"], v["post"])
            for loc, v in example_values(unit).items()]
