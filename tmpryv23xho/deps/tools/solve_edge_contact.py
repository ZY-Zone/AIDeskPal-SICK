"""Offline FK solver for edge-pose contact.

Hand-tuning Euler angles cannot reliably land a wrist or ankle on a screen edge,
so this tool solves limb chains against explicit contact targets and prints
absolute local angles.  Results are pasted into ``polish_citlali_motion.py`` as
constants: runtime never solves anything, and actions stay byte-deterministic.

The solver walks the real parent chain of the target bone using rest-local
transforms.  Every bone on the path contributes its rest offset (the rig inserts
``捩`` twist bones that shifting the chain would otherwise drop); only the joints
that animations actually rotate become free variables.  Joints are solved
together against several targets at once, so a W-sit is defined by where the
knee *and* the ankle go, not by an ankle alone.

Run from the repository root:

    $env:PYTHONPATH='src'; .venv/Scripts/python tools/solve_edge_contact.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aideskpal.pmx.model import load_pmx  # noqa: E402
from aideskpal.pmx.skeleton import Skeleton, quat_from_euler_xyz, quat_to_matrix  # noqa: E402

MODEL = ROOT / "src/aideskpal/character/茜特菈莉/model.pmx"

# Bones that carry no useful rotation for contact (twist/roll helpers).
FROZEN = {
    "左腕捩", "右腕捩", "左手捩", "右手捩",
    "左足捩", "右足捩", "左ひざ捩", "右ひざ捩",
    "左足D", "右足D", "左ひざD", "右ひざD", "左足首D", "右足首D",
}


def _local(rest: np.ndarray, angles) -> np.ndarray:
    matrix = rest.copy()
    angles = np.asarray(angles, dtype=np.float64)
    if np.any(angles != 0.0):
        matrix[:3, :3] = quat_to_matrix(quat_from_euler_xyz(angles))[:3, :3]
    return matrix


class Chain:
    """Full parent path from a root bone to a tip."""

    def __init__(self, skeleton: Skeleton, root: str, tip: str) -> None:
        model = skeleton.model
        tip_index = model.bone_index(tip)
        root_index = model.bone_index(root)
        if tip_index < 0 or root_index < 0:
            raise ValueError(f"unknown bone in chain {root} -> {tip}")
        path: list[int] = []
        current = tip_index
        while current >= 0:
            path.append(current)
            if current == root_index:
                break
            current = int(skeleton.parents[current])
        if not path or path[-1] != root_index:
            raise ValueError(f"{root} is not an ancestor of {tip}")
        path.reverse()
        self.skeleton = skeleton
        self.path = path
        self.names = [model.bones[index].name for index in path]
        self.rest = [skeleton._rest_locals[index].astype(np.float64) for index in path]
        self.free = [slot for slot, name in enumerate(self.names) if name not in FROZEN]
        self.slots = {name: slot for slot, name in enumerate(self.names)}
        # Column offset of each free joint in the parameter vector.  Built once:
        # ``list.index`` per bone per evaluation made the Jacobian silently
        # constant, because slot numbers and free-list positions differ.
        self.columns = {slot: position * 3 for position, slot in enumerate(self.free)}
        self.size = len(self.free) * 3
        parent = int(skeleton.parents[root_index])
        self.base = _rest_world(skeleton, parent) if parent >= 0 else np.eye(4)
        self.root_index = root_index

    def world_at(self, params: np.ndarray, upto: int) -> np.ndarray:
        params = np.asarray(params)
        world = self.base.copy()
        for slot in range(upto + 1):
            column = self.columns.get(slot)
            angles = [0.0, 0.0, 0.0] if column is None else params[column:column + 3]
            world = world @ _local(self.rest[slot], angles)
        return world

    def tip(self, params: np.ndarray) -> np.ndarray:
        return self.world_at(params, len(self.path) - 1)[:3, 3].copy()

    def report(self, params: np.ndarray) -> list[tuple[str, list[float]]]:
        out = []
        for slot, name in enumerate(self.names):
            column = self.columns.get(slot)
            if column is None:
                continue
            out.append((name, [round(float(v), 2) for v in params[column:column + 3]]))
        return out


def _rest_world(skeleton: Skeleton, index: int) -> np.ndarray:
    world = np.eye(4)
    path: list[int] = []
    current = index
    while 0 <= current < skeleton.count:
        path.append(current)
        current = int(skeleton.parents[current])
    for bone in reversed(path):
        world = world @ skeleton._rest_locals[bone].astype(np.float64)
    return world


def solve(
    chain: Chain,
    targets: list[tuple[str, tuple[float, float, float]]],
    prior_mapping: dict[str, list[float]],
    *,
    prior_weight: float = 0.03,
    iterations: int = 120,
    seeds: int = 6,
) -> tuple[np.ndarray, list[tuple[str, float]]]:
    """Levenberg–Marquardt over all targets at once, with a rest-pose prior."""
    prior = np.zeros(chain.size)
    for slot, name in enumerate(chain.names):
        column = chain.columns.get(slot)
        if column is None:
            continue
        prior[column:column + 3] = prior_mapping.get(name, [0.0, 0.0, 0.0])

    resolved = []
    for name, position in targets:
        if name not in chain.slots:
            raise ValueError(f"{name} is not on the {chain.root_index} chain")
        resolved.append((chain.slots[name], np.asarray(position, dtype=np.float64)))

    def residuals(params: np.ndarray) -> np.ndarray:
        out = []
        for slot, position in resolved:
            out.extend(position - chain.world_at(params, slot)[:3, 3])
        return np.asarray(out)

    rng = np.random.default_rng(3)
    best: tuple[float, np.ndarray] | None = None
    for seed in range(seeds):
        params = prior.copy() if seed == 0 else prior + rng.normal(0.0, 20.0, chain.size)
        damping = 3.0
        for _ in range(iterations):
            current = residuals(params)
            cost = float(current @ current)
            jacobian = np.empty((current.size, chain.size))
            step = 1e-3
            for column in range(chain.size):
                probe = params.copy()
                probe[column] += step
                jacobian[:, column] = (residuals(probe) - current) / step
            gradient = jacobian.T @ current - prior_weight * (params - prior)
            matrix = jacobian.T @ jacobian + damping * np.eye(chain.size)
            try:
                delta = np.linalg.solve(matrix, gradient)
            except np.linalg.LinAlgError:
                break
            scale, improved = 1.0, False
            for _ in range(10):
                candidate = params + delta * scale
                trial = residuals(candidate)
                if float(trial @ trial) < cost:
                    params, improved = candidate, True
                    break
                scale *= 0.5
            if not improved:
                damping *= 4.0
                if damping > 1e5:
                    break
            else:
                damping = max(0.05, damping * 0.4)
            if float(np.linalg.norm(delta * scale)) < 1e-6:
                break
        final = residuals(params)
        distance = float(np.linalg.norm(final))
        if best is None or distance < best[0]:
            best = (distance, params.copy())
    assert best is not None
    params = best[1]
    errors = [
        (chain.names[slot], round(float(np.linalg.norm(position - chain.world_at(params, slot)[:3, 3])), 3))
        for slot, position in resolved
    ]
    return params, errors


_SKELETON: Skeleton | None = None


def skeleton() -> Skeleton:
    global _SKELETON
    if _SKELETON is None:
        model = load_pmx(MODEL)
        model.to_render_space()
        _SKELETON = Skeleton(model)
    return _SKELETON


def rest(name: str) -> np.ndarray:
    """Rest-pose world position of a bone, used to express targets sensibly."""
    sk = skeleton()
    index = sk.model.bone_index(name)
    return _rest_world(sk, index)[:3, 3]


def report(label: str, chain: Chain, params: np.ndarray, errors) -> None:
    print(f"-- {label}")
    print("   errors: " + ", ".join(f"{name}={value}" for name, value in errors))
    for name, angles in chain.report(params):
        print(f"     {name}: {angles}")


def main() -> None:
    sk = skeleton()
    print("Citlali edge contact solve (model units, +y up, +z toward viewer)\n")

    # ---------------------------------------------------------------- top grip
    # Both arms reach almost straight up, hands roughly shoulder-width apart and
    # level: that is what gripping a horizontal edge overhead looks like.  The
    # previous pose spread the hands wide (x=±4.5) and read as a cheer.
    for side, sign in (("左", 1), ("右", -1)):
        chain = Chain(sk, side + "腕", side + "手首")
        shoulder = rest(side + "腕")
        target = (shoulder[0] + 0.35 * sign, shoulder[1] + 4.80, shoulder[2] + 0.40)
        params, errors = solve(
            chain,
            [(side + "手首", tuple(target))],
            {
                side + "腕": [0, -6 * sign, 78 * sign],
                side + "ひじ": [0, 0, 14 * sign],
            },
        )
        report(f"top_grip {side} 腕→手首  target={np.round(target, 2)}", chain, params, errors)
    print()

    # -------------------------------------------------------------- duck sit
    # W-sit: buttocks on the ground, knees forward and slightly outward, shins
    # folded back so the ankles sit beside the hips.  Knee and ankle are solved
    # together because an ankle-only target invites a contorted knee.
    for side, sign in (("左", 1), ("右", -1)):
        chain = Chain(sk, side + "足", side + "足首")
        hip = rest(side + "足")
        knee = (hip[0] + 0.60 * sign, hip[1] + 0.30, hip[2] + 4.60)
        ankle = (hip[0] + 2.60 * sign, hip[1] - 0.60, hip[2] - 0.20)
        params, errors = solve(
            chain,
            [(side + "ひざ", tuple(knee)), (side + "足首", tuple(ankle))],
            {
                side + "足": [-74, 0, 10 * sign],
                side + "ひざ": [128, 0, 0],
                side + "足首": [58, 0, 0],
            },
        )
        report(f"bottom_sit {side} 足→足首  knee/ankle targets", chain, params, errors)


if __name__ == "__main__":
    main()
