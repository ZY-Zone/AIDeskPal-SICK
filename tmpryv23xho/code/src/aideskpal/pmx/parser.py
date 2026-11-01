"""Low-level PMX 2.0 / 2.1 reader.

The parser intentionally has no third-party dependencies.  It is strict about
bounds (a malformed PMX must never be able to allocate unbounded memory or hang
the UI) while being tolerant of slightly non-conforming files.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import numpy as np

from aideskpal.pmx.model import (
    Bone,
    Ik,
    IkLink,
    Material,
    Morph,
    PmxError,
    PmxModel,
    Vertex,
)

MAX_COUNT = 2_000_000
MAX_TEXT_BYTES = 4 * 1024 * 1024

MORPH_TYPE_NAMES = {
    0: "group",
    1: "vertex",
    2: "bone",
    3: "uv",
    4: "uv1",
    5: "uv2",
    6: "uv3",
    7: "uv4",
    8: "material",
    9: "flip",
    10: "impulse",
}


class PmxParser:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data = path.read_bytes()
        self._view = memoryview(self._data)
        self._pos = 0
        self._encoding = "utf-16-le"
        self._extra_uv_count = 0
        self._index_sizes = {
            "vertex": 4,
            "texture": 1,
            "material": 1,
            "bone": 1,
            "morph": 1,
            "rigidbody": 1,
        }

    # ------------------------------------------------------------------ readers
    def _take(self, size: int) -> memoryview:
        if size < 0 or self._pos + size > len(self._view):
            raise PmxError(f"Unexpected end of PMX at byte {self._pos} (wanted {size} bytes)")
        chunk = self._view[self._pos : self._pos + size]
        self._pos += size
        return chunk

    def _unpack(self, fmt: str) -> tuple[Any, ...]:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self._take(size))

    def _u8(self) -> int:
        return self._unpack("<B")[0]

    def _i8(self) -> int:
        return self._unpack("<b")[0]

    def _u16(self) -> int:
        return self._unpack("<H")[0]

    def _i16(self) -> int:
        return self._unpack("<h")[0]

    def _u32(self) -> int:
        return self._unpack("<I")[0]

    def _i32(self) -> int:
        return self._unpack("<i")[0]

    def _f32(self) -> float:
        return self._unpack("<f")[0]

    def _text(self) -> str:
        length = self._i32()
        if length < 0 or length > MAX_TEXT_BYTES:
            raise PmxError(f"Invalid PMX text length: {length}")
        raw = bytes(self._take(length))
        try:
            return raw.decode(self._encoding)
        except UnicodeDecodeError as exc:
            raise PmxError(f"Invalid {self._encoding} text in PMX") from exc

    def _vec(self, count: int) -> tuple[float, ...]:
        return self._unpack("<" + "f" * count)

    def _index(self, kind: str, *, signed: bool = True) -> int:
        size = self._index_sizes[kind]
        if size == 1:
            return self._i8() if signed else self._u8()
        if size == 2:
            return self._i16() if signed else self._u16()
        if size == 4:
            return self._i32() if signed else self._u32()
        raise PmxError(f"Unsupported PMX index size {size} for {kind}")

    def _count(self, label: str) -> int:
        count = self._i32()
        if count < 0 or count > MAX_COUNT:
            raise PmxError(f"Invalid {label} count: {count}")
        return count

    # ------------------------------------------------------------------- parse
    def parse(self) -> PmxModel:
        if bytes(self._take(4)) != b"PMX ":
            raise PmxError("Not a PMX file (missing 'PMX ' magic)")
        version = self._f32()
        if not (2.0 <= version < 3.0):
            raise PmxError(f"Unsupported PMX version {version}")

        globals_count = self._u8()
        if globals_count < 8:
            # Some old exporters omit trailing globals. Remaining fields default.
            self._encoding = "utf-16-le"
        else:
            globals_data = self._take(globals_count)
            enc = globals_data[0]
            self._encoding = "utf-16-le" if enc == 0 else "utf-8"
            self._extra_uv_count = int(globals_data[1])
            sizes = list(globals_data[2:8])
            self._index_sizes.update(
                {
                    "vertex": sizes[0],
                    "texture": sizes[1],
                    "material": sizes[2],
                    "bone": sizes[3],
                    "morph": sizes[4],
                    "rigidbody": sizes[5],
                }
            )
            if version >= 2.1 and globals_count >= 9:
                self._index_sizes["rigidbody"] = sizes[5]

        if any(size not in (1, 2, 4) for size in self._index_sizes.values()):
            raise PmxError("Unsupported PMX index width")

        name = self._text()
        name_en = self._text()
        comment = self._text()
        _comment_en = self._text()

        vertices = [self._read_vertex() for _ in range(self._count("vertex"))]
        index_count = self._u32()
        if index_count > 120_000_000:
            raise PmxError("PMX face index count exceeds plausible bounds")
        if index_count > (len(self._view) - self._pos):
            raise PmxError("PMX face index count exceeds the remaining file size")
        flat = np.empty(index_count, dtype=np.uint32)
        size = self._index_sizes["vertex"]
        if index_count:
            fmt = {1: "B", 2: "H", 4: "I"}[size]
            raw = self._take(index_count * size)
            flat[:] = np.frombuffer(raw, dtype=np.dtype(f"<u{size}"), count=index_count)
            if int(flat.max(initial=0)) >= len(vertices):
                raise PmxError("PMX face references a vertex that does not exist")
        if len(flat) % 3:
            flat = flat[: len(flat) - (len(flat) % 3)]

        texture_paths = [self._text() for _ in range(self._count("texture"))]
        materials = [
            self._read_material(texture_paths) for _ in range(self._count("material"))
        ]
        bones = [self._read_bone() for _ in range(self._count("bone"))]
        for bone_index, bone in enumerate(bones):
            bone.index = bone_index
        morphs = [self._read_morph() for _ in range(self._count("morph"))]
        for morph_index, morph in enumerate(morphs):
            morph.index = morph_index
        _display_frames = self._count("display frame")
        for _ in range(_display_frames):
            self._read_display_frame()

        # Physics bodies/joints are intentionally not parsed: the renderer uses
        # authored bone animation only (see docs/architecture.md).  Stopping at
        # the display frames also tolerates exporter-specific trailing payloads.
        rigid_body_count = 0
        joint_count = 0

        return PmxModel(
            path=self.path,
            version=version,
            encoding=self._encoding,
            name=name,
            name_en=name_en,
            comment=comment,
            vertices=vertices,
            indices=flat,
            texture_paths=texture_paths,
            materials=materials,
            bones=bones,
            morphs=morphs,
            rigid_body_count=rigid_body_count,
            joint_count=joint_count,
        )

    def _read_vertex(self) -> Vertex:
        pos = self._vec(3)
        normal = self._vec(3)
        uv = self._vec(2)
        extra = tuple(self._vec(4) for _ in range(self._extra_uv_count))
        weight_type = self._u8()
        indices = [-1, -1, -1, -1]
        weights = [0.0, 0.0, 0.0, 0.0]
        type_name = {0: "BDEF1", 1: "BDEF2", 2: "BDEF4", 3: "SDEF", 4: "QDEF"}.get(
            weight_type, "BDEF1"
        )
        if weight_type == 0:
            indices[0] = self._index("bone")
            weights[0] = 1.0
        elif weight_type == 1:
            indices[0] = self._index("bone")
            indices[1] = self._index("bone")
            weights[0] = self._f32()
            weights[1] = 1.0 - weights[0]
        elif weight_type == 2:
            for i in range(4):
                indices[i] = self._index("bone")
            for i in range(4):
                weights[i] = self._f32()
        elif weight_type == 3:
            indices[0] = self._index("bone")
            indices[1] = self._index("bone")
            weights[0] = self._f32()
            weights[1] = 1.0 - weights[0]
            # C, R0, R1 spherical weights are unused by the linear renderer.
            for _ in range(9):
                self._f32()
        elif weight_type == 4:
            for i in range(4):
                indices[i] = self._index("bone")
            for i in range(4):
                weights[i] = self._f32()
        else:
            raise PmxError(f"Unsupported PMX vertex weight type {weight_type}")
        edge_scale = self._f32()
        return Vertex(
            position=pos,
            normal=normal,
            uv=uv,
            bone_indices=tuple(indices),  # type: ignore[arg-type]
            bone_weights=tuple(weights),  # type: ignore[arg-type]
            edge_scale=edge_scale,
            extra_uvs=extra,
            weight_type=type_name,
        )

    def _read_material(self, textures: list[str]) -> Material:
        name = self._text()
        name_en = self._text()
        diffuse = self._vec(4)
        specular = self._vec(3)
        specular_strength = self._f32()
        ambient = self._vec(3)
        flags = self._u8()
        edge_color = self._vec(4)
        edge_size = self._f32()
        texture_index = self._index("texture")
        sphere_index = self._index("texture")
        sphere_mode = self._u8()
        toon_sharing = self._u8()
        if toon_sharing == 0:
            toon_index = self._index("texture")
        else:
            toon_index = self._u8()
        memo = self._text()
        index_count = self._u32()
        return Material(
            name=name,
            name_en=name_en,
            diffuse=diffuse,
            specular=specular,
            specular_strength=specular_strength,
            ambient=ambient,
            flags=flags,
            edge_color=edge_color,
            edge_size=edge_size,
            texture_index=texture_index,
            sphere_texture_index=sphere_index,
            sphere_mode=sphere_mode,
            toon_index=toon_index,
            memo=memo,
            index_count=index_count,
            texture_path=textures[texture_index] if 0 <= texture_index < len(textures) else None,
            sphere_texture_path=(
                textures[sphere_index] if 0 <= sphere_index < len(textures) else None
            ),
        )

    def _read_bone(self) -> Bone:
        name = self._text()
        name_en = self._text()
        position = self._vec(3)
        parent = self._index("bone")
        layer = self._i32()
        flags = self._u16()
        tail_bone = -1
        tail_offset = (0.0, 1.0, 0.0)
        if flags & 0x0001:
            tail_bone = self._index("bone")
        else:
            tail_offset = self._vec(3)
        inherit_parent = -1
        inherit_ratio = 0.0
        # PMX 2.0 bone flag bits 0x0080 is obsolete; inheritance starts at 0x0100.
        if flags & (0x0100 | 0x0200):
            inherit_parent = self._index("bone")
            inherit_ratio = self._f32()
        fixed_axis = None
        if flags & 0x0400:
            fixed_axis = self._vec(3)
        local_x = local_z = None
        if flags & 0x0800:
            local_x = self._vec(3)
            local_z = self._vec(3)
        external_key = self._i32() if flags & 0x2000 else 0
        ik = None
        if flags & 0x0020:
            target = self._index("bone")
            loop_count = self._i32()
            angle_limit = self._f32()
            link_count = self._count("IK link")
            links: list[IkLink] = []
            for _ in range(link_count):
                bone_index = self._index("bone")
                has_limit = bool(self._u8())
                lower = upper = (-3.1415926, -3.1415926, -3.1415926)
                if has_limit:
                    lower = self._vec(3)
                    upper = self._vec(3)
                links.append(IkLink(bone_index, has_limit, lower, upper))
            ik = Ik(target, loop_count, angle_limit, links)
        return Bone(
            index=-1,  # filled in by caller after append
            name=name,
            name_en=name_en,
            position=position,
            parent_index=parent,
            layer=layer,
            flags=flags,
            tail_bone_index=tail_bone,
            tail_offset=tail_offset,
            inherit_parent_index=inherit_parent,
            inherit_ratio=inherit_ratio,
            fixed_axis=fixed_axis,
            local_axis_x=local_x,
            local_axis_z=local_z,
            external_key=external_key,
            ik=ik,
        )

    def _read_morph(self) -> Morph:
        name = self._text()
        name_en = self._text()
        panel = self._u8()
        morph_type = self._u8()
        count = self._count("morph offset")
        offsets: list[Any] = []
        if morph_type == 0:  # group
            for _ in range(count):
                offsets.append((self._index("morph"), self._f32()))
        elif morph_type == 1:  # vertex
            for _ in range(count):
                offsets.append((self._index("vertex"), self._vec(3)))
        elif morph_type == 2:  # bone
            for _ in range(count):
                offsets.append(
                    (self._index("bone"), self._vec(3), self._vec(4))
                )
        elif morph_type in (3, 4, 5, 6, 7):  # uv
            for _ in range(count):
                offsets.append((self._index("vertex"), self._vec(4)))
        elif morph_type == 8:  # material
            for _ in range(count):
                index = self._index("material")
                method = self._u8()
                diffuse = self._vec(4)
                specular = self._vec(3)
                specular_strength = self._f32()
                ambient = self._vec(3)
                edge_color = self._vec(4)
                edge_size = self._f32()
                texture_tint = self._vec(4)
                sphere_tint = self._vec(4)
                toon_tint = self._vec(4)
                offsets.append(
                    {
                        "index": index,
                        "method": method,
                        "diffuse": diffuse,
                        "specular": specular,
                        "specular_strength": specular_strength,
                        "ambient": ambient,
                        "edge_color": edge_color,
                        "edge_size": edge_size,
                        "texture_tint": texture_tint,
                        "sphere_tint": sphere_tint,
                        "toon_tint": toon_tint,
                    }
                )
        elif morph_type == 9:  # flip
            for _ in range(count):
                offsets.append((self._index("morph"), self._f32()))
        elif morph_type == 10:  # impulse
            for _ in range(count):
                index = self._index("rigidbody")
                local = bool(self._u8())
                velocity = self._vec(3)
                torque = self._vec(3)
                offsets.append((index, local, velocity, torque))
        else:
            raise PmxError(f"Unsupported PMX morph type {morph_type}")
        return Morph(
            index=-1,
            name=name,
            name_en=name_en,
            panel=panel,
            morph_type=morph_type,
            offsets=offsets,
            type_name=MORPH_TYPE_NAMES.get(morph_type, "unknown"),
        )

    def _read_display_frame(self) -> None:
        self._text()  # name
        self._text()  # English name
        self._u8()  # preferred panel: 0 root, 1 expression, 2 IK ...
        count = self._count("display frame item")
        for _ in range(count):
            # Each display item carries its own kind byte.  The frame's
            # "special" flag is only a UI hint and does not change the index width.
            item_type = self._u8()
            if item_type == 0:
                self._index("bone")
            elif item_type == 1:
                self._index("morph")
            else:
                raise PmxError(f"Unsupported PMX display frame item type {item_type}")

    def _skip_rigid_body(self) -> None:
        self._text()
        self._text()
        self._index("bone")
        self._u8()  # group
        self._u16()  # mask
        self._u8()  # shape
        self._f32()  # width
        self._f32()  # height
        self._f32()  # depth
        self._vec(3)  # position
        self._vec(3)  # rotation
        self._f32()  # mass
        self._f32()  # linear damping
        self._f32()  # angular damping
        self._f32()  # restitution
        self._f32()  # friction
        self._u8()  # physics mode

    def _skip_joint(self) -> None:
        self._text()
        self._text()
        self._u8()  # type
        for _ in range(2):
            self._index("rigidbody")
            self._vec(3)  # position
            self._vec(3)  # rotation
            self._vec(3)  # limit min
            self._vec(3)  # limit max
            self._vec(3)  # spring position
            self._vec(3)  # spring rotation
