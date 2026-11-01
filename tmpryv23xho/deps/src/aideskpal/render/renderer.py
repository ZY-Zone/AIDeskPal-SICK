"""A small, dependency-light PMX renderer built on OpenGL 3.3."""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path

import numpy as np
from PIL import Image
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_BLEND,
    GL_CLAMP_TO_EDGE,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_ATTACHMENT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_COMPONENT,
    GL_DEPTH_COMPONENT24,
    GL_DEPTH_TEST,
    GL_DYNAMIC_DRAW,
    GL_FRAMEBUFFER,
    GL_FRAMEBUFFER_COMPLETE,
    GL_NONE,
    GL_ELEMENT_ARRAY_BUFFER,
    GL_FALSE,
    GL_FLOAT,
    GL_LEQUAL,
    GL_LINEAR,
    GL_LINEAR_MIPMAP_LINEAR,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_RGBA,
    GL_RGBA32F,
    GL_RGBA8,
    GL_SRC_ALPHA,
    GL_STATIC_DRAW,
    GL_TEXTURE0,
    GL_TEXTURE1,
    GL_TEXTURE2,
    GL_TEXTURE3,
    GL_TEXTURE_2D,
    GL_TEXTURE_BUFFER,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLE_STRIP,
    GL_TRIANGLES,
    GL_UNSIGNED_BYTE,
    GL_UNSIGNED_INT,
    GL_UNPACK_ALIGNMENT,
    glActiveTexture,
    glBindBuffer,
    glBindFramebuffer,
    glBindTexture,
    glBindVertexArray,
    glBlendFunc,
    glBufferData,
    glBufferSubData,
    glCheckFramebufferStatus,
    glClear,
    glClearColor,
    glDeleteBuffers,
    glDeleteFramebuffers,
    glDeleteProgram,
    glDeleteTextures,
    glDeleteVertexArrays,
    glDepthFunc,
    glDisable,
    glDrawArrays,
    glDrawBuffer,
    glDrawElements,
    glEnable,
    glEnableVertexAttribArray,
    glFramebufferTexture2D,
    glGenBuffers,
    glGenFramebuffers,
    glGenTextures,
    glGenVertexArrays,
    glGenerateMipmap,
    glGetUniformLocation,
    glPixelStorei,
    glReadBuffer,
    glTexBuffer,
    glTexImage2D,
    glTexParameteri,
    glUniform1f,
    glUniform1i,
    glUniform2f,
    glUniform3f,
    glUniform4f,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribPointer,
    glViewport,
)
from OpenGL.GL import shaders

from aideskpal.animation.action import ActionClip
from aideskpal.pmx.model import Material, PmxModel
from aideskpal.pmx.skeleton import Pose, Skeleton
from aideskpal.render.shaders import (
    MODEL_FRAGMENT,
    MODEL_VERTEX,
    SHADOW_FRAGMENT,
    SHADOW_VERTEX,
)

logger = logging.getLogger(__name__)


def _compile(vertex_src: str, fragment_src: str, label: str) -> int:
    try:
        vs = shaders.compileShader(vertex_src, 0x8B31)  # GL_VERTEX_SHADER
        fs = shaders.compileShader(fragment_src, 0x8B30)  # GL_FRAGMENT_SHADER
        program = shaders.compileProgram(vs, fs)
        return int(program)
    except Exception as exc:  # pragma: no cover - requires an OpenGL context
        raise RuntimeError(f"Could not compile {label} shader: {exc}") from exc


