"""Locations, units, and where the narrowing is.

The locations follow how venous manometry is recorded in our reports (NeuroVERT
`venous_pressure` repo, label_normalization.py), listed in the direction blood
flows: superior sagittal sinus -> torcula -> transverse sinus (medial, mid,
lateral) -> transverse-sigmoid junction -> sigmoid sinus -> jugular bulb ->
internal jugular vein.

The narrowing is not entered by hand: it is placed where the pressure falls the
most between two neighbouring readings (`find_stenosis`).
"""
from __future__ import annotations

from dataclasses import dataclass

LOCATIONS = [
    "Superior sagittal sinus",
    "Straight sinus",
    "Torcula",
    "Transverse sinus (medial)",
    "Transverse sinus (mid)",
    "Transverse sinus (lateral)",
    "Transverse-sigmoid junction",
    "Sigmoid sinus",
    "Jugular bulb",
    "Internal jugular vein",
]
# The drainage path the narrowing is searched along (the straight sinus joins
# at the torcula, so it is not on it).
PATH = [loc for loc in LOCATIONS if loc != "Straight sinus"]
MIDLINE = {"Superior sagittal sinus", "Straight sinus", "Torcula"}

# Table rows shown by default; the rest are under "More locations".
MAIN_ROWS = [loc for loc in PATH]
EXTRA_ROWS = ["Straight sinus"]

# Canonical names used by the venous_pressure pipeline: (location, sub_location).
CANONICAL = {
    "Superior sagittal sinus": ("superior_sagittal_sinus", ""),
    "Straight sinus": ("straight_sinus", ""),
    "Torcula": ("torcula", ""),
    "Transverse sinus (medial)": ("transverse_sinus", "medial"),
    "Transverse sinus (mid)": ("transverse_sinus", "mid"),
    "Transverse sinus (lateral)": ("transverse_sinus", "lateral"),
    "Transverse-sigmoid junction": ("transverse_sigmoid_junction", ""),
    "Sigmoid sinus": ("sigmoid_sinus", ""),
    "Jugular bulb": ("jugular_bulb", ""),
    "Internal jugular vein": ("internal_jugular_vein", ""),
}

# Plain names for anything a patient sees.
PLAIN = {
    "Superior sagittal sinus": "Top of the head",
    "Straight sinus": "Deep in the middle",
    "Torcula": "Back of the head",
    "Transverse sinus (medial)": "Back of the head",
    "Transverse sinus (mid)": "Back, toward the side",
    "Transverse sinus (lateral)": "Behind the ear",
    "Transverse-sigmoid junction": "Behind the ear",
    "Sigmoid sinus": "Behind the ear, lower",
    "Jugular bulb": "Base of the skull",
    "Internal jugular vein": "Neck",
}

# A fall of at least this much between neighbouring readings is shown as a
# narrowing. Kept low on purpose: this places the picture, it is not a
# treatment threshold.
MIN_DROP_MMHG = 4.0

# --------------------------------------------------------------------------- #
# Units. Our reports use cm H2O about 85% of the time; the literature uses mmHg.
# --------------------------------------------------------------------------- #
CMH2O_PER_MMHG = 1.3595
UNITS = ["cm H₂O", "mmHg"]
_RANGE_MMHG = (-10.0, 80.0)


def to_mmhg(value: float, unit: str) -> float:
    return value / CMH2O_PER_MMHG if unit == "cm H₂O" else value


def from_mmhg(value: float, unit: str) -> float:
    return value * CMH2O_PER_MMHG if unit == "cm H₂O" else value


def convert(value: float | None, src: str, dst: str) -> float | None:
    if value is None or src == dst:
        return value
    return round(from_mmhg(to_mmhg(value, src), dst), 1)


def valid_range(unit: str) -> tuple[float, float]:
    lo, hi = _RANGE_MMHG
    return round(from_mmhg(lo, unit)), round(from_mmhg(hi, unit))


@dataclass
class Measurement:
    """One reading. `pressure` is before stenting, `post` after (optional).
    Both are in the case's unit."""

    location: str
    side: str = ""
    pressure: float | None = None
    post: float | None = None

    @property
    def label(self) -> str:
        """e.g. 'Right sigmoid sinus'."""
        if not self.side:
            return self.location
        return f"{self.side} {self.location[0].lower()}{self.location[1:]}"


def flow_sorted(measurements: list[Measurement]) -> list[Measurement]:
    return sorted(measurements, key=lambda m: LOCATIONS.index(m.location))


@dataclass
class Stenosis:
    """The narrowing: between `up` and `down`, the neighbouring readings with
    the largest pressure fall."""

    up: str
    down: str
    pre: float   # pressure at `up`
    post: float  # pressure at `down`

    @property
    def drop(self) -> float:
        return round(self.pre - self.post, 1)


def find_stenosis(measurements: list[Measurement], unit: str,
                  after: bool = False) -> Stenosis | None:
    """Where the pressure falls the most between neighbouring readings on the
    drainage path. Returns None if no fall reaches MIN_DROP_MMHG.

    With after=True the same two locations are used (the narrowing is where it
    was before stenting) with the after-stent readings, if both were taken.
    """
    before = _largest_drop(measurements, unit)
    if before is None or not after:
        return before
    vals = {m.location: m.post for m in measurements}
    a, b = vals.get(before.up), vals.get(before.down)
    return None if a is None or b is None else Stenosis(before.up, before.down, a, b)


def _largest_drop(measurements, unit) -> Stenosis | None:
    on_path = [m for m in flow_sorted(measurements)
               if m.location in PATH and m.pressure is not None]
    best = None
    for a, b in zip(on_path, on_path[1:]):
        if best is None or a.pressure - b.pressure > best.drop:
            best = Stenosis(a.location, b.location, a.pressure, b.pressure)
    if best is None or to_mmhg(best.drop, unit) < MIN_DROP_MMHG:
        return None
    return best
