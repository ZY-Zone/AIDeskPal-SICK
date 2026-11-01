"""Generate the original, MIT-licensed '星灵·露米' sample PMX model.

The sample exists so AIDeskPal-SICK is usable before a user imports a model, and
so the market has a fully paired, license-safe demo bundle.  Geometry is built from
primitive meshes; no third-party model data is used.
"""

from __future__ import annotations

import json
import math
import struct
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_content" / "starling"
ACTIONS = ROOT / "actions" / "starling"
MARKET_SEED = ROOT / "server" / "seed"

MODEL_ID = "starling"
MODEL_NAME = "星灵·露米"
MODEL_NAME_EN = "Starling Lumi"
AUTHOR = "AIDeskPal-SICK"


class MeshBuilder:
    def __init__(self) -> None:
        self.positions: list[tuple[float, float, float]] = []
        self.normals: list[tuple[float, float, float]] = []
        self.uvs: list[tuple[float, float]] = []
        self.bones: list[int] = []
        self.indices: list[int] = []
        self.materials: list[dict] = []

    def add_mesh(
        self,
        positions: np.ndarray,
        normals: np.ndarray,
        faces: np.ndarray,
        uvs: np.ndarray,
        *,
        name: str,
        color: tuple[float, float, float, float],
        bone: int,
        specular: float = 0.15,
    ) -> None:
        start = len(self.positions)
        for pos, normal, uv in zip(positions, normals, uvs):
            self.positions.append(tuple(float(v) for v in pos))
            self.normals.append(tuple(float(v) for v in normal))
            self.uvs.append(tuple(float(v) for v in uv))
            self.bones.append(bone)
        face_start = len(self.indices)
        for face in faces:
            self.indices.extend(int(start + index) for index in face)
        self.materials.append(
            {
                "name": name,
                "color": color,
                "index_count": len(self.indices) - face_start,
                "specular": specular,
            }
        )

    # ------------------------------------------------------------------ shapes
    def sphere(
        self,
        center: tuple[float, float, float],
        radii: tuple[float, float, float],
        *,
        name: str,
        color: tuple[float, float, float, float],
        bone: int,
        segments: int = 20,
        rings: int = 12,
        specular: float = 0.18,
    ) -> None:
        center_v = np.asarray(center, dtype=np.float64)
        radii_v = np.asarray(radii, dtype=np.float64)
        verts: list[np.ndarray] = []
        normals: list[np.ndarray] = []
        uvs: list[tuple[float, float]] = []
        for i in range(rings + 1):
            phi = math.pi * i / rings
            for j in range(segments):
                theta = 2 * math.pi * j / segments
                direction = np.array(
                    [math.sin(phi) * math.cos(theta), math.cos(phi), math.sin(phi) * math.sin(theta)]
                )
                verts.append(center_v + direction * radii_v)
                normal = np.array(
                    [
                        direction[0] / max(radii_v[0] ** 2, 1e-6),
                        direction[1] / max(radii_v[1] ** 2, 1e-6),
                        direction[2] / max(radii_v[2] ** 2, 1e-6),
                    ]
                )
                normals.append(normal / np.linalg.norm(normal))
                uvs.append((j / segments, i / rings))
        faces: list[tuple[int, int, int]] = []
        for i in range(rings):
            for j in range(segments):
                a = i * segments + j
                b = i * segments + (j + 1) % segments
                c = (i + 1) * segments + j
                d = (i + 1) * segments + (j + 1) % segments
                if i != 0:
                    faces.append((a, c, b))
                if i != rings - 1:
                    faces.append((b, c, d))
        self.add_mesh(
            np.asarray(verts),
            np.asarray(normals),
            np.asarray(faces, dtype=np.int64),
            np.asarray(uvs),
            name=name,
            color=color,
            bone=bone,
            specular=specular,
        )

    def taper(
        self,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        r1: float,
        r2: float,
        *,
        name: str,
        color: tuple[float, float, float, float],
        bone: int,
        segments: int = 14,
        specular: float = 0.12,
    ) -> None:
        p0 = np.asarray(start, dtype=np.float64)
        p1 = np.asarray(end, dtype=np.float64)
        axis = p1 - p0
        length = np.linalg.norm(axis)
        if length < 1e-8:
            return
        axis /= length
        helper = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(axis, helper)) > 0.92:
            helper = np.array([0.0, 1.0, 0.0])
        side = np.cross(axis, helper)
        side /= np.linalg.norm(side)
        other = np.cross(axis, side)
        verts: list[np.ndarray] = []
        normals: list[np.ndarray] = []
        uvs: list[tuple[float, float]] = []
        for i, (center, radius) in enumerate(((p0, r1), (p1, r2))):
            for j in range(segments):
                theta = 2 * math.pi * j / segments
                radial = side * math.cos(theta) + other * math.sin(theta)
                verts.append(center + radial * radius)
                normals.append(radial.copy())
                uvs.append((j / segments, float(i)))
        # End caps.
        cap0_index = len(verts)
        verts.append(p0)
        normals.append(-axis)
        uvs.append((0.5, 0.5))
        cap1_index = len(verts)
        verts.append(p1)
        normals.append(axis)
        uvs.append((0.5, 0.5))
        faces: list[tuple[int, int, int]] = []
        for j in range(segments):
            a = j
            b = (j + 1) % segments
            c = segments + j
            d = segments + (j + 1) % segments
            faces.extend([(a, b, c), (b, d, c), (cap0_index, b, a), (cap1_index, c, d)])
        self.add_mesh(
            np.asarray(verts),
            np.asarray(normals),
            np.asarray(faces, dtype=np.int64),
            np.asarray(uvs),
            name=name,
            color=color,
            bone=bone,
            specular=specular,
        )

    def star(
        self,
        center: tuple[float, float, float],
        radius: float,
        depth: float,
        *,
        name: str,
        color: tuple[float, float, float, float],
        bone: int,
        rotation_y: float = 0.0,
    ) -> None:
        cx, cy, cz = center
        points = []
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5
            r = radius if i % 2 == 0 else radius * 0.42
            x = r * math.cos(angle)
            y = r * math.sin(angle)
            points.append((x, y))
        verts = []
        normals = []
        uvs = []
        for z in (cz - depth / 2, cz + depth / 2):
            for x, y in points:
                verts.append((cx + x, cy + y, z))
                normals.append((0, 0, -1 if z < cz else 1))
                uvs.append(((x / radius + 1) / 2, (y / radius + 1) / 2))
        center_front = len(verts)
        verts.append((cx, cy, cz + depth / 2 + 0.01))
        normals.append((0, 0, 1))
        uvs.append((0.5, 0.5))
        center_back = len(verts)
        verts.append((cx, cy, cz - depth / 2 - 0.01))
        normals.append((0, 0, -1))
        uvs.append((0.5, 0.5))
        faces = []
        for i in range(10):
            a = i
            b = (i + 1) % 10
            c = 10 + i
            d = 10 + (i + 1) % 10
            faces.extend([(center_front, a, b), (center_back, d, c)])
            faces.extend([(a, c, b), (b, c, d)])
        self.add_mesh(
            np.asarray(verts),
            np.asarray(normals),
            np.asarray(faces, dtype=np.int64),
            np.asarray(uvs),
            name=name,
            color=color,
            bone=bone,
            specular=0.5,
        )


