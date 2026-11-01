"""Interpolation curves available to action authors."""

from __future__ import annotations

import math


def apply_easing(name: str, t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    name = (name or "smooth").strip().lower()
    if name in {"linear", "line"}:
        return t
    if name in {"constant", "step"}:
        return 0.0
    if name in {"ease_in", "easein", "in"}:
        return t * t
    if name in {"ease_out", "easeout", "out"}:
        return 1.0 - (1.0 - t) * (1.0 - t)
    if name in {"ease_in_out", "easeinout", "inout"}:
        return 3 * t * t - 2 * t * t * t
    if name in {"sine", "smooth", "ease", "bezier"}:
        return 0.5 - 0.5 * math.cos(math.pi * t)
    # Unknown curves degrade to smoothstep instead of failing an animation.
    return 3 * t * t - 2 * t * t * t
