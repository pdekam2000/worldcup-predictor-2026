"""PHASE ECSE-X3-A — Accepted composite signal calculator."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.research.ecse_x3.constants import ZZ2_BTTS_MIN, ZZ2_U25_MIN


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den <= 0 or not math.isfinite(num) or not math.isfinite(den):
        return None
    out = float(num) / float(den)
    if not math.isfinite(out):
        return None
    return out


def _raw_overround(row: dict[str, Any]) -> float | None:
    implied = []
    for stem in ("ft_home", "ft_draw", "ft_away"):
        odd = row.get(f"{stem}_closing")
        if odd is not None and float(odd) > 1.0:
            implied.append(1.0 / float(odd))
    if len(implied) < 2:
        return None
    return round(sum(implied), 6)


@dataclass
class CompositeSignals:
    ph: float | None = None
    pd: float | None = None
    pa: float | None = None
    p_o15: float | None = None
    p_o25: float | None = None
    p_u25: float | None = None
    p_btts: float | None = None
    p_btts_no: float | None = None
    H: float | None = None
    I: float | None = None
    zz2_flag: bool | None = None
    J2: float | None = None
    G: float | None = None
    ou_slope: float | None = None
    missing_fields: list[str] = field(default_factory=list)
    normalization_method: str = "pair_triple_devig"
    overround: float | None = None
    signal_families_available: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ph": self.ph,
            "pd": self.pd,
            "pa": self.pa,
            "p_o15": self.p_o15,
            "p_o25": self.p_o25,
            "p_u25": self.p_u25,
            "p_btts": self.p_btts,
            "p_btts_no": self.p_btts_no,
            "H": self.H,
            "I": self.I,
            "zz2_flag": self.zz2_flag,
            "J2": self.J2,
            "G": self.G,
            "ou_slope": self.ou_slope,
            "missing_fields": list(self.missing_fields),
            "normalization_method": self.normalization_method,
            "overround": self.overround,
            "signal_families_available": self.signal_families_available,
        }


def compute_composite_signals(
    probs: dict[str, float | None],
    *,
    raw_row: dict[str, Any] | None = None,
) -> CompositeSignals:
    missing: list[str] = []
    ph = probs.get("ft_home")
    pa = probs.get("ft_away")
    pd = probs.get("ft_draw") or probs.get("draw_proxy")
    p_o15 = probs.get("ou_over_15")
    p_o25 = probs.get("ou_over_25")
    p_u25 = probs.get("ou_under_25")
    p_btts = probs.get("btts_yes")
    p_btts_no = probs.get("btts_no")

    for name, val in (
        ("ph", ph),
        ("pd", pd),
        ("pa", pa),
        ("p_o15", p_o15),
        ("p_o25", p_o25),
        ("p_u25", p_u25),
        ("p_btts", p_btts),
        ("p_btts_no", p_btts_no),
    ):
        if val is None or not math.isfinite(float(val)):
            missing.append(name)

    H = None
    if ph is not None and p_o25 is not None and p_btts is not None:
        H = (float(ph) + float(p_o25) + float(p_btts)) / 3.0

    I = None
    if pd is not None and p_u25 is not None and p_btts_no is not None:
        I = (float(pd) + float(p_u25) + float(p_btts_no)) / 3.0

    zz2_flag = None
    if p_btts is not None and p_u25 is not None:
        zz2_flag = float(p_btts) > ZZ2_BTTS_MIN and float(p_u25) > ZZ2_U25_MIN

    J2 = _safe_div(p_o25, p_btts)
    G = None
    if ph is not None and pa is not None and p_o25 is not None and float(p_o25) > 0:
        G = abs(float(ph) - float(pa)) / float(p_o25)
    ou_slope = _safe_div(p_o15, p_o25)

    families = 0
    if H is not None or I is not None:
        families += 1
    if zz2_flag is not None:
        families += 1
    if J2 is not None:
        families += 1
    if G is not None:
        families += 1
    if ou_slope is not None:
        families += 1

    overround = _raw_overround(raw_row) if raw_row else None

    return CompositeSignals(
        ph=round(ph, 8) if ph is not None else None,
        pd=round(pd, 8) if pd is not None else None,
        pa=round(pa, 8) if pa is not None else None,
        p_o15=round(p_o15, 8) if p_o15 is not None else None,
        p_o25=round(p_o25, 8) if p_o25 is not None else None,
        p_u25=round(p_u25, 8) if p_u25 is not None else None,
        p_btts=round(p_btts, 8) if p_btts is not None else None,
        p_btts_no=round(p_btts_no, 8) if p_btts_no is not None else None,
        H=round(H, 8) if H is not None and math.isfinite(H) else None,
        I=round(I, 8) if I is not None and math.isfinite(I) else None,
        zz2_flag=zz2_flag,
        J2=round(J2, 8) if J2 is not None else None,
        G=round(G, 8) if G is not None and math.isfinite(G) else None,
        ou_slope=round(ou_slope, 8) if ou_slope is not None else None,
        missing_fields=missing,
        overround=overround,
        signal_families_available=families,
    )


def signals_finite(sig: CompositeSignals) -> bool:
    for val in (sig.H, sig.I, sig.J2, sig.G, sig.ou_slope):
        if val is not None and not math.isfinite(val):
            return False
    return True
