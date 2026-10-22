"""Real venous sinus anatomy, painted with the patient's pressures.

The anatomy is one open-data head CT angiogram (TopBrain 2025, University
Hospital Zurich; built by tools/build_example_scan.py), not the patient's own
scan. This module turns the readings into what the browser viewer
(viewer3d.html, three.js) draws: colours along the real sinus, the narrowing,
the stent, labels, the blood-flow paths, the skull and CT slices.

Each reading sits at a fixed point on the traced drainage path (ANCHORS).
Pressure is interpolated along the path. The narrowing is placed halfway
between the two neighbouring readings with the largest fall
(anatomy.find_stenosis), where the pressure drops sharply. Parts of the sinus
with no readings stay grey.
"""
from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .anatomy import (MIDLINE, PATH, PLAIN, Measurement, Stenosis, convert, find_stenosis,
                      from_mmhg, to_mmhg)
from .render import CMAP, NORM, SCALE_MAX, SCALE_MIN

DATA = Path(__file__).parent / "data" / "example_scan.npz"
TEMPLATE = Path(__file__).parent / "viewer3d.html"
SIDES = ("Left", "Right")
GREY = (139, 149, 165)
NARROW = 0.62      # how far the wall is pulled in at the narrowing (fraction of radius)
Q_STENOSED = 0.55  # relative flow on the narrowed side before stenting (illustration)

# Where each reading sits: (part of the path, fraction along it).
# Parts: "sss" = front of the SSS -> torcula, "ts" = torcula -> transverse-sigmoid
# junction, "sig" = junction -> jugular bulb.
ANCHORS = {
    "Superior sagittal sinus": ("sss", 0.60),
    "Torcula": ("sss", 1.00),
    "Transverse sinus (medial)": ("ts", 0.25),
    "Transverse sinus (mid)": ("ts", 0.50),
    "Transverse sinus (lateral)": ("ts", 0.78),
    "Transverse-sigmoid junction": ("ts", 1.00),
    "Sigmoid sinus": ("sig", 0.50),
    "Jugular bulb": ("sig", 1.00),
    "Internal jugular vein": ("sig", 1.00),  # below the scan; label sits under the bulb
}


@lru_cache(maxsize=1)
def scan() -> dict:
    with np.load(DATA) as z:
        d = {k: z[k] for k in z.files}
    d["paths"] = {"Left": d["path_left"], "Right": d["path_right"]}
    d["lms"] = {"Left": d["lm_left"], "Right": d["lm_right"]}
    d["radius"] = {s: _radius_along(d, i) for i, s in enumerate(SIDES)}
    return d


def credit() -> str:
    return str(scan()["source"])


def _radius_along(d, s_i) -> np.ndarray:
    """Median distance from path point to the vessel wall, smoothed."""
    path = d["paths"][SIDES[s_i]]
    on = d["v_side"] == s_i
    dist = np.linalg.norm(d["verts"][on] - path[d["v_idx"][on]], axis=1)
    r = np.full(len(path), np.nan)
    for i in range(len(path)):
        sel = dist[d["v_idx"][on] == i]
        if len(sel):
            r[i] = np.median(sel)
    idx = np.arange(len(r))
    ok = ~np.isnan(r)
    r = np.interp(idx, idx[ok], r[ok])
    return np.convolve(np.pad(r, 3, mode="edge"), np.ones(7) / 7, mode="valid")


def _index(side: str, location: str) -> float:
    torc, tsj, end = scan()["lms"][side]
    part, f = ANCHORS[location]
    lo, hi = {"sss": (0, torc), "ts": (torc, tsj), "sig": (tsj, end)}[part]
    return lo + f * (hi - lo)


def _narrowing(side: str, sten: Stenosis) -> tuple[float, float]:
    """(path index of the narrowing, its half-width in path points)."""
    a, b = _index(side, sten.up), _index(side, sten.down)
    return (a + b) / 2, max(3.0, (b - a) / 4)


# --------------------------------------------------------------------------- #
# Readings -> pressure along the path
# --------------------------------------------------------------------------- #
def _values(ms, sten, after, unit) -> dict[str, float]:
    """{location: value in the case unit} before or after stenting. Missing
    after-stent readings are illustrated: the drop collapses, so readings above
    the narrowing fall to just above the reading below it."""
    out = {}
    order = {loc: i for i, loc in enumerate(PATH)}
    for m in ms:
        if m.pressure is None or m.location not in ANCHORS:
            continue
        v = m.pressure
        if after:
            if m.post is not None:
                v = m.post
            elif sten is not None and order[m.location] < order[sten.down]:
                v = min(v, sten.post + convert(2.0, "mmHg", unit))
        out[m.location] = v
    return out