# ---------------------------------------------------------------------- model
SKIN = (0.98, 0.91, 0.86, 1.0)
DRESS = (0.76, 0.68, 0.97, 1.0)
CAPE = (0.47, 0.39, 0.74, 1.0)
HAT = (0.12, 0.10, 0.20, 1.0)
GOLD = (1.0, 0.80, 0.38, 1.0)
EYE = (0.22, 0.33, 0.65, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
PINK = (0.98, 0.55, 0.64, 1.0)
BOOT = (0.31, 0.27, 0.48, 1.0)
MOUTH = (0.30, 0.14, 0.20, 1.0)


def build_mesh() -> tuple[MeshBuilder, list[dict]]:
    mesh = MeshBuilder()
    # Bones: body=1, head=2, arm_L=3, arm_R=4, leg_L=5, leg_R=6, hat=7, root=0.
    mesh.sphere((0, 3.4, 0), (1.0, 1.18, 0.82), name="躯干", color=DRESS, bone=1)
    mesh.taper((0, 3.7, 0), (0, 1.15, 0), 1.15, 2.0, name="裙摆", color=CAPE, bone=1)
    mesh.taper((0, 4.4, -0.1), (0, 5.15, 0), 0.38, 0.33, name="颈部", color=SKIN, bone=1)
    # Head.
    mesh.sphere((0, 5.78, 0), (1.28, 1.22, 1.14), name="头部", color=SKIN, bone=2, segments=24, rings=15)
    # Hair cap: a slightly larger back half sphere, using a scaled sphere.
    mesh.sphere((0, 5.86, -0.12), (1.34, 1.25, 1.18), name="发冠", color=(0.83, 0.76, 0.99, 1.0), bone=2)
    # Eyes and highlights.
    for side, x in (("L", 0.44), ("R", -0.44)):
        mesh.sphere((x, 5.86, 1.0), (0.21, 0.27, 0.08), name=f"眼{side}", color=EYE, bone=2, segments=14, rings=9, specular=0.7)
        mesh.sphere((x - 0.05, 5.94, 1.08), (0.06, 0.08, 0.03), name=f"高光{side}", color=WHITE, bone=2, segments=8, rings=6, specular=0.9)
        mesh.sphere((x - 0.03, 5.78, 1.09), (0.025, 0.025, 0.02), name=f"星芒{side}", color=GOLD, bone=2, segments=6, rings=4)
        mesh.sphere((x * 1.55, 5.52, 1.0), (0.18, 0.055, 0.025), name=f"腮红{side}", color=PINK, bone=2, segments=10, rings=6)
    mesh.sphere((0, 5.43, 1.08), (0.10, 0.035, 0.025), name="嘴", color=MOUTH, bone=2, segments=10, rings=6)
    # Arms, with mitten hands.
    for side, sx in (("L", 1.0), ("R", -1.0)):
        bone = 3 if sx > 0 else 4
        mesh.taper((sx, 4.12, 0.0), (sx * 1.85, 2.82, 0.32), 0.27, 0.19, name=f"手臂{side}", color=SKIN, bone=bone)
        mesh.sphere((sx * 1.9, 2.68, 0.36), (0.24, 0.24, 0.22), name=f"手{side}", color=SKIN, bone=bone, segments=14, rings=9)
        mesh.taper((sx * 0.9, 4.2, -0.05), (sx * 1.8, 3.05, 0.2), 0.42, 0.28, name=f"袖{side}", color=DRESS, bone=bone)
    # Legs and boots.
    for side, sx in (("L", 0.42), ("R", -0.42)):
        bone = 5 if sx > 0 else 6
        mesh.taper((sx, 2.0, 0.0), (sx * 1.04, 0.55, 0.12), 0.22, 0.17, name=f"腿{side}", color=SKIN, bone=bone)
        mesh.sphere((sx * 1.05, 0.35, 0.18), (0.32, 0.35, 0.46), name=f"鞋{side}", color=BOOT, bone=bone, segments=14, rings=9)
    # Hat brim and cone.
    mesh.taper((0, 6.83, 0), (0, 6.7, 0), 2.3, 2.15, name="帽檐", color=HAT, bone=7, segments=28)
    mesh.taper((0, 6.86, 0), (0, 8.1, -0.15), 1.25, 0.12, name="帽顶", color=HAT, bone=7, segments=24)
    mesh.sphere((0, 8.16, -0.15), (0.2, 0.2, 0.2), name="帽尖", color=GOLD, bone=7, segments=12, rings=8)
    mesh.star((0, 7.65, 0.75), 0.34, 0.08, name="帽星", color=GOLD, bone=7)
    mesh.star((0, 3.7, 1.02), 0.16, 0.05, name="胸口星", color=GOLD, bone=1)
    # Floating star companions, weighted to body.
    for index, (x, y, z, r) in enumerate(
        [(-2.3, 4.6, 0.3, 0.28), (2.35, 5.2, -0.2, 0.22), (-2.0, 8.0, -0.6, 0.18), (2.1, 7.7, -0.4, 0.16)]
    ):
        mesh.star((x, y, z), r, 0.05, name=f"星灵{index}", color=(1.0, 0.88, 0.55, 1.0), bone=1)

    bones = [
        {"name": "root", "parent": -1, "pos": (0.0, 0.0, 0.0)},
        {"name": "body", "parent": 0, "pos": (0.0, 1.15, 0.0)},
        {"name": "head", "parent": 1, "pos": (0.0, 4.9, 0.0)},
        {"name": "arm_L", "parent": 1, "pos": (1.0, 4.12, 0.0)},
        {"name": "arm_R", "parent": 1, "pos": (-1.0, 4.12, 0.0)},
        {"name": "leg_L", "parent": 0, "pos": (0.42, 2.0, 0.0)},
        {"name": "leg_R", "parent": 0, "pos": (-0.42, 2.0, 0.0)},
        {"name": "hat", "parent": 2, "pos": (0.0, 6.7, 0.0)},
    ]
    return mesh, bones


# ------------------------------------------------------------------ PMX writer
def _text(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<i", len(raw)) + raw


def _f(*values: float) -> bytes:
    return struct.pack("<" + "f" * len(values), *values)


def _i16(value: int) -> bytes:
    return struct.pack("<h", value)


def write_pmx(mesh: MeshBuilder, bones: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = bytearray()
    out += b"PMX "
    out += _f(2.0)
    out.append(8)
    out += bytes([1, 0, 4, 1, 1, 2, 1, 1])  # UTF-8, no extra UV, index widths
    out += _text(MODEL_NAME) + _text(MODEL_NAME_EN)
    out += _text("原创示例模型：星灵·露米。由 AIDeskPal-SICK 使用基础几何体生成，以 MIT 许可发布。")
    out += _text("Original sample model generated for AIDeskPal-SICK. MIT licensed.")
    out += struct.pack("<i", len(mesh.positions))
    for pos, normal, uv, bone in zip(mesh.positions, mesh.normals, mesh.uvs, mesh.bones):
        # Write raw MMD-style coordinates; the renderer mirrors Z on load.
        out += _f(pos[0], pos[1], -pos[2])
        out += _f(normal[0], normal[1], -normal[2])
        out += _f(uv[0], uv[1])
        out.append(0)  # BDEF1
        out += _i16(bone)
        out += _f(1.0)
    out += struct.pack("<I", len(mesh.indices))
    out += struct.pack("<" + "I" * len(mesh.indices), *mesh.indices)
    out += struct.pack("<i", 0)  # textures
    out += struct.pack("<i", len(mesh.materials))
    for material in mesh.materials:
        r, g, b, a = material["color"]
        out += _text(material["name"]) + _text(material["name"])
        out += _f(r, g, b, a)
        out += _f(0.20, 0.20, 0.22)
        out += _f(float(material["specular"]))
        out += _f(0.55, 0.55, 0.62)
        out.append(0x03)  # double-sided + receives shadow
        out += _f(0.08, 0.07, 0.10, 1.0)
        out += _f(1.0)
        out += struct.pack("<b", -1)  # texture index (1-byte width)
        out += struct.pack("<b", -1)  # sphere texture index
        out.append(0)
        out.append(1)
        out.append(0)  # built-in toon
        out += _text("")
        out += struct.pack("<I", material["index_count"])
    out += struct.pack("<i", len(bones))
    for index, bone in enumerate(bones):
        out += _text(bone["name"]) + _text(bone["name"])
        out += _f(*bone["pos"])
        out += _i16(int(bone["parent"]))
        out += struct.pack("<i", 0)
        out += struct.pack("<H", 0x1E)  # rotatable, movable, visible, enabled
        out += _f(0.0, 1.0, 0.0)  # tail offset
    out += struct.pack("<i", 0)  # morphs
    out += struct.pack("<i", 1)  # display frames
    out += _text("Root") + _text("Root")
    out.append(0)
    out += struct.pack("<i", 1)
    out.append(0)
    out += _i16(0)
    out += struct.pack("<i", 0)  # rigid bodies
    out += struct.pack("<i", 0)  # joints
    path.write_bytes(bytes(out))
    print(f"wrote {path.relative_to(ROOT)} ({len(out):,} bytes)")


# ------------------------------------------------------------------- actions
def action(
    action_id: str,
    name: str,
    description: str,
    duration: float,
    loop: bool,
    category: str,
    tracks: dict,
    morphs: dict | None = None,
    tags: tuple[str, ...] = (),
    ai_visible: bool = True,
) -> dict:
    return {
        "schema_version": "1.0",
        "model": MODEL_ID,
        "id": action_id,
        "name": name,
        "description": description,
        "category": category,
        "tags": list(tags),
        "loop": loop,
        "duration": duration,
        "fade_in": 0.35,
        "fade_out": 0.4,
        "priority": 40,
        "ai_visible": ai_visible,
        "content": {
            "duration": duration,
            "loop": loop,
            "bones": tracks,
            "morphs": morphs or {},
            "notes": "Starling sample action.",
        },
        "version": "1.0.0",
        "author": AUTHOR,
    }


def build_actions() -> list[dict]:
    actions: list[dict] = []
    actions.append(
        action(
            "idle_twinkle",
            "星灵呼吸",
            "小星灵安静悬浮，身体轻轻起伏，帽子与手臂微微摇晃，偶尔闪一下星光。适合待机与专注陪伴。",
            6.0,
            True,
            "idle",
            {
                "root": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 3, "rot": [0, 1.5, 0]}, {"t": 6, "rot": [0, 0, 0]}]},
                "body": {"translation": [{"t": 0, "trans": [0, 0, 0]}, {"t": 3, "trans": [0, 0.08, 0]}, {"t": 6, "trans": [0, 0, 0]}]},
                "head": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 2, "rot": [2, -3, 3]}, {"t": 4.5, "rot": [-1, 3, -2]}, {"t": 6, "rot": [0, 0, 0]}]},
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, -4]}, {"t": 3, "rot": [0, 0, 8]}, {"t": 6, "rot": [0, 0, -4]}]},
                "arm_R": {"rotation": [{"t": 0, "rot": [0, 0, 4]}, {"t": 3, "rot": [0, 0, -8]}, {"t": 6, "rot": [0, 0, 4]}]},
                "hat": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 3, "rot": [-2, 0, 2]}, {"t": 6, "rot": [0, 0, 0]}]},
            },
            tags=("idle", "gentle", "star"),
        )
    )
    actions.append(
        action(
            "wave_hello",
            "小星灵挥手",
            "抬起一只手臂来回挥动，身体轻微前倾。适合用户回来、打招呼或启动程序时。",
            3.0,
            False,
            "greeting",
            {
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, -4]}, {"t": 0.5, "rot": [0, 0, 88]}, {"t": 0.8, "rot": [0, 0, 72]}, {"t": 1.1, "rot": [0, 0, 96]}, {"t": 1.4, "rot": [0, 0, 72]}, {"t": 1.7, "rot": [0, 0, 96]}, {"t": 2.1, "rot": [0, 0, 80]}, {"t": 2.5, "rot": [0, 0, -4]}]},
                "head": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 0.5, "rot": [0, -6, 7]}, {"t": 2.1, "rot": [0, -4, 5]}, {"t": 3, "rot": [0, 0, 0]}]},
                "body": {"translation": [{"t": 0, "trans": [0, 0, 0]}, {"t": 0.5, "trans": [0, 0.05, 0]}, {"t": 3, "trans": [0, 0, 0]}]},
            },
            tags=("greeting", "wave", "friendly"),
        )
    )
    actions.append(
        action(
            "cheer_hop",
            "开心跳跃",
            "双手举起，原地轻轻跳一下，帽子上的星星跟着弹动。适合用户完成任务或分享好消息时。",
            2.2,
            False,
            "emotion",
            {
                "root": {"translation": [{"t": 0, "trans": [0, 0, 0]}, {"t": 0.3, "trans": [0, 0.65, 0]}, {"t": 0.7, "trans": [0, 0, 0]}, {"t": 2.2, "trans": [0, 0, 0]}]},
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, -4]}, {"t": 0.3, "rot": [0, 0, 125]}, {"t": 1.5, "rot": [0, 0, 118]}, {"t": 2.2, "rot": [0, 0, -4]}]},
                "arm_R": {"rotation": [{"t": 0, "rot": [0, 0, 4]}, {"t": 0.3, "rot": [0, 0, -125]}, {"t": 1.5, "rot": [0, 0, -118]}, {"t": 2.2, "rot": [0, 0, 4]}]},
                "head": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 0.3, "rot": [-8, 0, 5]}, {"t": 1.4, "rot": [-4, 0, -4]}, {"t": 2.2, "rot": [0, 0, 0]}]},
                "hat": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 0.3, "rot": [-9, 0, 0]}, {"t": 0.9, "rot": [4, 0, 0]}, {"t": 2.2, "rot": [0, 0, 0]}]},
            },
            tags=("happy", "jump", "celebrate"),
        )
    )
    actions.append(
        action(
            "spin_dance",
            "星轨旋转",
            "张开双手原地转一圈，帽子与裙摆跟着旋转。适合庆祝、播放音乐或用户请她表演时。",
            4.0,
            False,
            "dance",
            {
                "root": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 1.0, "rot": [0, 120, 0]}, {"t": 2.0, "rot": [0, 240, 0]}, {"t": 3.0, "rot": [0, 360, 0]}, {"t": 4.0, "rot": [0, 360, 0]}]},
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, -4]}, {"t": 0.6, "rot": [0, 0, 65]}, {"t": 3.0, "rot": [0, 0, 65]}, {"t": 4.0, "rot": [0, 0, -4]}]},
                "arm_R": {"rotation": [{"t": 0, "rot": [0, 0, 4]}, {"t": 0.6, "rot": [0, 0, -65]}, {"t": 3.0, "rot": [0, 0, -65]}, {"t": 4.0, "rot": [0, 0, 4]}]},
                "hat": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 1.0, "rot": [-5, 0, 0]}, {"t": 2.0, "rot": [0, 0, 5]}, {"t": 4.0, "rot": [0, 0, 0]}]},
            },
            tags=("dance", "spin", "perform"),
        )
    )
    actions.append(
        action(
            "sleepy_doze",
            "打盹星灵",
            "垂下帽子轻轻打盹，呼吸缓慢，身体每隔几秒点一下头。适合深夜或用户长时间离开时。",
            8.0,
            True,
            "idle",
            {
                "head": {"rotation": [{"t": 0, "rot": [14, 4, 5]}, {"t": 3.5, "rot": [20, 3, 6]}, {"t": 4, "rot": [12, 3, 5]}, {"t": 8, "rot": [14, 4, 5]}]},
                "hat": {"rotation": [{"t": 0, "rot": [4, 0, 3]}, {"t": 4, "rot": [8, 0, 4]}, {"t": 8, "rot": [4, 0, 3]}]},
                "body": {"translation": [{"t": 0, "trans": [0, -0.05, 0]}, {"t": 4, "trans": [0, -0.12, 0]}, {"t": 8, "trans": [0, -0.05, 0]}]},
            },
            tags=("sleep", "night", "calm"),
        )
    )
    actions.append(
        action(
            "comfort_reach",
            "伸出小手",
            "向用户的方向伸出双手，帽子微微倾斜，像在说“我在这里”。适合用户在难过或疲惫时安慰。",
            3.6,
            False,
            "affection",
            {
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, -4]}, {"t": 0.8, "rot": [0, -20, 68]}, {"t": 2.6, "rot": [0, -18, 66]}, {"t": 3.6, "rot": [0, 0, -4]}]},
                "arm_R": {"rotation": [{"t": 0, "rot": [0, 0, 4]}, {"t": 0.8, "rot": [0, 20, -68]}, {"t": 2.6, "rot": [0, 18, -66]}, {"t": 3.6, "rot": [0, 0, 4]}]},
                "head": {"rotation": [{"t": 0, "rot": [0, 0, 0]}, {"t": 0.8, "rot": [4, 6, -5]}, {"t": 2.6, "rot": [3, 6, -5]}, {"t": 3.6, "rot": [0, 0, 0]}]},
            },
            tags=("comfort", "affection", "reach"),
        )
    )
    actions.append(
        action(
            "drag_dangle",
            "被拎起",
            "被动动作：被鼠标拎起时手臂上扬、双腿轻蹬、帽子后仰。不供 AI 选择。",
            3.0,
            True,
            "passive",
            {
                "root": {"rotation": [{"t": 0, "rot": [0, 0, -5]}, {"t": 1.5, "rot": [0, 0, 5]}, {"t": 3, "rot": [0, 0, -5]}]},
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, 35]}, {"t": 1.5, "rot": [0, 0, 48]}, {"t": 3, "rot": [0, 0, 35]}]},
                "arm_R": {"rotation": [{"t": 0, "rot": [0, 0, -35]}, {"t": 1.5, "rot": [0, 0, -48]}, {"t": 3, "rot": [0, 0, -35]}]},
                "leg_L": {"rotation": [{"t": 0, "rot": [-15, 0, 8]}, {"t": 1.5, "rot": [18, 0, 4]}, {"t": 3, "rot": [-15, 0, 8]}]},
                "leg_R": {"rotation": [{"t": 0, "rot": [16, 0, -8]}, {"t": 1.5, "rot": [-12, 0, -4]}, {"t": 3, "rot": [16, 0, -8]}]},
                "hat": {"rotation": [{"t": 0, "rot": [-8, 0, 0]}, {"t": 1.5, "rot": [-12, 0, 4]}, {"t": 3, "rot": [-8, 0, 0]}]},
            },
            ai_visible=False,
            tags=("passive", "drag"),
        )
    )
    actions.append(
        action(
            "drag_land",
            "落地回稳",
            "被动动作：松手后轻轻落地，身体晃一下再恢复。不供 AI 选择。",
            1.2,
            False,
            "passive",
            {
                "root": {"rotation": [{"t": 0, "rot": [0, 0, 8]}, {"t": 0.3, "rot": [0, 0, -4]}, {"t": 0.7, "rot": [0, 0, 2]}, {"t": 1.2, "rot": [0, 0, 0]}]},
                "arm_L": {"rotation": [{"t": 0, "rot": [0, 0, 28]}, {"t": 0.4, "rot": [0, 0, 8]}, {"t": 1.2, "rot": [0, 0, -4]}]},
                "arm_R": {"rotation": [{"t": 0, "rot": [0, 0, -28]}, {"t": 0.4, "rot": [0, 0, -8]}, {"t": 1.2, "rot": [0, 0, 4]}]},
                "hat": {"rotation": [{"t": 0, "rot": [5, 0, 0]}, {"t": 0.5, "rot": [-4, 0, 0]}, {"t": 1.2, "rot": [0, 0, 0]}]},
            },
            ai_visible=False,
            tags=("passive", "drag", "land"),
        )
    )
    return actions


