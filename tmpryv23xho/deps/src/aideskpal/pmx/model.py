"""Data model for PMX (MikuMikuDance) files.

Only geometry, materials, bones and morphs are needed by the companion.  Physics,
joints and display frames are parsed for forward compatibility but are not used by
the renderer (see docs/architecture.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class PmxError(RuntimeError):
    """Raised when a PMX file cannot be parsed."""


@dataclass(slots=True)
class Vertex:
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]
    bone_indices: tuple[int, int, int, int] = (-1, -1, -1, -1)
    bone_weights: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    edge_scale: float = 1.0
    extra_uvs: tuple[tuple[float, float, float, float], ...] = ()
    weight_type: str = "BDEF1"


@dataclass(slots=True)
class Material:
    name: str
    name_en: str
    diffuse: tuple[float, float, float, float]
    specular: tuple[float, float, float]
    specular_strength: float
    ambient: tuple[float, float, float]
    flags: int
    edge_color: tuple[float, float, float, float]
    edge_size: float
    texture_index: int
    sphere_texture_index: int
    sphere_mode: int
    toon_index: int
    memo: str
    index_count: int
    texture_path: str | None = None
    sphere_texture_path: str | None = None
    index_start: int = 0
    vertex_offset: int = 0

    @property
    def alpha(self) -> float:
        return float(self.diffuse[3])

    @property
    def double_sided(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def draw_edge(self) -> bool:
        return bool(self.flags & 0x10)

    @property
    def casts_shadow(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def receives_shadow(self) -> bool:
        return bool(self.flags & 0x04)

    @property
    def is_transparent(self) -> bool:
        return self.alpha < 0.999


@dataclass(slots=True)
class Bone:
    index: int
    name: str
    name_en: str
    position: tuple[float, float, float]
    parent_index: int
    layer: int
    flags: int
    tail_bone_index: int = -1
    tail_offset: tuple[float, float, float] = (0.0, 1.0, 0.0)
    inherit_parent_index: int = -1
    inherit_ratio: float = 0.0
    fixed_axis: tuple[float, float, float] | None = None
    local_axis_x: tuple[float, float, float] | None = None
    local_axis_z: tuple[float, float, float] | None = None
    external_key: int = 0
    ik: "Ik | None" = None

    @property
    def rotatable(self) -> bool:
        return bool(self.flags & 0x0002)

    @property
    def movable(self) -> bool:
        return bool(self.flags & 0x0004)

    @property
    def visible(self) -> bool:
        return bool(self.flags & 0x0008)

    @property
    def enabled(self) -> bool:
        return bool(self.flags & 0x0010)

    @property
    def is_ik(self) -> bool:
        return bool(self.flags & 0x0020)


@dataclass(slots=True)
class IkLink:
    bone_index: int
    has_limit: bool
    lower: tuple[float, float, float] = (-3.1415926, -3.1415926, -3.1415926)
    upper: tuple[float, float, float] = (3.1415926, 3.1415926, 3.1415926)


@dataclass(slots=True)
class Ik:
    target_index: int
    loop_count: int
    angle_limit: float
    links: list[IkLink] = field(default_factory=list)


@dataclass(slots=True)
class Morph:
    index: int
    name: str
    name_en: str
    panel: int
    morph_type: int
    offsets: list[Any] = field(default_factory=list)

    type_name: str = "unknown"


@dataclass(slots=True)
class PmxModel:
    path: Path
    version: float
    encoding: str
    name: str
    name_en: str
    comment: str
    vertices: list[Vertex]
    indices: np.ndarray
    texture_paths: list[str]
    materials: list[Material]
    bones: list[Bone]
    morphs: list[Morph]
    rigid_body_count: int = 0
    joint_count: int = 0

    # Numpy views built lazily by :func:`prepare_arrays`.
    positions: np.ndarray = field(default_factory=lambda: np.empty((0, 3), np.float32), repr=False)
    normals: np.ndarray = field(default_factory=lambda: np.empty((0, 3), np.float32), repr=False)
    uvs: np.ndarray = field(default_factory=lambda: np.empty((0, 2), np.float32), repr=False)
    bone_indices: np.ndarray = field(
        default_factory=lambda: np.empty((0, 4), np.int32), repr=False
    )
    bone_weights: np.ndarray = field(
        default_factory=lambda: np.empty((0, 4), np.float32), repr=False
    )
    bbox_min: np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32), repr=False)
    bbox_max: np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32), repr=False)
    bone_by_name: dict[str, int] = field(default_factory=dict, repr=False)
    morph_by_name: dict[str, int] = field(default_factory=dict, repr=False)
    render_space: bool = False

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3

    @property
    def height(self) -> float:
        return float(self.bbox_max[1] - self.bbox_min[1])

    @property
    def directory(self) -> Path:
        return self.path.parent

    def resolve_asset(self, relative: str | None) -> Path | None:
        if not relative:
            return None
        # PMX files often contain Windows separators even on Linux/macOS.
        cleaned = relative.replace("\\", "/").lstrip("/")
        candidate = (self.directory / cleaned).resolve()
        try:
            candidate.relative_to(self.directory.resolve())
        except ValueError:
            return None
        return candidate

    def prepare_arrays(self) -> None:
        if len(self.positions):
            return
        count = len(self.vertices)
        self.positions = np.asarray([v.position for v in self.vertices], dtype=np.float32)
        self.normals = np.asarray([v.normal for v in self.vertices], dtype=np.float32)
        self.uvs = np.asarray([v.uv for v in self.vertices], dtype=np.float32)
        self.bone_indices = np.asarray([v.bone_indices for v in self.vertices], dtype=np.int32)
        self.bone_weights = np.asarray([v.bone_weights for v in self.vertices], dtype=np.float32)
        if count:
            self.bbox_min = self.positions.min(axis=0)
            self.bbox_max = self.positions.max(axis=0)
        self.bone_by_name = {b.name: b.index for b in self.bones}
        self.morph_by_name = {m.name: m.index for m in self.morphs}

        vertex_offset = 0
        for material in self.materials:
            material.index_start = vertex_offset
            material.vertex_offset = vertex_offset
            vertex_offset += material.index_count

    def bone_index(self, *names: str) -> int:
        """Return the first matching bone index, supporting JP/EN names."""
        for name in names:
            if name in self.bone_by_name:
                return self.bone_by_name[name]
        for bone in self.bones:
            if bone.name_en in names:
                return bone.index
        return -1

    def to_render_space(self) -> None:
        """Mirror Z to match OpenGL's right-handed view and flip winding.

        PMX uses MMD's left-handed coordinate system; its models face -Z.  The
        companion's action files are authored in this mirrored, right-handed space:
        +X is the character's left (screen right from the front), +Y is up and +Z
        points toward the viewer.  UV V is flipped to match OpenGL's texture origin.
        """
        if self.render_space:
            return
        if not len(self.positions):
            self.prepare_arrays()
        self.positions[:, 2] *= -1.0
        self.normals[:, 2] *= -1.0
        self.uvs[:, 1] = 1.0 - self.uvs[:, 1]
        self.indices = np.ascontiguousarray(
            self.indices.reshape(-1, 3)[:, ::-1].reshape(-1)
        )
        for bone in self.bones:
            bone.position = (bone.position[0], bone.position[1], -bone.position[2])
            if bone.fixed_axis:
                bone.fixed_axis = (
                    bone.fixed_axis[0],
                    bone.fixed_axis[1],
                    -bone.fixed_axis[2],
                )
        self.bbox_min = self.positions.min(axis=0)
        self.bbox_max = self.positions.max(axis=0)
        self.render_space = True

    def material_index_by_name(self, name: str) -> int:
        for index, material in enumerate(self.materials):
            if name in (material.name, material.name_en):
                return index
        return -1


def load_pmx(path: str | Path) -> PmxModel:
    """Parse a PMX file from disk."""
    from aideskpal.pmx.parser import PmxParser

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise PmxError(f"PMX file not found: {resolved}")
    parser = PmxParser(resolved)
    model = parser.parse()
    model.prepare_arrays()
    from aideskpal.pmx.rigging import repair_known_rigging

    repaired = repair_known_rigging(model)
    if repaired:
        logger.info("Repaired %d mirrored leg bindings for %s in memory", repaired, model.name)
    return model