def _profile(side, values_mmhg, sten, stented) -> np.ndarray | None:
    n = len(scan()["paths"][side])
    pts = sorted((_index(side, loc), v) for loc, v in values_mmhg.items())
    if not pts:
        return None
    xs, vs = map(np.array, zip(*pts))
    idx = np.arange(n)
    p = np.interp(idx, xs, vs)
    if sten is not None and not stented:
        a, b = _index(side, sten.up), _index(side, sten.down)
        mid = (a + b) / 2
        gap = (idx > a) & (idx < b)
        p[gap] = np.where(idx[gap] < mid, values_mmhg[sten.up], values_mmhg[sten.down])
    return p


def _colours(values_mmhg, side, sten, stented, straight) -> np.ndarray:
    """RGB per vertex. Midline readings colour the SSS on both paths; side
    readings colour only the side they were taken on."""
    d = scan()
    side_of, idx_of = d["v_side"], d["v_idx"]
    mmhg = np.full(len(side_of), np.nan)
    mid_only = {k: v for k, v in values_mmhg.items() if k in MIDLINE}
    for s_i, s in enumerate(SIDES):
        vals = values_mmhg if s == side else mid_only
        prof = _profile(s, vals, sten if s == side else None, stented)
        if prof is None:
            continue
        ok = side_of == s_i
        has_own = s == side and any(k not in MIDLINE for k in values_mmhg)
        if not has_own:                                 # unmeasured side: only the SSS part
            ok &= idx_of <= d["lms"][s][0]
        mmhg[ok] = prof[idx_of[ok]]
    if straight is not None:
        mmhg[side_of == 2] = straight
    rgb = (CMAP(NORM(np.nan_to_num(mmhg)))[:, :3] * 255).astype(np.uint8)
    rgb[np.isnan(mmhg)] = GREY
    return rgb


def _narrowed(verts, side, sten):
    d = scan()
    s_i = SIDES.index(side)
    out = verts.copy()
    on = d["v_side"] == s_i
    centre_idx, width = _narrowing(side, sten)
    w = np.exp(-((d["v_idx"][on] - centre_idx) / width) ** 2)
    centre = d["paths"][side][d["v_idx"][on]]
    out[on] = centre + (verts[on] - centre) * (1 - NARROW * w)[:, None]
    return out