def _ortho(left: float, right: float, bottom: float, top: float, near: float, far: float) -> np.ndarray:
    return np.array(
        [
            [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
            [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
            [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


class PmxRenderer:
    """Render a PMX into the current framebuffer.

    Call :meth:`initialize` with an active OpenGL 3.3 core context, then
    :meth:`render` for every frame.  The renderer has no Qt dependency.
    """

    def __init__(self, model: PmxModel, opacity: float = 1.0) -> None:
        self.model = model
        self.skeleton = Skeleton(model)
        self.opacity = float(np.clip(opacity, 0.0, 1.0))
        self._initialized = False
        self._positions = model.positions.copy()
        self._normals = model.normals.copy()
        self._uvs = model.uvs.copy()
        self._base_positions = model.positions.copy()
        self._base_normals = model.normals.copy()
        self._morph_arrays: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._build_morphs()
        self._texture_cache: dict[str, int] = {}
        self._material_textures: dict[int, int] = {}
        self._material_spheres: dict[int, int] = {}
        self._model_program = 0
        self._shadow_program = 0
        self._vao = 0
        self._vbo_pos = 0
        self._vbo_nrm = 0
        self._vbo_uv = 0
        self._vbo_bones = 0
        self._bone_buffer = 0
        self._bone_texture = 0
        self._morph_signature: tuple[tuple[int, float], ...] = ()
        self._shadow_texture = 0
        self._shadow_fbo = 0
        self._shadow_map_size = 1024
        self._shadow_enabled = False
        self._light_view_proj = np.eye(4, dtype=np.float32)
        self._ebo = 0
        self._shadow_vao = 0
        self._shadow_vbo = 0
        self._uniforms: dict[str, int] = {}
        self._shadow_uniforms: dict[str, int] = {}
        self._view_proj = np.eye(4, dtype=np.float32)
        self._camera = np.array([0.0, 0.0, 30.0], dtype=np.float32)
        self.stage_roll_degrees = 0.0
        self.stage_yaw_degrees = 0.0
        self.stage_scale = 1.0
        self.contact_shadow_enabled = True
        self._last_pose = Pose.empty()
        self._dummy_texture = 0
        self._visible_materials = 0
        self._last_fit: tuple[float, float, float, float] | None = None
        self._alpha_mask: np.ndarray | None = None
        self._frame_count = 0

    # ------------------------------------------------------------------ setup
    @property
    def initialized(self) -> bool:
        return self._initialized

    def _build_morphs(self) -> None:
        for morph in self.model.morphs:
            if morph.morph_type != 1:
                continue
            indices: list[int] = []
            offsets: list[tuple[float, float, float]] = []
            for vertex_index, offset in morph.offsets:
                if 0 <= vertex_index < len(self.model.vertices):
                    indices.append(vertex_index)
                    offsets.append(offset)
            if indices:
                self._morph_arrays[morph.index] = (
                    np.asarray(indices, dtype=np.int32),
                    np.asarray(offsets, dtype=np.float32),
                )

    def initialize(self) -> None:
        if self._initialized:
            return
        self.model.prepare_arrays()
        if not self.model.render_space:
            raise RuntimeError("PMX model must be converted with to_render_space() before rendering")
        self._model_program = _compile(MODEL_VERTEX, MODEL_FRAGMENT, "model")
        self._shadow_program = _compile(SHADOW_VERTEX, SHADOW_FRAGMENT, "shadow")
        self._uniforms = self._uniform_locations(
            self._model_program,
            [
                "uViewProj",
                "uTexture",
                "uSphereTexture",
                "uDiffuse",
                "uAmbient",
                "uSpecular",
                "uSpecularStrength",
                "uLightDirection",
                "uCameraPosition",
                "uHasTexture",
                "uSphereMode",
                "uAlphaCutoff",
                "uOpacity",
                "uToonStrength",
                "uBoneMatrices",
                "uShadowMap",
                "uLightViewProj",
                "uShadowEnabled",
                "uShadowTexel",
            ],
        )
        self._shadow_uniforms = self._uniform_locations(
            self._shadow_program, ["uViewProj", "uCenter", "uScale", "uColor"]
        )
        self._create_geometry()
        self._dummy_texture = self._create_dummy_texture()
        self._load_textures()
        self._create_shadow_map()
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self._initialized = True
        logger.info(
            "Renderer ready: %d vertices, %d triangles, %d materials",
            self.model.vertex_count,
            self.model.triangle_count,
            len(self.model.materials),
        )

    @staticmethod
    def _uniform_locations(program: int, names: list[str]) -> dict[str, int]:
        return {name: glGetUniformLocation(program, name) for name in names}

    def _create_geometry(self) -> None:
        model = self.model
        self._vao = int(glGenVertexArrays(1))
        glBindVertexArray(self._vao)
        self._vbo_pos = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_pos)
        glBufferData(GL_ARRAY_BUFFER, self._positions.nbytes, self._positions, GL_DYNAMIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))

        self._vbo_nrm = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_nrm)
        glBufferData(GL_ARRAY_BUFFER, self._normals.nbytes, self._normals, GL_DYNAMIC_DRAW)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))

        self._vbo_uv = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_uv)
        glBufferData(GL_ARRAY_BUFFER, self._uvs.nbytes, self._uvs, GL_STATIC_DRAW)
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, 0, ctypes.c_void_p(0))

        # Static skinning attributes: one interleaved vec4 bone-index + vec4
        # weight buffer.  The bone matrices themselves live in a texture buffer
        # and are sampled by the vertex shader, so the CPU never touches 59k
        # vertices per frame.
        bone_indices = np.where(model.bone_indices >= 0, model.bone_indices, 0).astype(np.float32)
        bone_weights = model.bone_weights.astype(np.float32)
        weight_sum = bone_weights.sum(axis=1, keepdims=True)
        bone_weights = np.divide(
            bone_weights,
            weight_sum,
            out=np.zeros_like(bone_weights),
            where=weight_sum > 0,
        )
        skin_attributes = np.hstack([bone_indices, bone_weights]).astype(np.float32)
        self._vbo_bones = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_bones)
        glBufferData(
            GL_ARRAY_BUFFER, skin_attributes.nbytes, skin_attributes, GL_STATIC_DRAW
        )
        stride = 8 * 4
        glEnableVertexAttribArray(3)
        glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(4)
        glVertexAttribPointer(4, 4, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(16))

        self._bone_buffer = int(glGenBuffers(1))
        glBindBuffer(GL_TEXTURE_BUFFER, self._bone_buffer)
        glBufferData(
            GL_TEXTURE_BUFFER,
            self.skeleton.count * 16 * 4,
            None,
            GL_DYNAMIC_DRAW,
        )
        self._bone_texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_BUFFER, self._bone_texture)
        glTexBuffer(GL_TEXTURE_BUFFER, GL_RGBA32F, self._bone_buffer)
        glBindTexture(GL_TEXTURE_BUFFER, 0)

        self._ebo = int(glGenBuffers(1))
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._ebo)
        glBufferData(
            GL_ELEMENT_ARRAY_BUFFER,
            model.indices.nbytes,
            model.indices.astype(np.uint32),
            GL_STATIC_DRAW,
        )
        glBindVertexArray(0)

        quad = np.asarray(
            [-1.0, -1.0, 0.0, -1.0, 1.0, 0.0, 1.0, -1.0, 0.0, 1.0, 1.0, 0.0], dtype=np.float32
        )
        quad_local = np.asarray([-1.0, -1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype=np.float32)
        self._shadow_vao = int(glGenVertexArrays(1))
        glBindVertexArray(self._shadow_vao)
        self._shadow_vbo = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, self._shadow_vbo)
        data = np.hstack([quad.reshape(-1, 3), quad_local.reshape(-1, 2)]).astype(np.float32)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_STATIC_DRAW)
        stride = data.shape[1] * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
        glBindVertexArray(0)

        total_indices = int(sum(m.index_count for m in model.materials))
        if total_indices > len(model.indices):
            logger.warning("Materials reference more indices than the model contains")
        self._visible_materials = sum(1 for material in model.materials if material.index_count)

    def _create_shadow_map(self) -> None:
        """Create a depth-only directional shadow map for self-shadowing."""
        size = self._shadow_map_size
        self._shadow_texture = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self._shadow_texture)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_DEPTH_COMPONENT24,
            size,
            size,
            0,
            GL_DEPTH_COMPONENT,
            GL_FLOAT,
            None,
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)

        self._shadow_fbo = int(glGenFramebuffers(1))
        glBindFramebuffer(GL_FRAMEBUFFER, self._shadow_fbo)
        glFramebufferTexture2D(
            GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, self._shadow_texture, 0
        )
        glDrawBuffer(GL_NONE)
        glReadBuffer(GL_NONE)
        status = int(glCheckFramebufferStatus(GL_FRAMEBUFFER))
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        self._shadow_enabled = status == GL_FRAMEBUFFER_COMPLETE
        if self._shadow_enabled:
            self._light_view_proj = self._compute_light_view_proj()
            logger.info("Self-shadow map ready (%dx%d)", size, size)
        else:
            logger.warning("Shadow map unavailable (framebuffer status 0x%X)", status)

    def _compute_light_view_proj(self) -> np.ndarray:
        model = self.model
        cx = float((model.bbox_min[0] + model.bbox_max[0]) * 0.5)
        cy = float((model.bbox_min[1] + model.bbox_max[1]) * 0.5)
        center = np.array([cx, cy, 0.0], dtype=np.float32)
        light = np.array([-0.26, 0.64, 0.72], dtype=np.float32)
        light /= np.linalg.norm(light)
        width = float(model.bbox_max[0] - model.bbox_min[0])
        depth = float(model.bbox_max[2] - model.bbox_min[2])
        radius = max(width, model.height, depth) * 0.62
        distance = max(20.0, radius * 3.4)
        eye = center + light * distance
        view = _look_at(eye, center, np.array([0.0, 1.0, 0.0], dtype=np.float32))
        projection = _ortho(-radius, radius, -radius, radius, 0.1, distance * 2.4)
        return (projection @ view).astype(np.float32)

    # ------------------------------------------------------------------ textures
    def _create_dummy_texture(self) -> int:
        tex = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, tex)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, b"\xff\xff\xff\xff")
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)
        return tex

    def _resolve_texture(self, relative: str | None) -> Path | None:
        if not relative:
            return None
        direct = self.model.resolve_asset(relative)
        if direct and direct.is_file():
            return direct
        # Case-insensitive fallback for assets authored on Windows and served on Linux.
        name = Path(relative.replace("\\", "/")).name.lower()
        try:
            for candidate in self.model.directory.rglob("*"):
                if candidate.is_file() and candidate.name.lower() == name:
                    return candidate
        except OSError:
            pass
        return None

    def _load_texture(self, relative: str | None) -> int:
        path = self._resolve_texture(relative)
        if path is None:
            return 0
        key = str(path).lower()
        if key in self._texture_cache:
            return self._texture_cache[key]
        try:
            image = Image.open(path).convert("RGBA")
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            data = image.tobytes()
            tex = int(glGenTextures(1))
            glBindTexture(GL_TEXTURE_2D, tex)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA8,
                image.width,
                image.height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                data,
            )
            glGenerateMipmap(GL_TEXTURE_2D)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glBindTexture(GL_TEXTURE_2D, 0)
            self._texture_cache[key] = tex
            return tex
        except Exception as exc:
            logger.warning("Could not load texture %s: %s", path, exc)
            return 0

    def _load_textures(self) -> None:
        for index, material in enumerate(self.model.materials):
            self._material_textures[index] = self._load_texture(material.texture_path)
            self._material_spheres[index] = self._load_texture(material.sphere_texture_path)

    # ------------------------------------------------------------------ frame
    def _apply_morphs(self, morphs: dict[int, float]) -> tuple[np.ndarray, np.ndarray]:
        active = {
            int(index): float(weight)
            for index, weight in morphs.items()
            if abs(float(weight)) > 0.0005
        }
        if not active:
            return self._base_positions, self._base_normals
        positions = self._base_positions.copy()
        for morph_index, weight in active.items():
            if weight <= 0.0005:
                continue
            data = self._morph_arrays.get(morph_index)
            if data is None:
                continue
            indices, offsets = data
            positions[indices] += offsets * float(weight)
        return positions, self._base_normals

    def update_pose(self, pose: Pose) -> None:
        self._last_pose = pose

    def render(self, width: int, height: int, dpr: float = 1.0) -> None:
        if not self._initialized:
            self.initialize()
        width = max(1, int(width))
        height = max(1, int(height))
        if width <= 1 or height <= 1:
            return
        glViewport(0, 0, int(width * dpr), int(height * dpr))
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._view_proj = self._compute_view_proj(width, height)
        pose = self._last_pose
        morph_key = tuple(
            sorted(
                (int(index), round(float(weight), 4))
                for index, weight in pose.morphs.items()
                if abs(float(weight)) > 0.0005
            )
        )
        if morph_key != self._morph_signature:
            positions, normals = self._apply_morphs(pose.morphs)
            self._positions = positions
            self._normals = normals
            self._upload_dynamic()
            self._morph_signature = morph_key

        # Upload the bone matrix palette (columns, because GLSL mat4 is
        # column-major).  This is only a few dozen KB per frame.
        skin = self.skeleton.skin_matrices(pose)
        skin_columns = np.ascontiguousarray(skin.transpose(0, 2, 1), dtype=np.float32)
        glBindBuffer(GL_TEXTURE_BUFFER, self._bone_buffer)
        glBufferSubData(GL_TEXTURE_BUFFER, 0, skin_columns.nbytes, skin_columns)

        self._render_shadow_map(width, height, dpr)

        glUseProgram(self._shadow_program)
        self._draw_shadow(skin)
        glUseProgram(self._model_program)
        self._set_scene_uniforms()
        glBindVertexArray(self._vao)
        glActiveTexture(GL_TEXTURE0)
        for index, material in enumerate(self.model.materials):
            if material.index_count <= 0:
                continue
            self._draw_material(index, material)
        glBindVertexArray(0)
        glUseProgram(0)
        self._frame_count += 1

    def _render_shadow_map(self, width: int, height: int, dpr: float) -> None:
        if not self._shadow_enabled:
            return
        size = self._shadow_map_size
        glBindFramebuffer(GL_FRAMEBUFFER, self._shadow_fbo)
        glViewport(0, 0, size, size)
        glClear(GL_DEPTH_BUFFER_BIT)
        glUseProgram(self._model_program)
        self._set_uniform_mat4("uViewProj", self._light_view_proj)
        glUniform1i(self._uniforms["uBoneMatrices"], 2)
        # Never sample the shadow texture while rendering into its attached FBO.
        glUniform1i(self._uniforms["uShadowEnabled"], 0)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_BUFFER, self._bone_texture)
        glBindVertexArray(self._vao)
        for index, material in enumerate(self.model.materials):
            if material.index_count > 0:
                self._draw_material(index, material)
        glBindVertexArray(0)
        glUseProgram(0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glViewport(0, 0, int(width * dpr), int(height * dpr))

    def _upload_dynamic(self) -> None:
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_pos)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self._positions.nbytes, self._positions)
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo_nrm)
        glBufferSubData(GL_ARRAY_BUFFER, 0, self._normals.nbytes, self._normals)

    def _compute_view_proj(self, width: int, height: float) -> np.ndarray:
        aspect = max(0.2, float(width) / max(1.0, float(height)))
        model = self.model
        cy = float((model.bbox_min[1] + model.bbox_max[1]) * 0.5)
        zoom = max(0.45, min(1.25, float(self.stage_scale)))
        half_h = max(model.height * 0.585 / zoom, 1.0)
        half_w = half_h * aspect
        if half_w < model.height * 0.20:
            half_w = model.height * 0.20
            half_h = half_w / aspect
        cx = float((model.bbox_min[0] + model.bbox_max[0]) * 0.5)
        near, far = 0.1, 100.0
        # The view matrix already centers the camera on the model, so the
        # orthographic frustum must stay symmetric around zero.
        projection = _ortho(-half_w, half_w, -half_h, half_h, near, far)
        yaw = np.radians(float(self.stage_yaw_degrees))
        camera = np.array(
            [cx + 26.0 * np.sin(yaw), cy, 26.0 * np.cos(yaw)], dtype=np.float32
        )
        target = np.array([cx, cy, 0.0], dtype=np.float32)
        forward = target - camera
        forward /= max(1e-6, np.linalg.norm(forward))
        base_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        right = np.cross(forward, base_up)
        right /= max(1e-6, np.linalg.norm(right))
        angle = np.radians(float(self.stage_roll_degrees))
        up = (base_up * np.cos(angle) + right * np.sin(angle)).astype(np.float32)
        view = _look_at(camera, target, up)
        self._camera = camera
        self._last_fit = (cx, cy, half_w, half_h)
        return projection @ view

    def _set_uniform_mat4(self, name: str, matrix: np.ndarray) -> None:
        location = self._uniforms.get(name, -1)
        if location >= 0:
            glUniformMatrix4fv(location, 1, GL_FALSE, np.ascontiguousarray(matrix.T, dtype=np.float32))

    def _set_scene_uniforms(self) -> None:
        self._set_uniform_mat4("uViewProj", self._view_proj)
        light = np.array([-0.26, 0.64, 0.72], dtype=np.float32)
        light /= np.linalg.norm(light)
        glUniform3f(self._uniforms["uLightDirection"], *light)
        glUniform3f(self._uniforms["uCameraPosition"], *self._camera)
        glUniform1f(self._uniforms["uToonStrength"], 0.55)
        glUniform1f(self._uniforms["uOpacity"], self.opacity)
        glUniform1i(self._uniforms["uTexture"], 0)
        glUniform1i(self._uniforms["uSphereTexture"], 1)
        glUniform1i(self._uniforms["uBoneMatrices"], 2)
        glActiveTexture(GL_TEXTURE2)
        glBindTexture(GL_TEXTURE_BUFFER, self._bone_texture)
        self._set_uniform_mat4("uLightViewProj", self._light_view_proj)
        glUniform1i(self._uniforms["uShadowMap"], 3)
        glUniform1i(self._uniforms["uShadowEnabled"], 1 if self._shadow_enabled else 0)
        glUniform1f(self._uniforms["uShadowTexel"], 1.0 / float(self._shadow_map_size))
        glActiveTexture(GL_TEXTURE3)
        glBindTexture(GL_TEXTURE_2D, self._shadow_texture if self._shadow_enabled else 0)

    def _draw_material(self, index: int, material: Material) -> None:
        texture = self._material_textures.get(index, 0)
        has_texture = texture > 0
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture or self._dummy_texture)
        sphere = self._material_spheres.get(index, 0)
        sphere_mode = material.sphere_mode if sphere else 0
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, sphere or self._dummy_texture)
        glActiveTexture(GL_TEXTURE0)

        u = self._uniforms
        glUniform4f(u["uDiffuse"], *[float(v) for v in material.diffuse])
        glUniform3f(u["uAmbient"], *[float(v) * 0.95 for v in material.ambient])
        glUniform3f(u["uSpecular"], *[float(v) for v in material.specular])
        glUniform1f(u["uSpecularStrength"], float(material.specular_strength))
        glUniform1i(u["uHasTexture"], 1 if has_texture else 0)
        glUniform1i(u["uSphereMode"], int(sphere_mode))
        glUniform1f(u["uAlphaCutoff"], 0.015)
        offset = material.index_start * np.dtype(np.uint32).itemsize
        glDrawElements(
            GL_TRIANGLES,
            min(material.index_count, max(0, len(self.model.indices) - material.index_start)),
            GL_UNSIGNED_INT,
            ctypes.c_void_p(offset),
        )

    def _draw_shadow(self, skin: np.ndarray) -> None:
        if not self.contact_shadow_enabled or not len(self._positions):
            return
        model = self.model
        positions, _ = self.skeleton.skin_vertices(skin, self._positions, self._normals)
        # Use the current skinned support surface rather than the rest-pose feet.
        # During a hop the ground stays at rest height and the shadow fades;
        # during sitting it follows the newly lowered seat/leg contact surface.
        minimum = float(positions[:, 1].min())
        threshold = minimum + max(.04, model.height * .015)
        support = positions[positions[:, 1] <= threshold]
        cx = float(np.median(support[:, 0]))
        cz = float(np.median(support[:, 2]))
        rest_minimum = float(model.bbox_min[1])
        ground = min(rest_minimum, minimum) + .025
        lift = max(0.0, minimum - rest_minimum)
        strength = float(np.clip(1.0 - lift / max(.1, model.height * .35), .18, 1.0))
        spread_x = float(np.percentile(support[:, 0], 90) - np.percentile(support[:, 0], 10))
        spread_z = float(np.percentile(support[:, 2], 90) - np.percentile(support[:, 2], 10))
        width = float(np.clip(max(model.height * .24, spread_x * .75), .1, model.height * .55))
        depth = float(np.clip(max(model.height * .028, spread_z * .15), .02, model.height * .08))
        glUniformMatrix4fv(
            self._shadow_uniforms["uViewProj"],
            1,
            GL_FALSE,
            np.ascontiguousarray(self._view_proj.T, dtype=np.float32),
        )
        glUniform3f(self._shadow_uniforms["uCenter"], cx, ground, cz)
        glUniform2f(self._shadow_uniforms["uScale"], width, depth)
        glUniform4f(self._shadow_uniforms["uColor"], 0.018, 0.024, 0.055, 0.42 * strength)
        glDisable(GL_DEPTH_TEST)
        glBindVertexArray(self._shadow_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glEnable(GL_DEPTH_TEST)

    # ------------------------------------------------------------------ output
    def read_alpha_mask(self, width: int, height: int, threshold: float = 0.08) -> np.ndarray:
        """Read the current framebuffer alpha into a (h, w) boolean mask."""
        from OpenGL.GL import glReadPixels

        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            return np.zeros((1, 1), dtype=bool)
        raw = glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE)
        pixels = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
        self._alpha_mask = pixels[:, :, 3] > int(threshold * 255)
        return self._alpha_mask

    def release(self) -> None:
        if not self._initialized:
            return
        if self._model_program:
            glDeleteProgram(self._model_program)
        if self._shadow_program:
            glDeleteProgram(self._shadow_program)
        for texture in set(self._texture_cache.values()) | {self._dummy_texture}:
            if texture:
                glDeleteTextures([texture])
        glDeleteBuffers(1, [self._vbo_pos])
        glDeleteBuffers(1, [self._vbo_nrm])
        glDeleteBuffers(1, [self._vbo_uv])
        glDeleteBuffers(1, [self._vbo_bones])
        glDeleteBuffers(1, [self._bone_buffer])
        glDeleteBuffers(1, [self._ebo])
        glDeleteVertexArrays(1, [self._vao])
        if self._bone_texture:
            glDeleteTextures([self._bone_texture])
        if self._shadow_texture:
            glDeleteTextures([self._shadow_texture])
        if self._shadow_fbo:
            glDeleteFramebuffers(1, [self._shadow_fbo])
        glDeleteBuffers(1, [self._shadow_vbo])
        glDeleteVertexArrays(1, [self._shadow_vao])
        self._initialized = False
