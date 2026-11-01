"""Inspect a PMX model's bones, morphs and materials for action authoring.

Usage:
    python tools/dump_pmx.py "D:/path/model.pmx"
    python tools/dump_pmx.py model.pmx --bones-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aideskpal.pmx.model import load_pmx


def main() -> int:
    parser = argparse.ArgumentParser(description="List PMX bones, morphs and materials")
    parser.add_argument("model")
    parser.add_argument("--bones-only", action="store_true")
    args = parser.parse_args()
    model = load_pmx(args.model)
    print(f"Model: {model.name} / {model.name_en}")
    print(f"PMX {model.version:.1f} | {model.vertex_count:,} verts | {model.triangle_count:,} tris")
    print(f"Bounding box: {model.bbox_min} .. {model.bbox_max} | height {model.height:.2f}")
    print("\nBones:")
    for bone in model.bones:
        ik = " IK" if bone.is_ik else ""
        print(
            f"[{bone.index:4d}] {bone.name!r:24} parent={bone.parent_index:4d} "
            f"pos=({bone.position[0]:.2f},{bone.position[1]:.2f},{bone.position[2]:.2f}){ik}"
        )
    if not args.bones_only:
        print("\nMorphs:")
        for morph in model.morphs:
            print(f"[{morph.index:3d}] {morph.type_name:8} {morph.name!r} ({morph.name_en!r})")
        print("\nMaterials:")
        for index, material in enumerate(model.materials):
            print(
                f"[{index:3d}] {material.name!r:20} indices={material.index_count:6d} "
                f"alpha={material.alpha:.2f} texture={material.texture_path or '-'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
