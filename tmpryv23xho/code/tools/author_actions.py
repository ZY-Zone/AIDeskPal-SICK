"""Author the bundled Citlali action pack.

The JSON files in ``actions/citlali_summer`` are the source of truth shipped with
the application; this script keeps the repetitive base pose consistent while the
creative keyframes remain readable.  Run it from the repository root:

    .venv/Scripts/python tools/author_actions.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "actions" / "citlali_summer"

MODEL = "citlali_summer"

BASE = {
    "全ての親": (0.0, 0.0, 0.0),
    "センター": (0.0, 0.0, 0.0),
    "腰": (0.0, 0.0, 0.0),
    "上半身": (0.0, 0.0, 0.0),
    "上半身2": (1.0, 0.0, 0.0),
    "首": (0.0, 0.0, 0.0),
    "頭": (1.0, 0.0, 2.0),
    "左肩": (0.0, 0.0, 0.0),
    "右肩": (0.0, 0.0, 0.0),
    "左腕": (0.0, -50.0, -40.0),
    "右腕": (0.0, 50.0, 40.0),
    "左ひじ": (0.0, 0.0, 0.0),
    "右ひじ": (0.0, 0.0, 0.0),
    "左手首": (0.0, 0.0, 0.0),
    "右手首": (0.0, 0.0, 0.0),
    "左足": (0.0, 0.0, 0.0),
    "右足": (0.0, 0.0, 0.0),
    "左ひざ": (0.0, 0.0, 0.0),
    "右ひざ": (0.0, 0.0, 0.0),
    "左足首": (0.0, 0.0, 0.0),
    "右足首": (0.0, 0.0, 0.0),
    "左HairA_1": (0.0, 0.0, 0.0),
    "右HairA_1": (0.0, 0.0, 0.0),
    "Bone_HairB01_L": (0.0, 0.0, 0.0),
    "Bone_HairC01_R": (0.0, 0.0, 0.0),
    "左HairF01": (0.0, 0.0, 0.0),
    "右HairF01": (0.0, 0.0, 0.0),
}


def rot(t: float, angles: tuple[float, float, float], ease: str = "smooth") -> dict:
    return {"t": round(t, 3), "rot": [round(float(v), 3) for v in angles], "ease": ease}


def trans(t: float, offset: tuple[float, float, float], ease: str = "smooth") -> dict:
    return {"t": round(t, 3), "trans": [round(float(v), 3) for v in offset], "ease": ease}


def weight(t: float, w: float, ease: str = "smooth") -> dict:
    return {"t": round(t, 3), "w": round(float(w), 3), "ease": ease}


def base_tracks(duration: float) -> dict[str, dict]:
    tracks = {}
    for bone, angles in BASE.items():
        tracks[bone] = {"rotation": [rot(0, angles), rot(duration, angles)]}
    tracks["全ての親"]["translation"] = [trans(0, (0, 0, 0)), trans(duration, (0, 0, 0))]
    return tracks


def build(
    *,
    action_id: str,
    name: str,
    description: str,
    category: str,
    duration: float,
    loop: bool,
    tracks: dict[str, dict] | None = None,
    morphs: dict[str, list[dict]] | None = None,
    tags: tuple[str, ...] = (),
    priority: int = 50,
    fade_in: float = 0.35,
    fade_out: float = 0.4,
    ai_visible: bool = True,
    notes: str = "",
) -> dict:
    content_tracks = base_tracks(duration)
    for bone, data in (tracks or {}).items():
        merged = content_tracks.get(bone, {})
        merged.update(data)
        content_tracks[bone] = merged
    return {
        "schema_version": "1.0",
        "model": MODEL,
        "id": action_id,
        "name": name,
        "description": description,
        "category": category,
        "tags": list(tags),
        "loop": loop,
        "duration": duration,
        "fade_in": fade_in,
        "fade_out": fade_out,
        "priority": priority,
        "ai_visible": ai_visible,
        "content": {
            "duration": duration,
            "loop": loop,
            "fade_in": fade_in,
            "fade_out": fade_out,
            "bones": content_tracks,
            "morphs": morphs or {},
            "notes": notes,
        },
        "version": "1.0.0",
        "author": "AIDeskPal-SICK",
    }


def hair_sway(amplitude: float, phase: float = 1.0) -> dict[str, dict]:
    return {
        "左HairA_1": {"rotation": [rot(0, (0.0, 0.0, 0.0)), rot(phase, (-amplitude, 0.0, 0.0)), rot(phase * 2, (0.0, 0.0, 0.0))]},
        "右HairA_1": {"rotation": [rot(0, (0.0, 0.0, 0.0)), rot(phase, (-amplitude, 0.0, 0.0)), rot(phase * 2, (0.0, 0.0, 0.0))]},
        "Bone_HairB01_L": {"rotation": [rot(0, (0.0, 0.0, 0.0)), rot(phase * 1.2, (-amplitude * 0.8, 0.0, amplitude * 0.4)), rot(phase * 2.4, (0.0, 0.0, 0.0))]},
        "Bone_HairC01_R": {"rotation": [rot(0, (0.0, 0.0, 0.0)), rot(phase * 1.1, (-amplitude * 0.7, 0.0, -amplitude * 0.4)), rot(phase * 2.2, (0.0, 0.0, 0.0))]},
        "左HairF01": {"rotation": [rot(0, (0.0, 0.0, 0.0)), rot(phase * 1.15, (-amplitude * 0.6, 0.0, 0.0)), rot(phase * 2.3, (0.0, 0.0, 0.0))]},
        "右HairF01": {"rotation": [rot(0, (0.0, 0.0, 0.0)), rot(phase * 1.15, (-amplitude * 0.6, 0.0, 0.0)), rot(phase * 2.3, (0.0, 0.0, 0.0))]},
    }


def merge(*dicts: dict) -> dict:
    out: dict = {}
    for source in dicts:
        for key, value in source.items():
            out[key] = value
    return out


def write(action: dict, subdir: str = "") -> None:
    directory = OUT / subdir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{action['id']}.json"
    path.write_text(json.dumps(action, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", path.relative_to(ROOT))


def main() -> None:
    actions: list[tuple[dict, str]] = []

    # ---------------------------------------------------------------- idle 01
    actions.append(
        (
            build(
                action_id="idle_starlight",
                name="星幕静候",
                category="idle",
                duration=12.0,
                loop=True,
                priority=10,
                fade_in=0.8,
                fade_out=0.8,
                tags=("calm", "idle", "breathing"),
                description=(
                    "安静地站在桌面上，双手轻叠在身前，呼吸很轻，偶尔眨眼并微微偏头。"
                    "适用于用户正在专注工作、没有明确互动需求，或茜特菈莉想安静陪伴的时刻。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(4, (0.7, 0.4, 0.4)), rot(8, (0.2, -0.3, -0.4)), rot(12, (0, 0, 0))]},
                        "上半身2": {"rotation": [rot(0, (1, 0, 0)), rot(4, (1.8, 0, 0.8)), rot(8, (0.5, 0, -0.5)), rot(12, (1, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(3.2, (0.2, 3.5, 3.5)), rot(6.6, (1.2, -1.5, 1.2)), rot(9.4, (0.4, -3.5, 2.8)), rot(12, (1, 0, 2))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(4, (0.3, 1.2, 0.4)), rot(8, (0.1, -1.0, -0.2)), rot(12, (0, 0, 0))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(6, (0.5, -51, -41.5)), rot(12, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(6, (0.5, 51, 41.5)), rot(12, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(6, (0, 0, -2)), rot(12, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(6, (0, 0, 2)), rot(12, (0, 0, 0))]},
                    },
                    hair_sway(1.4, 4.0),
                ),
                morphs={
                    "まばたき": [weight(0, 0), weight(3.7, 0), weight(3.85, 1), weight(4.05, 0), weight(8.1, 0), weight(8.25, 1), weight(8.45, 0), weight(12, 0)],
                    "にこり": [weight(0, 0.22), weight(4, 0.35), weight(8, 0.18), weight(12, 0.22)],
                },
                notes="基础待机呼吸循环。手部保持在身前，避免穿过宽大的裙摆。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- idle 02
    actions.append(
        (
            build(
                action_id="idle_watch",
                name="四处张望",
                category="idle",
                duration=10.0,
                loop=True,
                priority=12,
                tags=("curious", "idle", "look"),
                description=(
                    "好奇地左右张望，像在观察桌面和房间，眼珠会跟着头的方向转动，偶尔眨眼。"
                    "适用于用户刚回到电脑前、切换了窗口，或气氛太安静时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(2.5, (0, -2.2, -0.5)), rot(5.5, (0, 2.5, 0.5)), rot(8, (0, 0.8, 0)), rot(10, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(2.5, (0, -5, 0)), rot(5.5, (0, 5, 0)), rot(10, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(2.5, (0, -14, 4)), rot(4.2, (0, -11, 1)), rot(5.5, (-1, 14, -3)), rot(7.4, (-3, 9, -2)), rot(10, (1, 0, 2))]},
                        "左目": {"rotation": [rot(0, (0, 0, 0)), rot(2.5, (0, -4, 0)), rot(5.5, (0, 4, 0)), rot(10, (0, 0, 0))]},
                        "右目": {"rotation": [rot(0, (0, 0, 0)), rot(2.5, (0, -4, 0)), rot(5.5, (0, 4, 0)), rot(10, (0, 0, 0))]},
                        "左肩": {"rotation": [rot(0, (0, 0, 0)), rot(5.5, (0, 1.5, 0)), rot(10, (0, 0, 0))]},
                    },
                    hair_sway(1.1, 3.3),
                ),
                morphs={
                    "まばたき": [weight(0, 0), weight(1.7, 0), weight(1.8, 1), weight(2.0, 0), weight(6.6, 0), weight(6.7, 1), weight(6.9, 0), weight(10, 0)],
                    "にこり": [weight(0, 0.18), weight(5, 0.28), weight(10, 0.18)],
                },
                notes="张望时眼珠与头部分开运动，避免头部大角度旋转造成头发穿模。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- wave
    actions.append(
        (
            build(
                action_id="wave_hello",
                name="挥手打招呼",
                category="greeting",
                duration=3.5,
                loop=False,
                priority=70,
                tags=("greeting", "wave", "happy"),
                description=(
                    "抬起一只手到肩上方，手掌轻轻左右挥动，带着笑意见向用户打招呼。"
                    "适用于用户启动程序、回到座位、或长时间专注后第一次看过来时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 1.5, -1.5)), rot(2.4, (0, 1.0, -1.2)), rot(3.5, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.5, (0, -5, 6)), rot(1.5, (0, -4, 6)), rot(2.5, (0, -2, 3)), rot(3.5, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.5, (0, -14, 66), "ease_out"), rot(0.9, (0, -10, 72)), rot(2.2, (0, -10, 72)), rot(2.8, (0, -30, 10), "ease_in"), rot(3.5, (0, -50, -40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 0, 28), "ease_out"), rot(0.9, (0, 0, 38)), rot(1.2, (0, 20, 22)), rot(1.45, (0, -14, 42)), rot(1.7, (0, 18, 25)), rot(1.95, (0, -12, 40)), rot(2.2, (0, 0, 34)), rot(2.8, (0, 0, 8)), rot(3.5, (0, 0, 0))]},
                        "左手首": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (0, 0, 10)), rot(1.2, (0, 20, 10)), rot(1.45, (0, -16, 10)), rot(1.7, (0, 20, 10)), rot(1.95, (0, -14, 8)), rot(2.2, (0, 0, 8)), rot(2.8, (0, 0, 0)), rot(3.5, (0, 0, 0))]},
                        "左肩": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 0, 8)), rot(2.2, (0, 0, 8)), rot(3.5, (0, 0, 0))]},
                    },
                    hair_sway(1.8, 1.7),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.5, 0.8), weight(2.6, 0.75), weight(3.5, 0.2)],
                    "まばたき": [weight(0, 0), weight(1.8, 0), weight(1.9, 1), weight(2.1, 0), weight(3.5, 0)],
                },
                notes="左手（画面右侧）挥动；手腕与前臂错开相位，看起来更自然。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- cheer
    actions.append(
        (
            build(
                action_id="cheer_hop",
                name="欢呼小跳",
                category="emotion",
                duration=2.8,
                loop=False,
                priority=80,
                tags=("happy", "excited", "jump"),
                description=(
                    "双手举高，原地开心地小跳两下，发梢跟着弹动。"
                    "适用于用户完成任务、测试通过、游戏胜利，或收到好消息的时候。"
                ),
                tracks=merge(
                    {
                        "全ての親": {
                            "rotation": [rot(0, (0, 0, 0)), rot(2.8, (0, 0, 0))],
                            "translation": [trans(0, (0, 0, 0)), trans(0.35, (0, 0.65, 0), "ease_out"), trans(0.75, (0, 0, 0), "ease_in"), trans(1.35, (0, 0.5, 0), "ease_out"), trans(1.75, (0, 0, 0), "ease_in"), trans(2.8, (0, 0, 0))],
                        },
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.35, (-4, 0, 0)), rot(0.75, (2, 0, 0)), rot(1.35, (-4, 0, 0)), rot(1.75, (1, 0, 0)), rot(2.8, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.35, (-8, 0, 4)), rot(0.75, (2, 0, 1)), rot(1.35, (-6, 0, -4)), rot(1.75, (3, 0, 2)), rot(2.8, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.35, (0, -12, 74), "ease_out"), rot(0.9, (0, -16, 68)), rot(2.0, (0, -14, 72)), rot(2.5, (0, -45, -20)), rot(2.8, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.35, (0, 12, -74), "ease_out"), rot(0.9, (0, 16, -68)), rot(2.0, (0, 14, -72)), rot(2.5, (0, 45, 20)), rot(2.8, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.35, (0, 0, 22)), rot(1.75, (0, 0, 18)), rot(2.8, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.35, (0, 0, -22)), rot(1.75, (0, 0, -18)), rot(2.8, (0, 0, 0))]},
                        "左ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.2, (8, 0, 0)), rot(0.75, (0, 0, 0)), rot(1.2, (8, 0, 0)), rot(1.75, (0, 0, 0)), rot(2.8, (0, 0, 0))]},
                        "右ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.2, (8, 0, 0)), rot(0.75, (0, 0, 0)), rot(1.2, (8, 0, 0)), rot(1.75, (0, 0, 0)), rot(2.8, (0, 0, 0))]},
                    },
                    hair_sway(4.2, 0.7),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.25, 0.9), weight(2.4, 0.85), weight(2.8, 0.2)],
                    "まばたき": [weight(0, 0), weight(1.0, 0), weight(1.1, 1), weight(1.3, 0), weight(2.8, 0)],
                },
                notes="根骨骼抬升让鞋底离开桌面；落地时膝盖微屈吸收冲击，不做夸张物理。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- stretch
    actions.append(
        (
            build(
                action_id="stretch_yawn",
                name="伸懒腰",
                category="idle",
                duration=5.0,
                loop=False,
                priority=40,
                tags=("tired", "stretch", "yawn"),
                description=(
                    "双手向上伸展，上身微微后仰，打一个很轻的哈欠，然后慢慢回到站姿。"
                    "适用于用户已经工作很久、深夜、或桌宠自己也显得困倦的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(1.1, (-5, 0, 0)), rot(2.8, (-5, 0, 0)), rot(4.2, (1, 0, 0)), rot(5, (0, 0, 0))]},
                        "上半身2": {"rotation": [rot(0, (1, 0, 0)), rot(1.1, (-3, 0, 0)), rot(2.8, (-3, 0, 0)), rot(5, (1, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (-3, 0, 0)), rot(2.8, (-2, 0, 0)), rot(5, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(1.2, (-10, 0, 1)), rot(2.8, (-8, 2, 2)), rot(4.2, (4, 0, 2)), rot(5, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(1.2, (0, -18, 76), "ease_out"), rot(2.7, (0, -15, 82)), rot(4.0, (0, -48, -34)), rot(5, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(1.2, (0, 18, -76), "ease_out"), rot(2.7, (0, 15, -82)), rot(4.0, (0, 48, 34)), rot(5, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, 12)), rot(2.7, (0, 0, 18)), rot(4.0, (0, 0, 2)), rot(5, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, -12)), rot(2.7, (0, 0, -18)), rot(4.0, (0, 0, -2)), rot(5, (0, 0, 0))]},
                        "全ての親": {
                            "rotation": [rot(0, (0, 0, 0)), rot(5, (0, 0, 0))],
                            "translation": [trans(0, (0, 0, 0)), trans(1.4, (0, 0.18, 0)), trans(2.8, (0, 0.2, 0)), trans(4.2, (0, 0, 0)), trans(5, (0, 0, 0))],
                        },
                    },
                    hair_sway(2.4, 1.3),
                ),
                morphs={
                    "まばたき": [weight(0, 0), weight(0.9, 0), weight(1.05, 0.75), weight(2.8, 0.8), weight(3.4, 0), weight(5, 0)],
                    "あ": [weight(0, 0), weight(1.0, 0.55), weight(2.6, 0.45), weight(3.3, 0), weight(5, 0)],
                    "にこり": [weight(0, 0.18), weight(4.2, 0.35), weight(5, 0.18)],
                },
                notes="伸懒腰期间眼睛半闭；根骨骼只上升 0.2，防止鞋底明显穿地。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- shy
    actions.append(
        (
            build(
                action_id="shy_fidget",
                name="害羞扭捏",
                category="emotion",
                duration=5.0,
                loop=False,
                priority=60,
                tags=("shy", "cute", "affection"),
                description=(
                    "脸微微发红，视线躲开，双手在身前不安地绞在一起，身体轻轻左右摇晃。"
                    "适用于用户夸奖她、长时间注视、或者说了让她不好意思的话时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (2, -2, 1)), rot(2.8, (2, 2, -1)), rot(4.2, (1, 0, 0)), rot(5, (0, 0, 0))]},
                        "腰": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 1.5, 1.5)), rot(2.8, (0, -1.5, -1.5)), rot(5, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (3, -3, 2)), rot(2.8, (3, 3, -2)), rot(5, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(1.2, (8, -8, 9)), rot(2.8, (8, 6, -4)), rot(4.2, (4, 2, 4)), rot(5, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(1.2, (0, -62, -22)), rot(2.8, (0, -58, -27)), rot(5, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(1.2, (0, 62, 22)), rot(2.8, (0, 58, 27)), rot(5, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, -18)), rot(2.8, (0, 0, -10)), rot(5, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, 18)), rot(2.8, (0, 0, 10)), rot(5, (0, 0, 0))]},
                        "左手首": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 12, 8)), rot(2.8, (0, -8, -6)), rot(5, (0, 0, 0))]},
                        "右手首": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, -12, -8)), rot(2.8, (0, 8, 6)), rot(5, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, 2.5)), rot(2.8, (0, 0, -1.5)), rot(5, (0, 0, 0))]},
                        "右足": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, -2.5)), rot(2.8, (0, 0, 1.5)), rot(5, (0, 0, 0))]},
                    },
                    hair_sway(1.5, 1.9),
                ),
                morphs={
                    "恥ずかしい": [weight(0, 0), weight(0.8, 0.7), weight(3.5, 0.65), weight(5, 0)],
                    "にこり": [weight(0, 0.2), weight(1.2, 0.45), weight(4.3, 0.3), weight(5, 0.2)],
                    "まばたき": [weight(0, 0), weight(1.5, 0), weight(1.62, 1), weight(1.8, 0), weight(3.9, 0), weight(4.0, 1), weight(4.2, 0), weight(5, 0)],
                },
                notes="害羞动作不使用大幅位移，靠头、肩和脚尖的小动作传达情绪。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- angry
    actions.append(
        (
            build(
                action_id="angry_pout",
                name="鼓腮生气",
                category="emotion",
                duration=3.6,
                loop=False,
                priority=65,
                tags=("angry", "pout", "comedy"),
                description=(
                    "皱眉鼓腮，双手叉在腰侧，跺一下脚并别过头，明显在闹小脾气。"
                    "适用于被用户冷落、被调侃、或用户做了她不喜欢的事情时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.4, (2, -3, -2)), rot(1.2, (0, 4, 2)), rot(2.4, (0, -2, 0)), rot(3.6, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.4, (4, -6, 0)), rot(2.4, (3, 8, 0)), rot(3.6, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.4, (10, -12, -4), "ease_out"), rot(1.0, (8, -8, 3)), rot(1.5, (8, 10, -3)), rot(2.2, (7, 6, 1)), rot(2.8, (3, 0, 2)), rot(3.6, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.5, (0, -62, -12)), rot(2.4, (0, -60, -16)), rot(3.6, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.5, (0, 62, 12)), rot(2.4, (0, 60, 16)), rot(3.6, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 0, -55)), rot(2.4, (0, 0, -55)), rot(3.6, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 0, 55)), rot(2.4, (0, 0, 55)), rot(3.6, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(0.55, (0, 0, -8), "ease_out"), rot(0.85, (0, 0, 3)), rot(1.1, (0, 0, 0)), rot(3.6, (0, 0, 0))]},
                        "左ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.55, (16, 0, 0)), rot(0.9, (0, 0, 0)), rot(3.6, (0, 0, 0))]},
                    },
                    hair_sway(2.9, 1.1),
                ),
                morphs={
                    "怒り目": [weight(0, 0), weight(0.3, 0.9), weight(2.9, 0.85), weight(3.6, 0)],
                    "怒り": [weight(0, 0), weight(0.3, 0.65), weight(2.9, 0.6), weight(3.6, 0)],
                    "口角下げ": [weight(0, 0), weight(0.3, 0.7), weight(2.9, 0.6), weight(3.6, 0)],
                    "まばたき": [weight(0, 0), weight(1.9, 0), weight(2.0, 1), weight(2.2, 0), weight(3.6, 0)],
                },
                notes="叉腰姿势利用上臂外旋和肘部折叠；不真正移动手部骨骼，避免手指穿模。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- surprise
    actions.append(
        (
            build(
                action_id="surprised",
                name="惊讶弹起",
                category="emotion",
                duration=2.0,
                loop=False,
                priority=90,
                tags=("surprise", "reaction", "jump"),
                description=(
                    "突然受惊，肩膀一缩、双手弹起，整个人轻轻跳离桌面，眼睛睁大。"
                    "适用于突然的巨大声音、用户突然快速移动窗口、或意外事件出现时。"
                ),
                fade_in=0.12,
                tracks=merge(
                    {
                        "全ての親": {
                            "rotation": [rot(0, (0, 0, 0)), rot(2, (0, 0, 0))],
                            "translation": [trans(0, (0, 0, 0), "linear"), trans(0.15, (0, 0.38, 0), "ease_out"), trans(0.5, (0, 0, 0), "ease_in"), trans(2, (0, 0, 0))],
                        },
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.18, (-5, 0, 0), "ease_out"), rot(0.7, (1, 0, 0)), rot(2, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.18, (-7, 0, 0)), rot(0.8, (0, 0, 0)), rot(2, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.18, (-10, -7, 5), "ease_out"), rot(0.9, (2, 4, 1)), rot(2, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.16, (0, -30, 10), "ease_out"), rot(0.6, (0, -42, -20)), rot(2, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.16, (0, 30, -10), "ease_out"), rot(0.6, (0, 42, 20)), rot(2, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.16, (0, 0, 35)), rot(0.7, (0, 0, 10)), rot(2, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.16, (0, 0, -35)), rot(0.7, (0, 0, -10)), rot(2, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(0.16, (-12, 0, 0)), rot(0.5, (0, 0, 0)), rot(2, (0, 0, 0))]},
                        "右足": {"rotation": [rot(0, (0, 0, 0)), rot(0.16, (-12, 0, 0)), rot(0.5, (0, 0, 0)), rot(2, (0, 0, 0))]},
                    },
                    hair_sway(6.5, 0.6),
                ),
                morphs={
                    "びっくり": [weight(0, 0), weight(0.12, 1, "ease_out"), weight(0.8, 0.9), weight(1.5, 0.35), weight(2, 0)],
                    "あ": [weight(0, 0), weight(0.15, 0.65), weight(0.7, 0.5), weight(1.4, 0.15), weight(2, 0)],
                    "まばたき": [weight(0, 0), weight(1.1, 0), weight(1.2, 1), weight(1.4, 0), weight(2, 0)],
                },
                notes="快速起跳与收缩，0.12 秒进入，强调突然性。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- headpat
    actions.append(
        (
            build(
                action_id="headpat_reaction",
                name="摸头回应",
                category="reaction",
                duration=4.2,
                loop=False,
                priority=85,
                tags=("affection", "headpat", "shy", "closed_eyes"),
                description=(
                    "意识到被摸头，先是轻轻一缩，然后闭眼偏头蹭向那只手，露出腼腆的笑。"
                    "适用于用户用鼠标在头部附近点击或抚摸、表达关心时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.35, (2, -2, 0)), rot(1.3, (4, -3, 1)), rot(3.2, (4, -3, 1)), rot(4.2, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.35, (-2, -3, 3)), rot(1.3, (5, -5, 7)), rot(3.2, (5, -5, 7)), rot(4.2, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.35, (-2, -5, 8)), rot(1.3, (7, -9, 13)), rot(2.6, (5, -7, 11)), rot(3.2, (7, -8, 12)), rot(4.2, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(1.3, (0, -58, -30)), rot(3.2, (0, -58, -30)), rot(4.2, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(1.3, (0, 58, 30)), rot(3.2, (0, 58, 30)), rot(4.2, (0, 50, 40))]},
                        "右足": {"rotation": [rot(0, (0, 0, 0)), rot(1.3, (0, 0, 3)), rot(3.2, (0, 0, 3)), rot(4.2, (0, 0, 0))]},
                    },
                    hair_sway(1.8, 1.5),
                ),
                morphs={
                    "恥ずかしい": [weight(0, 0), weight(0.5, 0.55), weight(3.2, 0.5), weight(4.2, 0)],
                    "にこり": [weight(0, 0.2), weight(1.2, 0.8), weight(3.3, 0.75), weight(4.2, 0.2)],
                    "まばたき": [weight(0, 0), weight(0.4, 0), weight(0.75, 1), weight(0.95, 0.4), weight(1.2, 1), weight(3.2, 1), weight(3.5, 0), weight(4.2, 0)],
                },
                notes="头往一侧压低并偏转，配合闭眼与脸红；不模拟实际手掌位置。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- think
    actions.append(
        (
            build(
                action_id="think_hmm",
                name="托腮思考",
                category="idle",
                duration=5.0,
                loop=False,
                priority=35,
                tags=("think", "curious", "idle"),
                description=(
                    "歪着头思考，一只手抬到脸侧，目光看向斜上方，过一会儿轻轻点头。"
                    "适用于用户提出复杂问题、长时间盯着屏幕，或桌宠在策划下一步行动时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 2, 1)), rot(3.8, (0, 2, 1)), rot(5, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (-2, -4, 3)), rot(3.8, (-2, -4, 3)), rot(5, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(1.2, (-4, 6, 10)), rot(2.8, (-6, 9, 7)), rot(3.8, (2, 4, 10)), rot(5, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(1.2, (0, -28, 18), "ease_out"), rot(3.8, (0, -30, 16)), rot(5, (0, -50, -40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, -35, 115), "ease_out"), rot(3.8, (0, -35, 112)), rot(5, (0, 0, 0))]},
                        "左手首": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 10, 18)), rot(3.8, (0, 10, 18)), rot(5, (0, 0, 0))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(1.2, (0, 54, 36)), rot(3.8, (0, 54, 36)), rot(5, (0, 50, 40))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, 8)), rot(3.8, (0, 0, 8)), rot(5, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(1.2, (0, 0, 1.5)), rot(3.8, (0, 0, 1.5)), rot(5, (0, 0, 0))]},
                    },
                    hair_sway(1.6, 1.7),
                ),
                morphs={
                    "まばたき": [weight(0, 0), weight(2.2, 0), weight(2.35, 1), weight(2.55, 0), weight(4.4, 0), weight(4.5, 1), weight(4.7, 0), weight(5, 0)],
                    "口角上げ": [weight(0, 0), weight(1.2, 0.15), weight(5, 0)],
                },
                notes="手抬到脸侧的姿势由肩部前旋与肘部大角度折叠组合，未使用 IK。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- laugh
    actions.append(
        (
            build(
                action_id="laugh_soft",
                name="轻笑",
                category="emotion",
                duration=4.0,
                loop=False,
                priority=55,
                tags=("happy", "laugh", "smile"),
                description=(
                    "肩膀轻轻颤动，头微微后仰，闭眼笑出声，身体跟着笑意上下起伏。"
                    "适用于用户讲了有趣的梗、聊天氛围轻松，或她自己想到开心事的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (-3, 0, 1)), rot(0.85, (1, 0, -1)), rot(1.2, (-3, 0, 1)), rot(1.55, (1, 0, -1)), rot(2.3, (-1, 0, 0)), rot(4, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (-5, 0, 0)), rot(1.2, (-3, 0, 0)), rot(2.3, (0, 0, 0)), rot(4, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.5, (-7, 3, 3)), rot(0.85, (-3, 1, 1)), rot(1.2, (-7, 3, 3)), rot(1.55, (-3, 1, 1)), rot(2.3, (-2, 0, 2)), rot(4, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.5, (0, -55, -32)), rot(2.3, (0, -54, -33)), rot(4, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.5, (0, 55, 32)), rot(2.3, (0, 54, 33)), rot(4, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 0, -10)), rot(1.2, (0, 0, -3)), rot(2.3, (0, 0, -8)), rot(4, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (0, 0, 10)), rot(1.2, (0, 0, 3)), rot(2.3, (0, 0, 8)), rot(4, (0, 0, 0))]},
                        "左ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (4, 0, 0)), rot(2.2, (2, 0, 0)), rot(4, (0, 0, 0))]},
                        "右ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.5, (4, 0, 0)), rot(2.2, (2, 0, 0)), rot(4, (0, 0, 0))]},
                    },
                    hair_sway(2.7, 0.8),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.4, 0.9), weight(2.5, 0.85), weight(3.4, 0.4), weight(4, 0.2)],
                    "笑い": [weight(0, 0), weight(0.4, 0.85), weight(2.5, 0.8), weight(3.4, 0.25), weight(4, 0)],
                    "まばたき": [weight(0, 0), weight(2.8, 0), weight(2.9, 1), weight(3.1, 0), weight(4, 0)],
                },
                notes="笑的时候眼睛由「笑い」闭合，嘴巴保持微笑。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- sleep
    actions.append(
        (
            build(
                action_id="sleepy_doze",
                name="打盹",
                category="idle",
                duration=10.0,
                loop=True,
                priority=20,
                tags=("sleep", "tired", "loop"),
                description=(
                    "低着头慢慢打盹，眼睛闭上，呼吸变得很缓，偶尔因为快睡着而轻轻点一下头。"
                    "适用于深夜、用户很久没有操作、或明确让她休息的时候。"
                ),
                fade_in=1.0,
                fade_out=1.0,
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (3, 0, 1)), rot(4, (4.5, 0, 1.5)), rot(8, (3, 0, 0.5)), rot(10, (3, 0, 1))]},
                        "首": {"rotation": [rot(0, (6, 0, 2)), rot(4, (8, 0, 3)), rot(8, (5, 0, 1)), rot(10, (6, 0, 2))]},
                        "頭": {"rotation": [rot(0, (12, 3, 5)), rot(3, (17, 4, 6), "ease_out"), rot(3.6, (9, 3, 4), "ease_in"), rot(4.6, (14, 3, 5)), rot(8, (18, 2, 7), "ease_out"), rot(8.5, (11, 2, 4)), rot(10, (12, 3, 5))]},
                        "左腕": {"rotation": [rot(0, (0, -54, -36)), rot(5, (0, -55, -35)), rot(10, (0, -54, -36))]},
                        "右腕": {"rotation": [rot(0, (0, 54, 36)), rot(5, (0, 55, 35)), rot(10, (0, 54, 36))]},
                        "上半身2": {"rotation": [rot(0, (1, 0, 0)), rot(5, (1.7, 0, 0.3)), rot(10, (1, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 1)), rot(10, (0, 0, 1))]},
                        "右足": {"rotation": [rot(0, (0, 0, -1)), rot(10, (0, 0, -1))]},
                    },
                    hair_sway(1.0, 5.0),
                ),
                morphs={
                    "まばたき": [weight(0, 1), weight(10, 1)],
                    "にこり": [weight(0, 0.1), weight(10, 0.1)],
                },
                notes="眼睛保持闭合。「まばたき」权重 1 表示闭眼；偶尔点头表现打瞌睡。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- star gaze
    actions.append(
        (
            build(
                action_id="starlit_gaze",
                name="仰望星幕",
                category="idle",
                duration=8.0,
                loop=True,
                priority=18,
                tags=("dreamy", "stars", "calm"),
                description=(
                    "抬起头望向不存在的星空，眼睛里浮起星芒，双手在胸前轻轻交握，慢慢呼吸。"
                    "适用于夜晚、用户放音乐、或气氛安静而温柔的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (-2, 0, 0)), rot(4, (-3, 0, 1)), rot(8, (-2, 0, 0))]},
                        "首": {"rotation": [rot(0, (-4, 0, 0)), rot(4, (-6, 0, 0)), rot(8, (-4, 0, 0))]},
                        "頭": {"rotation": [rot(0, (-9, 2, 3)), rot(4, (-12, -2, 5)), rot(8, (-9, 2, 3))]},
                        "左腕": {"rotation": [rot(0, (0, -54, -36)), rot(4, (0, -55, -36.5)), rot(8, (0, -54, -36))]},
                        "右腕": {"rotation": [rot(0, (0, 54, 36)), rot(4, (0, 55, 36.5)), rot(8, (0, 54, 36))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, -7)), rot(4, (0, 0, -8)), rot(8, (0, 0, -7))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 7)), rot(4, (0, 0, 8)), rot(8, (0, 0, 7))]},
                    },
                    hair_sway(1.3, 4.0),
                ),
                morphs={
                    "星目": [weight(0, 0.75), weight(2, 0.9), weight(6, 0.85), weight(8, 0.75)],
                    "にこり": [weight(0, 0.5), weight(4, 0.6), weight(8, 0.5)],
                    "まばたき": [weight(0, 0), weight(3.2, 0), weight(3.3, 0.7), weight(3.5, 0.7), weight(3.7, 0), weight(8, 0)],
                },
                notes="「星目」是模型自带的眼睛星芒 morph；仰望时配合轻笑。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- bow
    actions.append(
        (
            build(
                action_id="bow_greet",
                name="欠身问候",
                category="greeting",
                duration=3.0,
                loop=False,
                priority=60,
                tags=("greeting", "polite", "bow"),
                description=(
                    "双手轻贴身侧，端正地欠身行礼，停留片刻后优雅地直起身。"
                    "适用于初次见面、用户明确打招呼、或表达礼貌感谢的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (22, 0, 0), "ease_out"), rot(1.5, (24, 0, 0)), rot(2.4, (2, 0, 0), "ease_out"), rot(3, (0, 0, 0))]},
                        "上半身2": {"rotation": [rot(0, (1, 0, 0)), rot(0.8, (5, 0, 0)), rot(1.5, (6, 0, 0)), rot(2.4, (1, 0, 0)), rot(3, (1, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (8, 0, 0)), rot(1.5, (10, 0, 0)), rot(2.4, (0, 0, 0)), rot(3, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.8, (10, 0, 2)), rot(1.5, (12, 0, 2)), rot(2.4, (1, 0, 2)), rot(3, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.8, (0, -20, -62)), rot(1.5, (0, -18, -65)), rot(2.4, (0, -49, -41)), rot(3, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.8, (0, 20, 62)), rot(1.5, (0, 18, 65)), rot(2.4, (0, 49, 41)), rot(3, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (0, 0, -5)), rot(1.5, (0, 0, -5)), rot(3, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (0, 0, 5)), rot(1.5, (0, 0, 5)), rot(3, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (-4, 0, 0)), rot(2.4, (0, 0, 0)), rot(3, (0, 0, 0))]},
                        "右足": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (-4, 0, 0)), rot(2.4, (0, 0, 0)), rot(3, (0, 0, 0))]},
                    },
                    hair_sway(2.5, 1.2),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.8, 0.5), weight(2.4, 0.4), weight(3, 0.2)],
                    "まばたき": [weight(0, 0), weight(1.9, 0), weight(2.0, 1), weight(2.2, 0), weight(3, 0)],
                },
                notes="欠身时双臂自然内收，避免穿过宽裙摆；礼毕缓慢回正。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- nod / no
    actions.append(
        (
            build(
                action_id="nod_yes",
                name="点头答应",
                category="reaction",
                duration=2.0,
                loop=False,
                priority=50,
                tags=("agree", "nod", "reaction"),
                description=(
                    "认真地点两下头表示同意，眼睛看着用户，嘴角带一点笑意。"
                    "适用于用户提出请求、说完计划，或问「好不好」的时候。"
                ),
                tracks=merge(
                    {
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.35, (7, 0, 0)), rot(0.65, (0, 0, 0)), rot(0.95, (6, 0, 0)), rot(1.3, (0, 0, 0)), rot(2, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.35, (10, 0, 2)), rot(0.65, (-1, 0, 2)), rot(0.95, (8, 0, 2)), rot(1.3, (0, 0, 2)), rot(2, (1, 0, 2))]},
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.45, (2, 0, 0)), rot(1.2, (0, 0, 0)), rot(2, (0, 0, 0))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.5, (0, -52, -38)), rot(2, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.5, (0, 52, 38)), rot(2, (0, 50, 40))]},
                    },
                    hair_sway(1.2, 0.7),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.5, 0.55), weight(1.6, 0.5), weight(2, 0.2)],
                    "まばたき": [weight(0, 0), weight(0.8, 0), weight(0.9, 1), weight(1.1, 0), weight(2, 0)],
                },
                notes="小小的点头，不带动全身。",
            ),
            "",
        )
    )
    actions.append(
        (
            build(
                action_id="shake_no",
                name="摇头拒绝",
                category="reaction",
                duration=2.4,
                loop=False,
                priority=52,
                tags=("refuse", "shake", "reaction"),
                description=(
                    "轻轻左右摇头，表情认真但不算生气，像在说「这样不行哦」。"
                    "适用于用户提出她不愿意做的事、或需要提醒用户停下来的时候。"
                ),
                tracks=merge(
                    {
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.3, (0, -7, 0)), rot(0.65, (0, 7, 0)), rot(1.0, (0, -5, 0)), rot(1.35, (0, 3, 0)), rot(1.8, (0, 0, 0)), rot(2.4, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.3, (2, -13, 2)), rot(0.65, (2, 13, 1)), rot(1.0, (1, -8, 2)), rot(1.35, (1, 5, 2)), rot(1.8, (1, 0, 2)), rot(2.4, (1, 0, 2))]},
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.3, (0, -2, 0)), rot(0.65, (0, 2, 0)), rot(1.0, (0, -1, 0)), rot(2.4, (0, 0, 0))]},
                        "左手首": {"rotation": [rot(0, (0, 0, 0)), rot(0.7, (0, -10, 0)), rot(1.5, (0, 0, 0)), rot(2.4, (0, 0, 0))]},
                    },
                    hair_sway(1.8, 0.8),
                ),
                morphs={
                    "真面目": [weight(0, 0), weight(0.3, 0.5), weight(1.8, 0.45), weight(2.4, 0)],
                    "口角下げ": [weight(0, 0), weight(0.3, 0.3), weight(1.8, 0.25), weight(2.4, 0)],
                },
                notes="摇头时头发跟随，但幅度小于头部，营造重量感。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- point
    actions.append(
        (
            build(
                action_id="point_there",
                name="指向那边",
                category="gesture",
                duration=3.2,
                loop=False,
                priority=58,
                tags=("point", "attention", "gesture"),
                description=(
                    "顺着某个方向抬起手臂并指过去，同时转头看过去，像是在提醒用户注意。"
                    "适用于发现了新窗口、用户问「在哪里」，或想引导用户看某件东西时。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.6, (0, -4, -2)), rot(2.4, (0, -4, -2)), rot(3.2, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.6, (0, 8, 2)), rot(2.4, (0, 8, 2)), rot(3.2, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.6, (-2, 13, -3)), rot(2.4, (-2, 12, -3)), rot(3.2, (1, 0, 2))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.6, (0, -4, -12), "ease_out"), rot(2.4, (0, -2, -14)), rot(3.2, (0, 50, 40))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.6, (0, 0, 4)), rot(2.4, (0, 0, 4)), rot(3.2, (0, 0, 0))]},
                        "右手首": {"rotation": [rot(0, (0, 0, 0)), rot(0.6, (0, 0, 6)), rot(2.4, (0, 0, 6)), rot(3.2, (0, 0, 0))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.6, (0, -52, -38)), rot(2.4, (0, -52, -38)), rot(3.2, (0, -50, -40))]},
                    },
                    hair_sway(1.6, 1.6),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.6, 0.4), weight(2.7, 0.35), weight(3.2, 0.2)],
                    "まばたき": [weight(0, 0), weight(1.7, 0), weight(1.8, 1), weight(2.0, 0), weight(3.2, 0)],
                },
                notes="右臂向外侧展开指向；视角是正面，指向方向由头部转动强调。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- dance
    actions.append(
        (
            build(
                action_id="dance_spin",
                name="星轨旋舞",
                category="dance",
                duration=5.0,
                loop=False,
                priority=75,
                tags=("dance", "spin", "show"),
                description=(
                    "双臂轻轻展开，原地转一整圈，裙摆和头发跟着旋转，最后稳稳停住。"
                    "适用于用户播放音乐、庆祝、或想看她表演一段的时候。"
                ),
                tracks=merge(
                    {
                        "全ての親": {
                            "rotation": [rot(0, (0, 0, 0)), rot(1.0, (0, 90, 0), "ease_in_out"), rot(1.8, (0, 225, 0), "linear"), rot(2.8, (0, 360, 0), "ease_out"), rot(5, (0, 360, 0))],
                            "translation": [trans(0, (0, 0, 0)), trans(1.3, (0, 0.18, 0)), trans(2.0, (0, 0, 0)), trans(5, (0, 0, 0))],
                        },
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (-2, 0, -2)), rot(2.0, (1, 0, 2)), rot(3.2, (0, 0, 0)), rot(4.0, (1, 0, 0)), rot(5, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.8, (-2, 5, 4)), rot(2.2, (1, -5, -3)), rot(3.4, (1, 0, 2)), rot(5, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.7, (0, -18, 8)), rot(2.2, (0, -30, 30)), rot(3.5, (0, -35, 10)), rot(4.2, (0, -48, -30)), rot(5, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.7, (0, 18, -8)), rot(2.2, (0, 30, -30)), rot(3.5, (0, 35, -10)), rot(4.2, (0, 48, 30)), rot(5, (0, 50, 40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.7, (0, 0, -8)), rot(2.2, (0, 0, -18)), rot(3.5, (0, 0, -5)), rot(5, (0, 0, 0))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.7, (0, 0, 8)), rot(2.2, (0, 0, 18)), rot(3.5, (0, 0, 5)), rot(5, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (-6, 0, 0)), rot(1.6, (2, 0, 0)), rot(2.8, (0, 0, 0)), rot(5, (0, 0, 0))]},
                        "右足": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (4, 0, 0)), rot(1.6, (-4, 0, 0)), rot(2.8, (0, 0, 0)), rot(5, (0, 0, 0))]},
                        "左ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (6, 0, 0)), rot(2.8, (0, 0, 0)), rot(5, (0, 0, 0))]},
                        "右ひざ": {"rotation": [rot(0, (0, 0, 0)), rot(0.8, (4, 0, 0)), rot(2.8, (0, 0, 0)), rot(5, (0, 0, 0))]},
                    },
                    hair_sway(7.0, 0.75),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.8, 0.75), weight(4.2, 0.65), weight(5, 0.2)],
                    "まばたき": [weight(0, 0), weight(3.7, 0), weight(3.8, 1), weight(4.0, 0), weight(5, 0)],
                },
                notes="根骨骼分三段旋转 90/225/360 度，避免四元数插值走最短路径导致反向。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- focus
    actions.append(
        (
            build(
                action_id="focus_company",
                name="安静陪工",
                category="idle",
                duration=9.0,
                loop=True,
                priority=15,
                tags=("focus", "work", "quiet", "companion"),
                description=(
                    "把双手轻轻交叠在身前，低头看着键盘的方向，安静地陪着用户工作，几乎不打扰。"
                    "适用于用户在写代码、写文档、玩游戏或长时间使用电脑的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (2, 0, 0)), rot(4.5, (2.6, 0, 0)), rot(9, (2, 0, 0))]},
                        "首": {"rotation": [rot(0, (2, 0, 0)), rot(4.5, (3, 0, 0)), rot(9, (2, 0, 0))]},
                        "頭": {"rotation": [rot(0, (7, 0, 2)), rot(4.5, (8, 2, 2)), rot(9, (7, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -52, -36)), rot(4.5, (0, -53, -35)), rot(9, (0, -52, -36))]},
                        "右腕": {"rotation": [rot(0, (0, 52, 36)), rot(4.5, (0, 53, 35)), rot(9, (0, 52, 36))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, -4)), rot(4.5, (0, 0, -3)), rot(9, (0, 0, -4))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 4)), rot(4.5, (0, 0, 3)), rot(9, (0, 0, 4))]},
                    },
                    hair_sway(0.9, 4.5),
                ),
                morphs={
                    "まばたき": [weight(0, 0), weight(5.6, 0), weight(5.7, 1), weight(5.9, 0), weight(9, 0)],
                    "にこり": [weight(0, 0.12), weight(4.5, 0.18), weight(9, 0.12)],
                },
                notes="给专注场景的低存在感待机，不频繁移动。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- reach
    actions.append(
        (
            build(
                action_id="reach_out",
                name="伸手靠近",
                category="affection",
                duration=4.2,
                loop=False,
                priority=68,
                tags=("affection", "comfort", "reach"),
                description=(
                    "向用户的方向伸出手，掌心向上，像是想碰碰用户或递出什么东西，眼神温柔。"
                    "适用于用户情绪低落、需要安慰、或者她主动想靠近用户的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (5, 0, -2)), rot(2.8, (5, 0, -2)), rot(4.2, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (4, 2, -2)), rot(2.8, (4, 2, -2)), rot(4.2, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.9, (4, 5, -4)), rot(2.8, (3, 5, -4)), rot(4.2, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.9, (0, -68, -18), "ease_out"), rot(2.8, (0, -66, -20)), rot(4.2, (0, -50, -40))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (0, 0, -4)), rot(2.8, (0, 0, -3)), rot(4.2, (0, 0, 0))]},
                        "左手首": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (0, 20, 0)), rot(2.8, (0, 22, 0)), rot(4.2, (0, 0, 0))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.9, (0, 55, 32)), rot(2.8, (0, 55, 32)), rot(4.2, (0, 50, 40))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (0, 0, 6)), rot(2.8, (0, 0, 6)), rot(4.2, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (0, 0, 0)), rot(0.9, (-3, 0, 0)), rot(2.8, (-3, 0, 0)), rot(4.2, (0, 0, 0))]},
                    },
                    hair_sway(1.7, 1.6),
                ),
                morphs={
                    "にこり": [weight(0, 0.2), weight(0.9, 0.55), weight(3.4, 0.5), weight(4.2, 0.2)],
                    "まばたき": [weight(0, 0), weight(2.5, 0), weight(2.6, 1), weight(2.8, 0), weight(4.2, 0)],
                },
                notes="左臂向前下方伸，手心朝上；不显示额外道具。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- poke
    actions.append(
        (
            build(
                action_id="poke_reaction",
                name="被戳一下",
                category="reaction",
                duration=1.4,
                loop=False,
                priority=88,
                fade_in=0.08,
                tags=("reaction", "poke", "cute"),
                description=(
                    "被鼠标戳到后肩膀一抖，迅速转头看过来，眼睛睁圆，像在问「干嘛呀」。"
                    "适用于用户直接点击身体、想引起注意的时候。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (0, 0, 0)), rot(0.12, (0, -3, -1), "ease_out"), rot(0.45, (0, 1, 1)), rot(1.4, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (0, 0, 0)), rot(0.12, (0, 7, 1)), rot(1.4, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (1, 0, 2)), rot(0.12, (-3, 14, 3), "ease_out"), rot(0.8, (-1, 8, 2)), rot(1.4, (1, 0, 2))]},
                        "左肩": {"rotation": [rot(0, (0, 0, 0)), rot(0.12, (0, 0, 5)), rot(0.6, (0, 0, 0)), rot(1.4, (0, 0, 0))]},
                        "左腕": {"rotation": [rot(0, (0, -50, -40)), rot(0.12, (0, -52, -35)), rot(1.4, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 50, 40)), rot(0.12, (0, 52, 35)), rot(1.4, (0, 50, 40))]},
                    },
                    hair_sway(2.6, 0.55),
                ),
                morphs={
                    "びっくり": [weight(0, 0), weight(0.1, 0.75), weight(0.5, 0.5), weight(1.2, 0), weight(1.4, 0)],
                    "まばたき": [weight(0, 0), weight(0.7, 0), weight(0.8, 1), weight(1.0, 0), weight(1.4, 0)],
                },
                notes="短促的点击反馈；动作结束后由交互控制层回到待机。",
            ),
            "",
        )
    )

    # ---------------------------------------------------------------- drag hold
    actions.append(
        (
            build(
                action_id="drag_dangle",
                name="被拎起·悬空",
                category="passive",
                duration=3.0,
                loop=True,
                priority=95,
                fade_in=0.15,
                fade_out=0.3,
                ai_visible=False,
                tags=("passive", "drag", "dangle"),
                description=(
                    "被拎起时使用的被动循环：身体微微悬空，手臂上抬，双腿交替轻蹬，头发下垂。"
                    "不供 AI 自由选择，由拖动交互层强制播放。"
                ),
                tracks=merge(
                    {
                        "全ての親": {
                            "rotation": [rot(0, (0, 0, -3)), rot(0.8, (0, 0, 3.5)), rot(1.6, (0, 0, -2)), rot(2.4, (0, 0, 3)), rot(3, (0, 0, -3))],
                            "translation": [trans(0, (0, 0.75, 0)), trans(0.8, (0, 0.95, 0)), trans(1.6, (0, 0.7, 0)), trans(2.4, (0, 0.95, 0)), trans(3, (0, 0.75, 0))],
                        },
                        "上半身": {"rotation": [rot(0, (4, 0, 2)), rot(0.8, (6, 0, -2)), rot(1.6, (3, 0, 2)), rot(2.4, (6, 0, -1)), rot(3, (4, 0, 2))]},
                        "首": {"rotation": [rot(0, (-2, 0, 0)), rot(1.5, (-4, 0, 1)), rot(3, (-2, 0, 0))]},
                        "頭": {"rotation": [rot(0, (-6, 3, 4)), rot(0.8, (-4, -4, -2)), rot(1.6, (-7, 2, 5)), rot(2.4, (-4, -3, -1)), rot(3, (-6, 3, 4))]},
                        "左腕": {"rotation": [rot(0, (0, -30, 8)), rot(0.8, (0, -27, 13)), rot(1.6, (0, -32, 5)), rot(2.4, (0, -26, 15)), rot(3, (0, -30, 8))]},
                        "右腕": {"rotation": [rot(0, (0, 30, -8)), rot(0.8, (0, 27, -13)), rot(1.6, (0, 32, -5)), rot(2.4, (0, 26, -15)), rot(3, (0, 30, -8))]},
                        "左ひじ": {"rotation": [rot(0, (0, 0, -25)), rot(1.5, (0, 0, -35)), rot(3, (0, 0, -25))]},
                        "右ひじ": {"rotation": [rot(0, (0, 0, 25)), rot(1.5, (0, 0, 35)), rot(3, (0, 0, 25))]},
                        "左足": {"rotation": [rot(0, (-14, 0, 12)), rot(0.7, (10, 0, 22)), rot(1.4, (-16, 0, 8)), rot(2.1, (8, 0, 19)), rot(3, (-14, 0, 12))]},
                        "右足": {"rotation": [rot(0, (12, 0, -12)), rot(0.7, (-16, 0, -19)), rot(1.4, (10, 0, -8)), rot(2.1, (-14, 0, -22)), rot(3, (12, 0, -12))]},
                        "左ひざ": {"rotation": [rot(0, (32, 0, 0)), rot(0.7, (10, 0, 0)), rot(1.4, (28, 0, 0)), rot(2.1, (16, 0, 0)), rot(3, (32, 0, 0))]},
                        "右ひざ": {"rotation": [rot(0, (12, 0, 0)), rot(0.7, (30, 0, 0)), rot(1.4, (10, 0, 0)), rot(2.1, (26, 0, 0)), rot(3, (12, 0, 0))]},
                        "左足首": {"rotation": [rot(0, (-12, 0, 0)), rot(1.5, (-20, 0, 0)), rot(3, (-12, 0, 0))]},
                        "右足首": {"rotation": [rot(0, (-12, 0, 0)), rot(1.5, (-20, 0, 0)), rot(3, (-12, 0, 0))]},
                    },
                    hair_sway(5.0, 1.0),
                ),
                morphs={
                    "びっくり": [weight(0, 0.5), weight(1.5, 0.35), weight(3, 0.5)],
                    "まばたき": [weight(0, 0), weight(1.0, 0), weight(1.1, 0.7), weight(1.3, 0), weight(3, 0)],
                },
                notes="被动动作。实际播放时由 DragController 叠加鼠标速度产生的附加摆动。",
            ),
            "passive",
        )
    )

    # ---------------------------------------------------------------- drag release
    actions.append(
        (
            build(
                action_id="drag_land",
                name="落地回稳",
                category="passive",
                duration=1.1,
                loop=False,
                priority=96,
                fade_in=0.1,
                ai_visible=False,
                tags=("passive", "drag", "land"),
                description=(
                    "松手落地后的被动缓冲：膝盖微屈，双臂向外找平衡，随后回到站立。"
                    "不供 AI 自由选择，由拖动交互层在释放时播放。"
                ),
                tracks=merge(
                    {
                        "上半身": {"rotation": [rot(0, (7, 0, 0)), rot(0.25, (10, 0, 0)), rot(0.7, (2, 0, 0)), rot(1.1, (0, 0, 0))]},
                        "首": {"rotation": [rot(0, (5, 0, 0)), rot(0.25, (8, 0, 0)), rot(1.1, (0, 0, 0))]},
                        "頭": {"rotation": [rot(0, (10, 0, 2)), rot(0.25, (13, 0, 2)), rot(0.7, (4, 0, 2)), rot(1.1, (1, 0, 2))]},
                        "左腕": {"rotation": [rot(0, (0, -24, 6)), rot(0.25, (0, -20, 18)), rot(0.7, (0, -45, -25)), rot(1.1, (0, -50, -40))]},
                        "右腕": {"rotation": [rot(0, (0, 24, -6)), rot(0.25, (0, 20, -18)), rot(0.7, (0, 45, 25)), rot(1.1, (0, 50, 40))]},
                        "左ひざ": {"rotation": [rot(0, (16, 0, 0)), rot(0.3, (22, 0, 0)), rot(0.8, (4, 0, 0)), rot(1.1, (0, 0, 0))]},
                        "右ひざ": {"rotation": [rot(0, (16, 0, 0)), rot(0.3, (22, 0, 0)), rot(0.8, (4, 0, 0)), rot(1.1, (0, 0, 0))]},
                        "左足": {"rotation": [rot(0, (-8, 0, 0)), rot(0.3, (-12, 0, 0)), rot(1.1, (0, 0, 0))]},
                        "右足": {"rotation": [rot(0, (-8, 0, 0)), rot(0.3, (-12, 0, 0)), rot(1.1, (0, 0, 0))]},
                    },
                    hair_sway(3.0, 0.55),
                ),
                morphs={
                    "びっくり": [weight(0, 0.55), weight(0.35, 0.3), weight(1.1, 0)],
                },
                notes="被动落地。膝盖弯曲但根骨骼不下降，避免鞋底穿入桌面阴影。",
            ),
            "passive",
        )
    )

    OUT.mkdir(parents=True, exist_ok=True)
    for action, subdir in actions:
        write(action, subdir)
    print(f"total AI-visible actions: {sum(1 for action, _ in actions if action['ai_visible'])}")
    print(f"total passive actions: {sum(1 for action, _ in actions if not action['ai_visible'])}")


if __name__ == "__main__":
    main()
