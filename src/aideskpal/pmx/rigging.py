"""Scoped runtime repairs for known PMX binding defects.

Repairs operate on the loaded model only; source PMX assets are never rewritten.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from aideskpal.pmx.model import PmxModel


# Right-leg bones that the mesh binds to, and the left-side bone whose geometry
# they are supposed to match. The defects below only ever involve these pairs.
_THIGH = ("足D",)
_SHIN = ("ひざD",)
_KNEE_TOE = ("足首D", "足先EX")


def _influenced_by(model: PmxModel, bones: list[int]) -> np.ndarray:
    if not bones or not len(model.positions):
        return np.zeros(len(model.positions), dtype=bool)
    return (
        (model.bone_indices[:, :, None] == np.asarray(bones)[None, None, :]).any(axis=2)
        & (model.bone_weights > 0.0001)
    ).any(axis=1)


def _dominant_bone(model: PmxModel) -> np.ndarray:
    """Name of each vertex's heaviest bone (empty string if unweighted)."""
    indices = model.bone_indices
    weights = model.bone_weights
    best = np.argmax(weights, axis=1)
    chosen = indices[np.arange(len(indices)), best]
    names = np.array([""] + [bone.name for bone in model.bones])
    safe = np.where(chosen >= 0, chosen, 0)
    dominant = names[safe + 1]
    return np.where(chosen >= 0, dominant, "")


def _knee_line(model: PmxModel) -> float:
    """Rest height where the healthy left leg switches thigh -> shin.

    Derived from the left leg rather than hard-coded: 左足D owns the thigh and
    左ひざD the shin, so the highest vertex the shin bone drives is the knee.
    """
    dominant = _dominant_bone(model)
    shin = model.positions[dominant == "左ひざD", 1]
    if not len(shin):
        return float("inf")
    return float(shin.max())


def _reassign(model: PmxModel, vertices: np.ndarray, source: int, target: int) -> int:
    """Move `source` influence onto `target` for the given vertices."""
    changed = 0
    for vertex in vertices:
        indices = model.bone_indices[vertex].copy()
        weights = model.bone_weights[vertex].copy()
        hit = np.where(indices == source)[0]
        if not len(hit):
            continue
        for slot in hit:
            moved = float(weights[slot])
            indices[slot] = target
            weights[slot] = 0.0
            existing = np.where(indices == target)[0]
            weights[existing[0]] = min(1.0, float(weights[existing[0]]) + moved)
            if existing[0] == slot:  # merged onto itself
                break
        keep = sorted(
            (
                (float(weights[slot]), int(indices[slot]))
                for slot in range(4)
                if weights[slot] > 1e-5 and indices[slot] >= 0
            ),
            reverse=True,
        )[:4]
        new_indices = np.full(4, -1, dtype=np.int32)
        new_weights = np.zeros(4, dtype=np.float32)
        for slot, (weight, index) in enumerate(keep):
            new_indices[slot] = index
            new_weights[slot] = weight
        model.bone_indices[vertex] = new_indices
        model.bone_weights[vertex] = new_weights
        model.vertices[vertex].bone_indices = tuple(int(value) for value in new_indices)
        model.vertices[vertex].bone_weights = tuple(float(value) for value in new_weights)
        changed += 1
    return changed


def repair_right_leg_bands(model: PmxModel) -> int:
    """Move sub-knee right-leg vertices off the thigh bone onto the shin bone.

    Citlali's summer PMX binds the right leg asymmetrically below the knee: the
    left shin band (y around 1.1-6.2) is driven by 左ひざD, but the mirrored
    right band is driven largely by 右足D, the thigh bone a full parent above.
    The bones themselves are perfectly symmetric, so the skeleton is not at
    fault; the weights are. Bending the knee swings the mis-bound vertices a
    whole thigh-length away and visibly tears the skirt and shoe ornaments.

    The fix is geometric and left-referenced: anything below the knee line that
    the left leg would give to its shin bone is given to 右ひざD on the right.
    """
    knee = _knee_line(model)
    if not np.isfinite(knee):
        return 0
    thigh = model.bone_index("右足D")
    shin = model.bone_index("右ひざD")
    if thigh < 0 or shin < 0:
        return 0
    # No side filter: parts of the right shoe and its ornaments are modelled
    # across the centreline, so a sign test would skip exactly the vertices that
    # tear most. Membership in the right thigh chain is the only reliable cue.
    candidates = np.where((model.positions[:, 1] < knee) & _influenced_by(model, [thigh]))[0]
    return _reassign(model, candidates, thigh, shin)


def repair_known_rigging(model: PmxModel) -> int:
    """Apply only explicitly identified per-model compatibility repairs."""
    if model.name != "Citlali_CostumeSummer":
        return 0
    return repair_right_leg_bands(model)
