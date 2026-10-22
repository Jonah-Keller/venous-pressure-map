"""Shared look: the pressure colour scale, fonts, and saving figures.

Colour encodes pressure on a FIXED scale (SCALE_MIN..SCALE_MAX mmHg) so pictures
from different patients are directly comparable. Cool blue = low, red = high.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_hex  # noqa: E402

from .anatomy import to_mmhg  # noqa: E402

SCALE_MIN, SCALE_MAX = 0, 40  # mmHg; values outside are clipped to the end colours
CMAP = LinearSegmentedColormap.from_list(
    "venous", ["#2c7bb6", "#00a6ca", "#f9d057", "#f29e2e", "#d7191c"]
)
NORM = Normalize(SCALE_MIN, SCALE_MAX, clip=True)

INK = "#1b2533"
MUTED = "#5b6b7f"
PANEL_BG = "#f4f6fa"

FONT_FAMILY = ("Arial" if any(f.name == "Arial" for f in font_manager.fontManager.ttflist)
               else "DejaVu Sans")


def unit_label(unit: str) -> str:
    """Unit text for figures (Arial has no subscript-2 glyph)."""
    return "cm H$_2$O" if unit == "cm H₂O" else unit


def pressure_hex(p: float | None, unit: str = "mmHg") -> str:
    return "#8b95a5" if p is None else to_hex(CMAP(NORM(to_mmhg(p, unit))))


def handout_pdf(figs: list[plt.Figure]) -> bytes:
    """Several figures as pages of one PDF."""
    from matplotlib.backends.backend_pdf import PdfPages
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for f in figs:
            pdf.savefig(f, facecolor="white")
    return buf.getvalue()


def figure_bytes(fig: plt.Figure, fmt: str) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, dpi=200, facecolor="white")
    return buf.getvalue()
