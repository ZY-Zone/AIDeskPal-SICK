"""Measure edge-pose anatomy and screen contact for the Citlali rig.

This is a development probe, not runtime code.  It prints the numbers that the
regression tests assert, so pose authoring can be iterated against measurements
instead of guesswork.

Run from the repository root:

    $env:PYTHONPATH='src'; .venv/Scripts/python tools/measure_edge_poses.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aideskpal.animation.action import parse_action  # noqa: E402
from aideskpal.pmx.model import load_pmx  # noqa: E402
from aideskpal.pmx.skeleton import Skeleton  # noqa: E402
from aideskpal.render.renderer import PmxRenderer  # noqa: E402

MODEL = ROOT / "src/aideskpal/character/茜特菈莉/model.pmx"
ACTIONS = ROOT / "actions/citlali_summer/edge"

SKIN = ("肌", "肌2")
SHOE = ("鞋表情",)
SKIRT = ("裙", "裙内")
BODY = ("肌", "肌2", "体", "手")


def material_masks(model):
    masks: dict[str, np.ndarray] = {}
    offset = 0
    for material in model.materials:
        indices = model.indices[offset:offset + material.index_count]
        offset += material.index_count
        mask = np.zeros(len(model.positions), dtype=bool)
        mask[np.unique(indices)] = True
        masks[material.name] = mask
    return masks


def group(masks, names) -> np.ndarray:
    out = np.zeros(next(iter(masks.values())).shape, dtype=bool)
    for name in names:
        if name in masks:
            out |= masks[name]
    return out


def load(model, action_id):
    return parse_action(json.loads((ACTIONS / f"{action_id}.json").read_text(encoding="utf-8")), model)


def skin(rig, model, clip, time):
    pose = clip.sample(float(time))
    world = rig.world_matrices(pose)
    points, _ = rig.skin_vertices(rig.skin_matrices(pose), model.positions, model.normals)
    return world, points


def project_with(model, points, roll, yaw, scale, width, height):
    proxy = SimpleNamespace(
        model=model,
        stage_scale=float(scale),
        stage_roll_degrees=float(roll),
        stage_yaw_degrees=float(yaw),
    )
    matrix = PmxRenderer._compute_view_proj(proxy, width, height)
    clip = np.c_[points, np.ones(len(points))] @ matrix.T
    valid = np.abs(clip[:, 3]) > 1e-8
    ndc = np.zeros((len(points), 2), dtype=np.float32)
    ndc[valid] = clip[valid, :2] / clip[valid, 3:4]
    return (1 + ndc[:, 0]) * width * 0.5, (1 - ndc[:, 1]) * height * 0.5


def main() -> None:
    model = load_pmx(MODEL)
    model.to_render_space()
    rig = Skeleton(model)
    masks = material_masks(model)
    body = group(masks, BODY)
    shoe = group(masks, SHOE)
    skirt = group(masks, SKIRT)
    bone = {name: model.bone_index(name) for name in (
        "頭", "首", "上半身", "上半身2", "下半身", "左肩", "右肩",
        "左腕", "右腕", "左ひじ", "右ひじ", "左手首", "右手首",
        "左足", "右足", "左ひざ", "右ひざ", "左足首", "右足首",
        "左つま先", "右つま先",
    )}

    for action_id in ("edge_side_hang", "edge_top_grip", "edge_bottom_sit"):
        clip = load(model, action_id)
        print(f"=== {action_id}  duration={clip.duration:.2f} loop={clip.loop}")
        for time in (0.0, clip.duration * 0.5):
            world, points = skin(rig, model, clip, time)
            low = np.argmin(points[:, 1])
            top = np.argmax(points[:, 1])
            owner = next((name for name, mask in masks.items() if mask[low]), "?")
            owner_top = next((name for name, mask in masks.items() if mask[top]), "?")
            print(
                f"  t={time:.2f} mesh y {points[:, 1].min():6.2f}..{points[:, 1].max():6.2f}"
                f"  lowest={owner} highest={owner_top}"
            )
            for label, mask in (("skin", body), ("shoe", shoe), ("skirt", skirt)):
                if mask.any():
                    print(
                        f"    {label:5s} y {points[mask, 1].min():6.2f}..{points[mask, 1].max():6.2f}"
                        f"  x {points[mask, 0].min():6.2f}..{points[mask, 0].max():6.2f}"
                    )
            for name, index in bone.items():
                if index < 0:
                    continue
                point = world[index][:3, 3]
                print(
                    f"    {name:<8s} x={point[0]:6.2f} y={point[1]:6.2f} z={point[2]:6.2f}"
                )


if __name__ == "__main__":
    main()