def _frames(path):
    t = np.gradient(path, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    ref = np.where(np.abs(t[:, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])
    a = np.cross(t, ref)
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    return t, a, np.cross(t, a)


def _stent_lines(side, centre_idx, half_len, r):
    path = scan()["paths"][side]
    _, a, b = _frames(path)
    lines = []
    for phase in np.linspace(0, 2 * np.pi, 7)[:-1]:
        for direction in (1, -1):
            pts = []
            for q, ii in enumerate(np.arange(centre_idx - half_len, centre_idx + half_len + 0.01, 0.5)):
                i = int(np.clip(round(ii), 0, len(path) - 1))
                ang = phase + direction * q * 0.24
                pts.append(path[i] + (r + 0.5) * (np.cos(ang) * a[i] + np.sin(ang) * b[i]))
            lines.append(np.round(np.array(pts), 2).tolist())
    return lines


def _labels(values, side, unit):
    """Value labels: a whole number and a plain place name, nothing else."""
    d = scan()
    out, seen = [], set()
    for loc in PATH:
        if loc not in values:
            continue
        s = side if loc not in MIDLINE else "Right"
        p = d["paths"][s][int(round(_index(s, loc)))].copy()
        if loc == "Internal jugular vein":
            p[2] -= 16
        out_dir = p - np.array([0.0, -20.0, p[2] * 0.3])
        out_dir /= max(np.linalg.norm(out_dir), 1e-6)
        anchor = p.copy()
        p = p + out_dir * (14 + 7 * (len(out) % 2))
        place = PLAIN[loc]
        rgb = CMAP(NORM(to_mmhg(values[loc], unit)))[:3]
        out.append({"p": np.round(p, 1).tolist(), "a": np.round(anchor, 1).tolist(),
                    "value": f"{round(values[loc]):g}", "place": "" if place in seen else place,
                    "title": f"{loc}: {values[loc]:g} {unit}",
                    "colour": "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)})
        seen.add(place)
    return out


# --------------------------------------------------------------------------- #
# Payload for the browser viewer
# --------------------------------------------------------------------------- #
def _b64(a: np.ndarray, dtype) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()


def viewer_payload(ms: list[Measurement], unit: str, side: str) -> dict:
    """Everything viewer3d.html needs."""
    d = scan()
    side = side if side in SIDES else "Right"
    sten = find_stenosis(ms, unit)
    before, after = _values(ms, sten, False, unit), _values(ms, sten, True, unit)
    illustrative = any(m.post is None for m in ms if m.pressure is not None)
    to_m = lambda vals: {k: to_mmhg(v, unit) for k, v in vals.items()}  # noqa: E731
    straight = next((to_mmhg(m.pressure, unit) for m in ms
                     if m.location == "Straight sinus" and m.pressure is not None), None)

    verts = d["verts"]
    path = d["paths"][side]
    t, _, _ = _frames(path)
    paths, sten_info, stent = [], None, []
    centre_idx = width = None
    if sten is not None:
        centre_idx, width = _narrowing(side, sten)
        r_here = float(d["radius"][side][int(round(centre_idx))])
        sten_info = {"pos": np.round(path[int(round(centre_idx))], 2).tolist(),
                     "dir": np.round(t[int(round(centre_idx))], 4).tolist(), "r": r_here,
                     "where": (PLAIN[sten.up] if PLAIN[sten.up] == PLAIN[sten.down]
                               else f"Between {PLAIN[sten.up].lower()} and {PLAIN[sten.down].lower()}")}
        stent = _stent_lines(side, centre_idx, max(9.0, 1.6 * width), r_here)
    for s in SIDES:
        p = d["paths"][s]
        _, a, b = _frames(p)
        rad = d["radius"][s]
        rb = rad.copy()
        if sten is not None and s == side:
            rb = rad * (1 - NARROW * np.exp(-((np.arange(len(p)) - centre_idx) / width) ** 2))
        paths.append({"side": s, "n": len(p), "pts": _b64(p, np.float32),
                      "a": _b64(a, np.float32), "b": _b64(b, np.float32),
                      "r_before": _b64(rb, np.float32), "r_after": _b64(rad, np.float32),
                      "q_before": Q_STENOSED if (sten is not None and s == side) else 1.0,
                      "q_after": 1.0})

    def drop(vals):
        if sten is None or sten.up not in vals or sten.down not in vals:
            return None
        return f"{round(vals[sten.up] - vals[sten.down]):g} {unit}"

    ticks = [SCALE_MIN, (SCALE_MIN + SCALE_MAX) / 2, SCALE_MAX]
    return {
        "unit": unit, "side": side, "stenosis": sten_info, "illustrative": illustrative,
        "mesh": {"verts": _b64(verts, np.float32),
                 "verts_before": _b64(_narrowed(verts, side, sten) if sten else verts,
                                      np.float32),
                 "faces": _b64(d["faces"], np.uint32),
                 "colour_before": _b64(_colours(to_m(before), side, sten, False, straight),
                                       np.uint8),
                 "colour_after": _b64(_colours(to_m(after), side, sten, True, straight),
                                      np.uint8)},
        "stent": stent, "paths": paths,
        "labels_before": _labels(before, side, unit),
        "labels_after": _labels(after, side, unit),
        "drop_before": drop(before), "drop_after": drop(after),
        "skull": {"verts": _b64(d["skull_verts"], np.float32),
                  "faces": _b64(d["skull_faces"], np.uint32)},
        "vol": {"data": _b64(d["vol"], np.uint8), "shape": list(d["vol"].shape),
                "spacing": float(d["vol_spacing"]),
                "origin": [float(v) for v in d["vol_origin"]]},
        "scale": {"stops": ["#%02x%02x%02x" % tuple(int(c * 255) for c in CMAP(f)[:3])
                            for f in np.linspace(0, 1, 6)],
                  "ticks": [f"{from_mmhg(v, unit):.0f}" for v in ticks]},
    }


def viewer_html(payload: dict) -> str:
    return TEMPLATE.read_text().replace("__PAYLOAD__", json.dumps(payload))
