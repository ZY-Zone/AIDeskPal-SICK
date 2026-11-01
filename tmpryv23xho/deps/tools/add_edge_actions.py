"""Author screen-edge poses for Citlali.

Run from the repository root:

    .venv/Scripts/python tools/add_edge_actions.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import author_actions as aa  # noqa: E402

OUT = aa.OUT


def arms_up(height: float) -> dict[str, dict]:
    return {
        "左腕": {
            "rotation": [
                aa.rot(0, (0, -50, -40)),
                aa.rot(0.45, (0, -10, 74), "ease_out"),
                aa.rot(height - 0.5, (0, -8, 77)),
                aa.rot(height, (0, -50, -40)),
            ]
        },
        "右腕": {
            "rotation": [
                aa.rot(0, (0, 50, 40)),
                aa.rot(0.45, (0, 10, -74), "ease_out"),
                aa.rot(height - 0.5, (0, 8, -77)),
                aa.rot(height, (0, 50, 40)),
            ]
        },
        "左ひじ": {
            "rotation": [
                aa.rot(0, (0, 0, 0)),
                aa.rot(0.45, (0, 0, 34)),
                aa.rot(height - 0.5, (0, 0, 30)),
                aa.rot(height, (0, 0, 0)),
            ]
        },
        "右ひじ": {
            "rotation": [
                aa.rot(0, (0, 0, 0)),
                aa.rot(0.45, (0, 0, -34)),
                aa.rot(height - 0.5, (0, 0, -30)),
                aa.rot(height, (0, 0, 0)),
            ]
        },
        "左手首": {
            "rotation": [
                aa.rot(0, (0, 0, 0)),
                aa.rot(0.6, (0, -12, 14)),
                aa.rot(height - 0.5, (0, -10, 10)),
                aa.rot(height, (0, 0, 0)),
            ]
        },
        "右手首": {
            "rotation": [
                aa.rot(0, (0, 0, 0)),
                aa.rot(0.6, (0, 12, -14)),
                aa.rot(height - 0.5, (0, 10, -10)),
                aa.rot(height, (0, 0, 0)),
            ]
        },
    }


def build_actions() -> list[dict]:
    actions: list[dict] = []

    actions.append(
        aa.build(
            action_id="edge_side_hang",
            name="侧边扒屏",
            description="贴在屏幕侧边、双手抓住边缘的半身姿态。",
            category="passive",
            duration=4.0,
            loop=True,
            ai_visible=False,
            priority=0,
            tags=("edge", "hang", "side"),
            tracks=aa.merge(
                arms_up(4.0),
                {
                    "上半身": {"rotation": [aa.rot(0, (2, 0, -2)), aa.rot(2, (2, 0, -1)), aa.rot(4.0, (2, 0, -2))]},
                    "首": {"rotation": [aa.rot(0, (2, 0, 4)), aa.rot(2, (2, 0, 2)), aa.rot(4.0, (2, 0, 4))]},
                    "頭": {"rotation": [aa.rot(0, (2, -8, 8)), aa.rot(1.4, (2, -5, 10)), aa.rot(4.0, (2, -8, 8))]},
                    "左ひざ": {"rotation": [aa.rot(0, (10, 0, 0)), aa.rot(4.0, (10, 0, 0))]},
                    "右ひざ": {"rotation": [aa.rot(0, (16, 0, 0)), aa.rot(4.0, (16, 0, 0))]},
                    "左足": {"rotation": [aa.rot(0, (-8, 0, 1)), aa.rot(4.0, (-8, 0, 1))]},
                    "右足": {"rotation": [aa.rot(0, (-5, 0, -1)), aa.rot(4.0, (-5, 0, -1))]},
                },
                aa.hair_sway(1.2, 2.0),
            ),
            morphs={
                "まばたき": [aa.weight(0, 0), aa.weight(1.6, 0), aa.weight(1.7, 1), aa.weight(1.9, 0), aa.weight(4.0, 0)],
                "なごみ": [aa.weight(0, 0.25), aa.weight(4.0, 0.25)],
            },
            notes="窗口半身在屏幕外；由边缘控制器配合 stage roll 使用。",
        )
    )

    actions.append(
        aa.build(
            action_id="edge_top_grip",
            name="顶部悬挂",
            description="双手扒住屏幕顶部、身体自然垂下的姿态。",
            category="passive",
            duration=5.0,
            loop=True,
            ai_visible=False,
            priority=0,
            tags=("edge", "hang", "top"),
            tracks=aa.merge(
                arms_up(5.0),
                {
                    "上半身": {"rotation": [aa.rot(0, (3, 0, 0)), aa.rot(2.5, (2, 0, 0.5)), aa.rot(5.0, (3, 0, 0))]},
                    "首": {"rotation": [aa.rot(0, (4, 0, 0)), aa.rot(2.5, (3, 0, -1)), aa.rot(5.0, (4, 0, 0))]},
                    "頭": {"rotation": [aa.rot(0, (6, 0, 2)), aa.rot(2.2, (4, 2, 3)), aa.rot(5.0, (6, 0, 2))]},
                    "左ひざ": {"rotation": [aa.rot(0, (18, 0, 0)), aa.rot(2.5, (21, 0, 0)), aa.rot(5.0, (18, 0, 0))]},
                    "右ひざ": {"rotation": [aa.rot(0, (24, 0, 0)), aa.rot(2.5, (21, 0, 0)), aa.rot(5.0, (24, 0, 0))]},
                    "左足": {"rotation": [aa.rot(0, (-10, 0, 2)), aa.rot(5.0, (-10, 0, 2))]},
                    "右足": {"rotation": [aa.rot(0, (-14, 0, -2)), aa.rot(5.0, (-14, 0, -2))]},
                },
                aa.hair_sway(1.8, 2.2),
            ),
            morphs={
                "じと目": [aa.weight(0, 0.2), aa.weight(2.0, 0.35), aa.weight(5.0, 0.2)],
                "まばたき": [aa.weight(0, 0), aa.weight(2.8, 0), aa.weight(2.9, 1), aa.weight(3.1, 0), aa.weight(5.0, 0)],
            },
            notes="双手举过头顶；窗口顶部略微移出屏幕。",
        )
    )

    actions.append(
        aa.build(
            action_id="edge_bottom_sit",
            name="底部鸭子坐",
            description="坐在屏幕底部边缘，膝盖向两侧折开、双手低放。",
            category="passive",
            duration=6.0,
            loop=True,
            ai_visible=False,
            priority=0,
            tags=("edge", "sit", "bottom"),
            tracks=aa.merge(
                {
                    "全ての親": {
                        "rotation": [aa.rot(0, (0, 0, 0)), aa.rot(6.0, (0, 0, 0))],
                        "translation": [
                            aa.trans(0, (0, -1.9, 0)),
                            aa.trans(3.0, (0, -1.92, 0)),
                            aa.trans(6.0, (0, -1.9, 0)),
                        ],
                    },
                    "上半身": {"rotation": [aa.rot(0, (2, 0, 0)), aa.rot(3.0, (2.5, 0, 0.5)), aa.rot(6.0, (2, 0, 0))]},
                    "首": {"rotation": [aa.rot(0, (1, 0, 0)), aa.rot(3.0, (0, 0, 1)), aa.rot(6.0, (1, 0, 0))]},
                    "頭": {"rotation": [aa.rot(0, (1, 0, 2)), aa.rot(3.0, (2, 0, 3)), aa.rot(6.0, (1, 0, 2))]},
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(6.0, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(6.0, (0, 50, 40))]},
                    "左ひじ": {"rotation": [aa.rot(0, (0, 0, 4)), aa.rot(6.0, (0, 0, 4))]},
                    "右ひじ": {"rotation": [aa.rot(0, (0, 0, -4)), aa.rot(6.0, (0, 0, -4))]},
                    "左手首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(6.0, (0, 0, 0))]},
                    "右手首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(6.0, (0, 0, 0))]},
                    "左足": {"rotation": [aa.rot(0, (-52, 30, 55)), aa.rot(6.0, (-52, 30, 55))]},
                    "右足": {"rotation": [aa.rot(0, (-52, -30, -55)), aa.rot(6.0, (-52, -30, -55))]},
                    "左ひざ": {"rotation": [aa.rot(0, (115, 0, -6)), aa.rot(6.0, (115, 0, -6))]},
                    "右ひざ": {"rotation": [aa.rot(0, (115, 0, 6)), aa.rot(6.0, (115, 0, 6))]},
                    "左足首": {"rotation": [aa.rot(0, (58, 0, 10)), aa.rot(6.0, (58, 0, 10))]},
                    "右足首": {"rotation": [aa.rot(0, (58, 0, -10)), aa.rot(6.0, (58, 0, -10))]},
                },
                aa.hair_sway(0.8, 2.0),
            ),
            morphs={
                "まばたき": [aa.weight(0, 0), aa.weight(2.7, 0), aa.weight(2.8, 1), aa.weight(3.0, 0), aa.weight(6.0, 0)],
                "笑い": [aa.weight(0, 0.2), aa.weight(6.0, 0.2)],
            },
            notes="根骨骼下移让臀部贴近屏幕底边；腿部角度由 polish_citlali_motion 统一校准。",
        )
    )

    actions.append(
        aa.build(
            action_id="edge_fall",
            name="边缘摔落",
            description="从侧边或顶部失去平衡、双手乱抓的短促下落动作。",
            category="passive",
            duration=1.2,
            loop=False,
            ai_visible=False,
            priority=0,
            tags=("edge", "fall", "reaction"),
            tracks=aa.merge(
                {
                    "上半身": {"rotation": [aa.rot(0, (4, 0, 0)), aa.rot(0.2, (-4, 0, 0)), aa.rot(0.75, (5, 0, 0)), aa.rot(1.2, (0, 0, 0))]},
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.25, (-4, 0, 3)), aa.rot(1.2, (0, 0, 0))]},
                    "頭": {"rotation": [aa.rot(0, (1, 0, 2)), aa.rot(0.2, (-8, 4, 6)), aa.rot(0.9, (4, -2, -4)), aa.rot(1.2, (1, 0, 2))]},
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(0.2, (0, -12, 78)), aa.rot(0.7, (0, -68, 10)), aa.rot(1.2, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(0.25, (0, 20, -72)), aa.rot(0.8, (0, 66, -14)), aa.rot(1.2, (0, 50, 40))]},
                    "左ひじ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.3, (0, 0, 28)), aa.rot(0.8, (0, 0, 10)), aa.rot(1.2, (0, 0, 0))]},
                    "右ひじ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.3, (0, 0, -32)), aa.rot(0.8, (0, 0, -12)), aa.rot(1.2, (0, 0, 0))]},
                    "左足": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.5, (-12, 0, 3)), aa.rot(1.2, (0, 0, 0))]},
                    "右足": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.5, (-8, 0, -3)), aa.rot(1.2, (0, 0, 0))]},
                    "左ひざ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.5, (18, 0, 0)), aa.rot(1.2, (0, 0, 0))]},
                    "右ひざ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.5, (12, 0, 0)), aa.rot(1.2, (0, 0, 0))]},
                },
                aa.hair_sway(3.0, 0.45),
            ),
            morphs={
                "びっくり": [aa.weight(0, 0), aa.weight(0.15, 0.8), aa.weight(0.9, 0.35), aa.weight(1.2, 0)],
            },
            notes="窗口下落由控制器完成；动作只表现失衡和乱抓。",
        )
    )

    actions.append(
        aa.build(
            action_id="edge_land_sit",
            name="摔落着地",
            description="从边缘落到屏幕底部，轻轻弹一下后坐稳。",
            category="passive",
            duration=1.8,
            loop=False,
            ai_visible=False,
            priority=0,
            tags=("edge", "land", "sit"),
            tracks=aa.merge(
                {
                    "全ての親": {
                        "rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.8, (0, 0, 0))],
                        "translation": [
                            aa.trans(0, (0, 0.8, 0)),
                            aa.trans(0.38, (0, -1.55, 0), "ease_in"),
                            aa.trans(0.58, (0, -1.25, 0), "ease_out"),
                            aa.trans(0.8, (0, -1.42, 0)),
                            aa.trans(1.8, (0, -1.4, 0)),
                        ],
                    },
                    "上半身": {"rotation": [aa.rot(0, (7, 0, 0)), aa.rot(0.4, (10, 0, 0)), aa.rot(0.8, (1, 0, 0)), aa.rot(1.8, (2, 0, 0))]},
                    "首": {"rotation": [aa.rot(0, (5, 0, 0)), aa.rot(0.45, (8, 0, 0)), aa.rot(1.0, (1, 0, 0)), aa.rot(1.8, (1, 0, 0))]},
                    "頭": {"rotation": [aa.rot(0, (8, 0, 2)), aa.rot(0.4, (11, 0, 3)), aa.rot(1.0, (2, 0, 2)), aa.rot(1.8, (1, 0, 2))]},
                    "左腕": {"rotation": [aa.rot(0, (0, -24, 28)), aa.rot(0.4, (0, -38, 12)), aa.rot(1.0, (0, -50, -40)), aa.rot(1.8, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 24, -28)), aa.rot(0.4, (0, 38, -12)), aa.rot(1.0, (0, 50, 40)), aa.rot(1.8, (0, 50, 40))]},
                    "左ひざ": {"rotation": [aa.rot(0, (48, 0, 0)), aa.rot(0.4, (64, 0, 0)), aa.rot(1.8, (58, 0, 0))]},
                    "右ひざ": {"rotation": [aa.rot(0, (48, 0, 0)), aa.rot(0.4, (64, 0, 0)), aa.rot(1.8, (58, 0, 0))]},
                    "左足": {"rotation": [aa.rot(0, (-20, 0, 2)), aa.rot(1.8, (-26, 0, 2))]},
                    "右足": {"rotation": [aa.rot(0, (-20, 0, -2)), aa.rot(1.8, (-26, 0, -2))]},
                },
                aa.hair_sway(2.2, 0.8),
            ),
            morphs={
                "びっくり": [aa.weight(0, 0.55), aa.weight(0.45, 0.2), aa.weight(0.9, 0)],
                "まばたき": [aa.weight(0, 0), aa.weight(1.0, 0), aa.weight(1.1, 1), aa.weight(1.3, 0), aa.weight(1.8, 0)],
            },
            notes="落地后由控制器接 edge_bottom_sit。",
        )
    )
    return actions


def main() -> None:
    actions = build_actions()
    for action in actions:
        aa.write(action, "edge")
    pack_path = OUT / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    existing = list(pack.get("actions", []))
    for action in actions:
        item = f"edge/{action['id']}"
        if item not in existing:
            existing.append(item)
    pack["actions"] = existing
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(actions)} edge actions; pack now lists {len(existing)}")


if __name__ == "__main__":
    main()