def write_actions(actions: list[dict]) -> None:
    ACTIONS.mkdir(parents=True, exist_ok=True)
    for item in actions:
        path = ACTIONS / f"{item['id']}.json"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "pack_id": "starling_core",
        "name": "星灵·露米 基础动作集",
        "model": MODEL_ID,
        "model_name": MODEL_NAME,
        "version": "1.0.0",
        "author": AUTHOR,
        "license": "MIT",
        "description": "原创示例桌宠的待机、问候、庆祝、表演与拖动被动动作。",
        "character": "character.json",
        "actions": [item["id"] for item in actions],
    }
    (ACTIONS / "pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_market_bundle(actions: list[dict]) -> None:
    SAMPLE.mkdir(parents=True, exist_ok=True)
    (SAMPLE / "model.pmx").parent.mkdir(parents=True, exist_ok=True)
    bundle_actions = SAMPLE / "actions"
    bundle_actions.mkdir(parents=True, exist_ok=True)
    for item in actions:
        (bundle_actions / f"{item['id']}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (bundle_actions / "pack.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "pack_id": "starling_core",
                "name": "星灵·露米 基础动作集",
                "model": MODEL_ID,
                "version": "1.0.0",
                "author": AUTHOR,
                "license": "MIT",
                "character": "character.json",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    readme = """# 星灵·露米 / Starling Lumi

原创示例 PMX 桌宠，由 AIDeskPal-SICK 使用基础几何体程序化生成。

- 许可证：MIT（代码与模型几何）
- 包含 8 个基础动作：待机、挥手、欢呼、旋舞、打盹、伸手、拖动悬空、落地。
- 模型 id：`starling`
- 可用于测试 AIDeskPal-SICK 的 PMX、骨骼、动作与市场安装流程。

注意：本模型是抽象风格的低多边形示例，不是茜特菈莉，也不包含任何第三方角色素材。
"""
    (SAMPLE / "README.md").write_text(readme, encoding="utf-8")
    character_source = ACTIONS / "character.json"
    if character_source.is_file():
        (SAMPLE / "character.json").write_bytes(character_source.read_bytes())
    else:
        raise SystemExit("missing actions/starling/character.json")
    bundle = {
        "schema_version": "1.0",
        "kind": "model_action_bundle",
        "id": "starling_summer",
        "model_id": MODEL_ID,
        "name": "星灵·露米",
        "version": "1.0.0",
        "author": AUTHOR,
        "license": "MIT",
        "summary": "原创星灵桌宠与 8 个基础动作，适合作为 PMX 渲染与动作系统的示例。",
        "description": (
            "星灵·露米是一套原创、MIT 许可的低多边形 PMX 桌宠示例。"
            "她戴着星帽，会安静悬浮、挥手、跳跃、旋转和打盹，也有被拖动时的被动动作。"
            "适合在导入自己的模型前体验 AIDeskPal-SICK，或作为制作动作包的模板。"
        ),
        "tags": ["官方", "示例", "原创", "星灵"],
        "model": {"pmx": "model.pmx", "name": "星灵·露米"},
        "character": "character.json",
        "actions": ["actions/"],
        "cover": "cover.jpg",
    }
    (SAMPLE / "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # An abstract cover is generated separately by the render pipeline; use a copy
    # of the seed cover as a safe placeholder for now.
    cover = MARKET_SEED / "focus_orbit_cover.jpg"
    if cover.is_file():
        (SAMPLE / "cover.jpg").write_bytes(cover.read_bytes())


def zip_market_bundle() -> None:
    MARKET_SEED.mkdir(parents=True, exist_ok=True)
    target = MARKET_SEED / "starling_bundle.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SAMPLE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SAMPLE).as_posix())
    print(f"wrote {target.relative_to(ROOT)} ({target.stat().st_size:,} bytes)")


def main() -> None:
    mesh, bones = build_mesh()
    write_pmx(mesh, bones, SAMPLE / "model.pmx")
    actions = build_actions()
    write_actions(actions)
    write_market_bundle(actions)
    zip_market_bundle()
    print(f"vertices={len(mesh.positions):,} faces={len(mesh.indices) // 3:,} materials={len(mesh.materials)}")


if __name__ == "__main__":
    main()
