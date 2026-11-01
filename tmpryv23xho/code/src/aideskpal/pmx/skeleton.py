"""Skeleton evaluation and linear-blend skinning.

PMX stores bone positions in model space and has no bind-pose rotations.  A bone's
animated local transform is therefore ``T(parent-relative offset + delta) * R`` and
the skinning matrix is ``bone_world * T(-rest_position)``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aideskpal.pmx.model import PmxModel


def translation_matrix(v: np.ndarray) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[:3, 3] = v
    return m


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Convert an (x, y, z, w) quaternion to a 4x4 rotation matrix."""
    x, y, z, w = (float(q[0]), float(q[1]), float(q[2]), float(q[3]))
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(4, dtype=np.float32)
    s = 2.0 / n
    xx, yy, zz = x * x * s, y * y * s, z * z * s
    xy, xz, yz = x * y * s, x * z * s, y * z * s
    wx, wy, wz = w * x * s, w * y * s, w * z * s
    return np.array(
        [
            [1.0 - (yy + zz), xy - wz, xz + wy, 0.0],
            [xy + wz, 1.0 - (xx + zz), yz - wx, 0.0],
            [xz - wy, yz + wx, 1.0 - (xx + yy), 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


@dataclass(slots=True)
class Pose:
    """A sampled animation pose.

    Rotations are quaternions in *bone local* space (x, y, z, w).  Translations are
    parent-relative deltas in model units.  Morph weights use PMX morph indices.
    """

    rotations: dict[int, np.ndarray]
    translations: dict[int, np.ndarray]
    morphs: dict[int, float]

    @classmethod
    def empty(cls) -> "Pose":
        return cls({}, {}, {})

    def copy(self) -> "Pose":
        return Pose(
            {k: v.copy() for k, v in self.rotations.items()},
            {k: v.copy() for k, v in self.translations.items()},
            dict(self.morphs),
        )

    def blend_into(self, other: "Pose", weight: float) -> None:
        """Linearly blend *other* on top of this pose at ``weight`` (0..1)."""
        weight = float(np.clip(weight, 0.0, 1.0))
        if weight <= 0.0:
            return
        for bone, quat in other.rotations.items():
            current = self.rotations.get(bone)
            if current is None:
                self.rotations[bone] = slerp(
                    np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32), quat, weight
                )
            else:
                self.rotations[bone] = slerp(current, quat, weight)
        for bone, offset in other.translations.items():
            current = self.translations.get(bone)
            if current is None:
                self.translations[bone] = offset * weight
            else:
                self.translations[bone] = current * (1.0 - weight) + offset * weight
        for morph, value in other.morphs.items():
            current = self.morphs.get(morph, 0.0)
            self.morphs[morph] = current * (1.0 - weight) + value * weight


def nlerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    if np.dot(a, b) < 0:
        b = -b
    out = a * (1.0 - t) + b * t
    n = np.linalg.norm(out)
    return out / n if n > 1e-9 else np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Spherical interpolation with constant angular speed.

    Cross-fades and keyframe rotations use this instead of plain normalized
    linear interpolation so large joint rotations do not accelerate/decelerate
    unnaturally between keys.
    """
    t = float(np.clip(t, 0.0, 1.0))
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        return nlerp(a, b, t)
    dot = float(np.clip(dot, -1.0, 1.0))
    theta = float(np.arccos(dot))
    sin_theta = float(np.sin(theta))
    if abs(sin_theta) < 1e-7:
        return nlerp(a, b, t)
    w1 = np.sin((1.0 - t) * theta) / sin_theta
    w2 = np.sin(t * theta) / sin_theta
    out = a * w1 + b * w2
    n = float(np.linalg.norm(out))
    return (out / n).astype(np.float32) if n > 1e-9 else a.astype(np.float32, copy=True)


def quat_towards(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return slerp(a, b, t)


def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product for column-vector rotations (apply b, then a)."""
    ax, ay, az, aw = map(float, a)
    bx, by, bz, bw = map(float, b)
    out = np.array((aw*bx + ax*bw + ay*bz - az*by,
                    aw*by - ax*bz + ay*bw + az*bx,
                    aw*bz + ax*by - ay*bx + az*bw,
                    aw*bw - ax*bx - ay*by - az*bz), dtype=np.float64)
    norm = np.linalg.norm(out)
    return (out / norm).astype(np.float32) if norm > 1e-12 else np.array([0, 0, 0, 1], dtype=np.float32)


def quat_power(q: np.ndarray, exponent: float) -> np.ndarray:
    """Scale a shortest-arc rotation, including negative and >1 grant ratios.

    Unlike slerp, this operation must not clamp its ratio to [0, 1].
    Equivalent quaternion signs produce the same result.
    """
    q = np.asarray(q, dtype=np.float64)
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        return np.array([0, 0, 0, 1], dtype=np.float32)
    q = q / norm
    if q[3] < 0:
        q = -q
    length = np.linalg.norm(q[:3])
    if length < 1e-12:
        return np.array([0, 0, 0, 1], dtype=np.float32)
    angle = np.arctan2(length, q[3]) * float(exponent)
    return np.concatenate((q[:3] * (np.sin(angle) / length), [np.cos(angle)])).astype(np.float32)


class Skeleton:
    def __init__(self, model: PmxModel) -> None:
        self.model = model
        self.count = len(model.bones)
        self.parents = np.asarray([b.parent_index for b in model.bones], dtype=np.int32)
        self.positions = np.asarray([b.position for b in model.bones], dtype=np.float32)
        self.rest_inverse = np.tile(np.eye(4, dtype=np.float32), (self.count, 1, 1))
        for index, position in enumerate(self.positions):
            self.rest_inverse[index, :3, 3] = -position
        self._order = self._topological_order()
        self._identity = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self._zero = np.zeros(3, dtype=np.float32)
        self._rest_offsets = self.positions.copy()
        for index, parent in enumerate(self.parents):
            if 0 <= parent < self.count:
                self._rest_offsets[index] -= self.positions[parent]
        self._rest_locals = np.tile(np.eye(4, dtype=np.float32), (self.count, 1, 1))
        self._rest_locals[:, :3, 3] = self._rest_offsets

    def _topological_order(self) -> list[int]:
        order: list[int] = []
        visited = np.zeros(self.count, dtype=bool)
        state = np.zeros(self.count, dtype=np.uint8)

        def visit(index: int) -> None:
            if visited[index]:
                return
            if state[index] == 1:
                # Cyclic parenting is invalid; break the cycle gracefully.
                visited[index] = True
                order.append(index)
                return
            state[index] = 1
            parent = int(self.parents[index])
            if 0 <= parent < self.count:
                visit(parent)
            state[index] = 2
            visited[index] = True
            order.append(index)

        for i in range(self.count):
            visit(i)
        return order

    def _granted_transforms(self, pose: Pose) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Resolve append transforms independently of bone storage order.

        PMX 0x0080 (local append) copies the source's own animation delta;
        ordinary append also propagates its resolved append delta. Neither
        copies the source's rest offset or its ordinary parent's world pose.
        Rotations are prepended to the recipient's animation rotation. These
        are PMX animation-coordinate deltas, not a world-space constraint or IK.
        Invalid/cyclic append edges are ignored deterministically.
        """
        rotations = [pose.rotations.get(i, self._identity).copy() for i in range(self.count)]
        translations = [pose.translations.get(i, self._zero).copy() for i in range(self.count)]
        state = np.zeros(self.count, dtype=np.uint8)

        def resolve(index: int) -> None:
            if state[index] == 2:
                return
            state[index] = 1
            bone = self.model.bones[index]
            source = bone.inherit_parent_index
            local = bool(bone.flags & 0x0080)
            if bone.flags & 0x0300 and 0 <= source < self.count and (local or state[source] != 1):
                if not local:
                    resolve(source)
                if bone.flags & 0x0100:
                    rotation = pose.rotations.get(source, self._identity) if local else rotations[source]
                    rotations[index] = quat_multiply(quat_power(rotation, bone.inherit_ratio), rotations[index])
                if bone.flags & 0x0200:
                    translation = pose.translations.get(source, self._zero) if local else translations[source]
                    translations[index] = translations[index] + translation * bone.inherit_ratio
            state[index] = 2

        for index in range(self.count):
            resolve(index)
        return rotations, translations

    def world_matrices(self, pose: Pose) -> np.ndarray:
        rotations, translations = self._granted_transforms(pose)
        # Copy immutable rest locals once, rather than allocate two temporary
        # 4x4 matrices and multiply T*R for every bone (mostly identity R).
        locals_ = self._rest_locals.copy()
        locals_[:, :3, 3] += np.asarray(translations, dtype=np.float32)
        for index, rotation in enumerate(rotations):
            # Exact zero-vector test also accepts -identity and zero quaternions;
            # do not threshold away tiny but intentional animation rotations.
            if rotation[0] != 0 or rotation[1] != 0 or rotation[2] != 0:
                locals_[index, :3, :3] = quat_to_matrix(rotation)[:3, :3]
        world = np.empty_like(locals_)
        for index in self._order:
            parent = int(self.parents[index])
            if 0 <= parent < self.count:
                world[index] = world[parent] @ locals_[index]
            else:
                world[index] = locals_[index]
        return world

    def skin_matrices(self, pose: Pose) -> np.ndarray:
        return self.world_matrices(pose) @ self.rest_inverse

    def skin_vertices(
        self, skin_matrices: np.ndarray, positions: np.ndarray, normals: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        indices = self.model.bone_indices
        weights = self.model.bone_weights
        safe_indices = np.where(indices >= 0, indices, 0)
        weight_sum = weights.sum(axis=1, keepdims=True)
        weights = np.divide(weights, weight_sum, out=np.zeros_like(weights), where=weight_sum > 0)
        mats = skin_matrices[safe_indices]  # (V, 4, 4, 4)
        blended = np.einsum("vi,vijk->vjk", weights.astype(np.float32), mats)
        out_positions = (
            np.einsum("vij,vj->vi", blended[:, :3, :3], positions, optimize=True)
            + blended[:, :3, 3]
        )
        out_normals = np.einsum("vij,vj->vi", blended[:, :3, :3], normals, optimize=True)
        lengths = np.linalg.norm(out_normals, axis=1, keepdims=True)
        out_normals = np.divide(
            out_normals, lengths, out=np.zeros_like(out_normals), where=lengths > 1e-8
        )
        return out_positions, out_normals


def quat_from_euler_xyz(degrees: tuple[float, float, float] | list[float]) -> np.ndarray:
    """MMD-style local Euler rotation, degrees, applied in X→Y→Z order."""
    x, y, z = np.radians(np.asarray(degrees, dtype=np.float64))
    cx, sx = np.cos(x / 2), np.sin(x / 2)
    cy, sy = np.cos(y / 2), np.sin(y / 2)
    cz, sz = np.cos(z / 2), np.sin(z / 2)
    # Intrinsic XYZ: qz * qy * qx (column-vector convention).
    return np.array(
        [
            sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
            cx * cy * cz + sx * sy * sz,
        ],
        dtype=np.float32,
    )
