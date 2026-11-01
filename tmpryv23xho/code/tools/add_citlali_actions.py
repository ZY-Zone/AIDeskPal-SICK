"""Add the second Citlali action wave, built on the same authoring helpers.

Run from the repository root:

    .venv/Scripts/python tools/add_citlali_actions.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import author_actions as aa  # noqa: E402

OUT = aa.OUT


def hand_track(left: bool) -> dict:
    side = "左" if left else "右"
    sign = 1.0 if left else -1.0
    return {
        f"{side}腕": {
            "rotation": [
                aa.rot(0, (0, -50 * sign, -40 * sign)),
                aa.rot(0.55, (0, -12 * sign, 68 * sign), "ease_out"),
                aa.rot(1.1, (0, -9 * sign, 73 * sign)),
                aa.rot(2.6, (0, -11 * sign, 70 * sign)),
                aa.rot(3.8, (0, -46 * sign, -32 * sign), "ease_in"),
                aa.rot(4.4, (0, -50 * sign, -40 * sign)),
            ]
        },
        f"{side}ひじ": {
            "rotation": [
                aa.rot(0, (0, 0, 0)),
                aa.rot(0.55, (0, 0, 28 * sign), "ease_out"),
                aa.rot(2.6, (0, 0, 24 * sign)),
                aa.rot(4.4, (0, 0, 0)),
            ]
        },
        f"{side}手首": {
            "rotation": [
                aa.rot(0, (0, 0, 0)),
                aa.rot(0.9, (0, 18 * sign, 20 * sign)),
                aa.rot(1.25, (0, -18 * sign, -8 * sign)),
                aa.rot(1.6, (0, 18 * sign, 20 * sign)),
                aa.rot(1.95, (0, -18 * sign, -8 * sign)),
                aa.rot(2.3, (0, 8 * sign, 12 * sign)),
                aa.rot(3.8, (0, 0, 0)),
            ]
        },
    }


def build_new_actions() -> list[dict]:
    actions: list[dict] = []
    actions.append(
        aa.build(
            action_id="wave_both",
            name="双手挥手",
            description=(
                "双手一起抬到肩膀高度，掌心朝向用户轻轻摆动，眼睛弯起来。"
                "适合用户刚回来、完成任务或需要热烈一点的回应时。"
            ),
            category="greeting",
            duration=4.4,
            loop=False,
            priority=82,
            tags=("greeting", "wave", "happy"),
            tracks=aa.merge(
                {
                    "上半身2": {
                        "rotation": [
                            aa.rot(0, (1, 0, 0)),
                            aa.rot(0.5, (0, 1.5, 0)),
                            aa.rot(3.8, (1, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.7, (0, -2, 4)), aa.rot(3.8, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(0.7, (-2, -4, 7)),
                            aa.rot(2.8, (-1, -2, 5)),
                            aa.rot(3.8, (1, 0, 2)),
                        ]
                    },
                    "左肩": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.55, (0, 0, 8)), aa.rot(3.8, (0, 0, 0))]},
                    "右肩": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.55, (0, 0, -8)), aa.rot(3.8, (0, 0, 0))]},
                },
                hand_track(True),
                hand_track(False),
                aa.hair_sway(2.0, 1.7),
            ),
            morphs={
                "笑い": [aa.weight(0, 0.15), aa.weight(0.6, 0.75), aa.weight(3.8, 0.65), aa.weight(4.4, 0.15)],
                "まばたき": [aa.weight(0, 0), aa.weight(2.1, 0), aa.weight(2.2, 1), aa.weight(2.4, 0), aa.weight(4.4, 0)],
            },
            notes="双手同时举起，手腕交错摆动；比单臂挥手更热情。",
        )
    )

    actions.append(
        aa.build(
            action_id="curious_tilt",
            name="歪头好奇",
            description=(
                "把头轻轻歪向一侧，眉毛微动，像在认真理解用户刚说的话。"
                "适合用户提出问题、展示新东西或气氛需要一点好奇时。"
            ),
            category="reaction",
            duration=3.6,
            loop=False,
            priority=62,
            tags=("curious", "head_tilt", "reaction"),
            tracks=aa.merge(
                {
                    "上半身2": {
                        "rotation": [
                            aa.rot(0, (1, 0, 0)),
                            aa.rot(1.0, (1, 0, 4)),
                            aa.rot(2.5, (1, 0, -3)),
                            aa.rot(3.6, (1, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (0, -4, 6)), aa.rot(2.4, (0, 7, -4)), aa.rot(3.6, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(0.8, (0, -10, 12)),
                            aa.rot(2.2, (1, 9, -7)),
                            aa.rot(3.6, (1, 0, 2)),
                        ]
                    },
                    "左目": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.0, (0, -5, 0)), aa.rot(2.6, (0, 6, 0)), aa.rot(3.6, (0, 0, 0))]},
                    "右目": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.0, (0, -5, 0)), aa.rot(2.6, (0, 6, 0)), aa.rot(3.6, (0, 0, 0))]},
                },
                aa.hair_sway(1.2, 1.2),
            ),
            morphs={
                "まばたき": [aa.weight(0, 0), aa.weight(1.7, 0), aa.weight(1.8, 1), aa.weight(2.0, 0), aa.weight(3.6, 0)],
                "笑い": [aa.weight(0, 0), aa.weight(2.2, 0.3), aa.weight(3.6, 0.1)],
            },
            notes="头部倾斜与眼睛转动错开，避免只剩机械转头。",
        )
    )

    actions.append(
        aa.build(
            action_id="relieved_sigh",
            name="松一口气",
            description=(
                "肩膀先微微抬起，然后整个上身松下来，头低一点再抬回去，像终于放下心事。"
                "适合用户完成一段工作、说出压力或长舒一口气时。"
            ),
            category="emotion",
            duration=4.6,
            loop=False,
            priority=55,
            tags=("relief", "sigh", "comfort"),
            tracks=aa.merge(
                {
                    "上半身": {
                        "rotation": [
                            aa.rot(0, (0, 0, 0)),
                            aa.rot(0.7, (1, 0, 0)),
                            aa.rot(1.5, (4, 0, 0)),
                            aa.rot(3.6, (1, 0, 0)),
                            aa.rot(4.6, (0, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.2, (5, 0, 0)), aa.rot(3.4, (1, 0, 0)), aa.rot(4.6, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(1.2, (9, 0, 2)),
                            aa.rot(2.7, (10, 0, 2)),
                            aa.rot(3.7, (2, 0, 2)),
                            aa.rot(4.6, (1, 0, 2)),
                        ]
                    },
                    "左肩": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (0, 0, 3)), aa.rot(3.6, (0, 0, 0))]},
                    "右肩": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (0, 0, -3)), aa.rot(3.6, (0, 0, 0))]},
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(1.2, (0, -54, -38)), aa.rot(4.6, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(1.2, (0, 54, 38)), aa.rot(4.6, (0, 50, 40))]},
                },
                aa.hair_sway(1.3, 2.0),
            ),
            morphs={
                "まばたき": [aa.weight(0, 0), aa.weight(2.9, 0), aa.weight(3.0, 1), aa.weight(3.2, 0), aa.weight(4.6, 0)],
                "なごみ": [aa.weight(0, 0.05), aa.weight(1.7, 0.5), aa.weight(3.8, 0.32), aa.weight(4.6, 0.05)],
            },
            notes="从紧张到放松，避免头低得太久显得沮丧。",
        )
    )

    actions.append(
        aa.build(
            action_id="sleepy_nod",
            name="困倦点头",
            description=(
                "眼皮慢慢垂下来，头一点一点地往下沉，然后突然惊醒，装作什么都没发生。"
                "适合深夜、用户长时间专注或桌宠自己进入困倦状态时。"
            ),
            category="idle",
            duration=5.2,
            loop=False,
            priority=38,
            tags=("sleepy", "nod", "night"),
            tracks=aa.merge(
                {
                    "上半身": {
                        "rotation": [
                            aa.rot(0, (0, 0, 0)),
                            aa.rot(1.4, (2, 0, 0)),
                            aa.rot(3.0, (3, 0, 0)),
                            aa.rot(3.6, (0, 0, 0)),
                            aa.rot(5.2, (0, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.4, (6, 0, 0)), aa.rot(3.0, (8, 0, 0)), aa.rot(3.6, (-3, 0, 0)), aa.rot(5.2, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(1.4, (12, 0, 2)),
                            aa.rot(3.0, (15, 0, 2)),
                            aa.rot(3.6, (-4, 0, 2)),
                            aa.rot(4.4, (2, 0, 2)),
                            aa.rot(5.2, (1, 0, 2)),
                        ]
                    },
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(2.5, (0, -54, -38)), aa.rot(5.2, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(2.5, (0, 54, 38)), aa.rot(5.2, (0, 50, 40))]},
                },
                aa.hair_sway(1.4, 2.2),
            ),
            morphs={
                "じと目": [aa.weight(0, 0), aa.weight(1.2, 0.35), aa.weight(3.0, 0.5), aa.weight(3.7, 0.1), aa.weight(5.2, 0)],
                "まばたき": [aa.weight(0, 0), aa.weight(1.8, 0), aa.weight(1.95, 0.7), aa.weight(2.3, 0), aa.weight(3.5, 0), aa.weight(3.65, 1), aa.weight(3.85, 0), aa.weight(5.2, 0)],
            },
            notes="点头幅度较大但只用上半身和头，脚底保持稳定。",
        )
    )

    actions.append(
        aa.build(
            action_id="proud_humph",
            name="小小得意",
            description=(
                "抬起下巴，偏头轻轻哼一声，眼神带着一点得意但没有恶意。"
                "适合用户夸奖、占卜结果应验或用户说自己完成了任务时。"
            ),
            category="emotion",
            duration=3.8,
            loop=False,
            priority=66,
            tags=("proud", "tsundere", "happy"),
            tracks=aa.merge(
                {
                    "上半身2": {
                        "rotation": [
                            aa.rot(0, (1, 0, 0)),
                            aa.rot(0.8, (-3, 0, 0), "ease_out"),
                            aa.rot(3.0, (-2, 0, 0)),
                            aa.rot(3.8, (1, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (-3, 5, -2)), aa.rot(2.8, (-2, 4, -1)), aa.rot(3.8, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(0.8, (-7, 14, -6)),
                            aa.rot(2.7, (-5, 10, -4)),
                            aa.rot(3.8, (1, 0, 2)),
                        ]
                    },
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(1.0, (0, -54, -36)), aa.rot(3.8, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(1.0, (0, 54, 36)), aa.rot(3.8, (0, 50, 40))]},
                },
                aa.hair_sway(1.6, 1.8),
            ),
            morphs={
                "にやり": [aa.weight(0, 0), aa.weight(0.8, 0.65), aa.weight(2.8, 0.5), aa.weight(3.8, 0)],
                "まばたき": [aa.weight(0, 0), aa.weight(1.8, 0), aa.weight(1.9, 1), aa.weight(2.1, 0), aa.weight(3.8, 0)],
            },
            notes="得意但保持善意，身体只微微后仰。",
        )
    )

    actions.append(
        aa.build(
            action_id="starlight_guard",
            name="星幕守护",
            description=(
                "双手向前抬起，像在用户面前撑起一层很薄的星光，头微微抬起。"
                "适合用户紧张、害怕或说需要一点保护感时。"
            ),
            category="affection",
            duration=5.0,
            loop=False,
            priority=72,
            tags=("comfort", "guard", "warm"),
            tracks=aa.merge(
                {
                    "上半身": {
                        "rotation": [
                            aa.rot(0, (0, 0, 0)),
                            aa.rot(0.9, (3, 0, 0)),
                            aa.rot(4.0, (2, 0, 0)),
                            aa.rot(5.0, (0, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.0, (-2, 0, 0)), aa.rot(4.0, (-1, 0, 0)), aa.rot(5.0, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(1.0, (-4, 0, 2)),
                            aa.rot(3.8, (-2, 0, 2)),
                            aa.rot(5.0, (1, 0, 2)),
                        ]
                    },
                    "左腕": {
                        "rotation": [
                            aa.rot(0, (0, -50, -40)),
                            aa.rot(1.0, (0, -34, 18), "ease_out"),
                            aa.rot(3.8, (0, -32, 22)),
                            aa.rot(5.0, (0, -50, -40)),
                        ]
                    },
                    "右腕": {
                        "rotation": [
                            aa.rot(0, (0, 50, 40)),
                            aa.rot(1.0, (0, 34, -18), "ease_out"),
                            aa.rot(3.8, (0, 32, -22)),
                            aa.rot(5.0, (0, 50, 40)),
                        ]
                    },
                    "左ひじ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.0, (0, 0, 48)), aa.rot(3.8, (0, 0, 44)), aa.rot(5.0, (0, 0, 0))]},
                    "右ひじ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.0, (0, 0, -48)), aa.rot(3.8, (0, 0, -44)), aa.rot(5.0, (0, 0, 0))]},
                },
                aa.hair_sway(1.8, 2.0),
            ),
            morphs={
                "なごみ": [aa.weight(0, 0.05), aa.weight(1.2, 0.4), aa.weight(4.0, 0.35), aa.weight(5.0, 0.05)],
                "まばたき": [aa.weight(0, 0), aa.weight(2.4, 0), aa.weight(2.5, 1), aa.weight(2.7, 0), aa.weight(5.0, 0)],
            },
            notes="双手在胸前形成保护姿态，不越过身体中线过多。",
        )
    )

    actions.append(
        aa.build(
            action_id="happy_bounce",
            name="开心弹跳",
            description=(
                "双手向上打开，原地轻轻弹跳一下，落地时膝盖微屈，像在庆祝。"
                "适合用户完成任务、测试通过或分享好消息时。"
            ),
            category="emotion",
            duration=3.2,
            loop=False,
            priority=76,
            tags=("happy", "bounce", "celebrate"),
            tracks=aa.merge(
                {
                    "全ての親": {
                        "rotation": [aa.rot(0, (0, 0, 0)), aa.rot(3.2, (0, 0, 0))],
                        "translation": [
                            aa.trans(0, (0, 0, 0)),
                            aa.trans(0.28, (0, 0.5, 0), "ease_out"),
                            aa.trans(0.58, (0, 0, 0), "ease_in"),
                            aa.trans(1.05, (0, 0.32, 0), "ease_out"),
                            aa.trans(1.35, (0, 0, 0), "ease_in"),
                            aa.trans(3.2, (0, 0, 0)),
                        ],
                    },
                    "上半身": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.28, (-3, 0, 0)), aa.rot(0.7, (2, 0, 0)), aa.rot(1.6, (0, 0, 0)), aa.rot(3.2, (0, 0, 0))]},
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.3, (-4, 0, 3)), aa.rot(1.4, (0, 0, 0)), aa.rot(3.2, (0, 0, 0))]},
                    "頭": {"rotation": [aa.rot(0, (1, 0, 2)), aa.rot(0.3, (-7, 0, 4)), aa.rot(1.4, (1, 0, 2)), aa.rot(3.2, (1, 0, 2))]},
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(0.3, (0, -14, 70), "ease_out"), aa.rot(1.8, (0, -16, 66)), aa.rot(2.8, (0, -50, -40)), aa.rot(3.2, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(0.3, (0, 14, -70), "ease_out"), aa.rot(1.8, (0, 16, -66)), aa.rot(2.8, (0, 50, 40)), aa.rot(3.2, (0, 50, 40))]},
                    "左ひざ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.62, (7, 0, 0)), aa.rot(0.95, (0, 0, 0)), aa.rot(1.35, (5, 0, 0)), aa.rot(1.7, (0, 0, 0)), aa.rot(3.2, (0, 0, 0))]},
                    "右ひざ": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.62, (7, 0, 0)), aa.rot(0.95, (0, 0, 0)), aa.rot(1.35, (5, 0, 0)), aa.rot(1.7, (0, 0, 0)), aa.rot(3.2, (0, 0, 0))]},
                },
                aa.hair_sway(3.2, 0.8),
            ),
            morphs={
                "笑い": [aa.weight(0, 0.2), aa.weight(0.3, 0.9), aa.weight(2.8, 0.8), aa.weight(3.2, 0.2)],
                "まばたき": [aa.weight(0, 0), aa.weight(1.6, 0), aa.weight(1.7, 1), aa.weight(1.9, 0), aa.weight(3.2, 0)],
            },
            notes="轻量弹跳，落地有膝盖缓冲；不做夸张物理。",
        )
    )

    actions.append(
        aa.build(
            action_id="humming_sway",
            name="轻声哼唱",
            description=(
                "身体随着看不见的节拍左右轻摆，偶尔眨眼、嘴角上扬，像在小声哼歌。"
                "适合安静陪伴、用户写代码或长时间阅读时作为低打扰待机。"
            ),
            category="idle",
            duration=8.0,
            loop=True,
            priority=18,
            tags=("idle", "humming", "calm", "loop"),
            tracks=aa.merge(
                {
                    "上半身": {
                        "rotation": [
                            aa.rot(0, (0, 0, 0)),
                            aa.rot(2.0, (0, 0, 2.2)),
                            aa.rot(4.0, (0, 0, 0)),
                            aa.rot(6.0, (0, 0, -2.2)),
                            aa.rot(8.0, (0, 0, 0)),
                        ]
                    },
                    "首": {
                        "rotation": [
                            aa.rot(0, (0, 0, 0)),
                            aa.rot(2.0, (0, -1.5, 1.5)),
                            aa.rot(4.0, (0, 0, 0)),
                            aa.rot(6.0, (0, 1.5, -1.5)),
                            aa.rot(8.0, (0, 0, 0)),
                        ]
                    },
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(2.0, (1.5, -3, 4)),
                            aa.rot(4.0, (1, 0, 2)),
                            aa.rot(6.0, (1.5, 3, 0)),
                            aa.rot(8.0, (1, 0, 2)),
                        ]
                    },
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(2.0, (0, -52, -38)), aa.rot(4.0, (0, -50, -40)), aa.rot(6.0, (0, -48, -42)), aa.rot(8.0, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(2.0, (0, 48, 42)), aa.rot(4.0, (0, 50, 40)), aa.rot(6.0, (0, 52, 38)), aa.rot(8.0, (0, 50, 40))]},
                },
                aa.hair_sway(1.2, 2.0),
            ),
            morphs={
                "笑い": [aa.weight(0, 0.3), aa.weight(2.5, 0.45), aa.weight(5.5, 0.35), aa.weight(8.0, 0.3)],
                "まばたき": [aa.weight(0, 0), aa.weight(3.2, 0), aa.weight(3.3, 1), aa.weight(3.5, 0), aa.weight(6.5, 0), aa.weight(6.6, 1), aa.weight(6.8, 0), aa.weight(8.0, 0)],
            },
            notes="循环待机；首尾一致，避免摇摆跳帧。",
        )
    )

    actions.append(
        aa.build(
            action_id="shy_glance",
            name="害羞侧目",
            description=(
                "把视线移开，侧过脸又忍不住偷看回来，手指在身侧轻轻收紧。"
                "适合被夸奖、被摸头或用户说了让她不好意思的话时。"
            ),
            category="reaction",
            duration=3.6,
            loop=False,
            priority=64,
            tags=("shy", "glance", "soft"),
            tracks=aa.merge(
                {
                    "上半身2": {
                        "rotation": [
                            aa.rot(0, (1, 0, 0)),
                            aa.rot(0.8, (1, -3, 2)),
                            aa.rot(2.5, (1, 2, -1)),
                            aa.rot(3.6, (1, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (2, -9, 3)), aa.rot(2.4, (0, 4, -2)), aa.rot(3.6, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(0.8, (5, -14, 8)),
                            aa.rot(2.3, (2, 8, -2)),
                            aa.rot(3.6, (1, 0, 2)),
                        ]
                    },
                    "左目": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (0, -10, 0)), aa.rot(2.3, (0, 5, 0)), aa.rot(3.6, (0, 0, 0))]},
                    "右目": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(0.8, (0, -10, 0)), aa.rot(2.3, (0, 5, 0)), aa.rot(3.6, (0, 0, 0))]},
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(1.0, (0, -58, -30)), aa.rot(3.6, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(1.0, (0, 58, 30)), aa.rot(3.6, (0, 50, 40))]},
                },
                aa.hair_sway(1.1, 1.4),
            ),
            morphs={
                "なごみ": [aa.weight(0, 0.05), aa.weight(1.0, 0.55), aa.weight(2.8, 0.45), aa.weight(3.6, 0.05)],
                "まばたき": [aa.weight(0, 0), aa.weight(1.6, 0), aa.weight(1.7, 1), aa.weight(1.9, 0), aa.weight(3.6, 0)],
            },
            notes="侧目和头部回转分两段，保留回看的小动作。",
        )
    )

    actions.append(
        aa.build(
            action_id="soft_lean",
            name="轻轻靠近",
            description=(
                "上身向前倾一点，像在认真听用户说话，眼神温和地停留在用户身上。"
                "适合用户低声倾诉、需要陪伴或分享一件小事时。"
            ),
            category="affection",
            duration=4.2,
            loop=False,
            priority=58,
            tags=("lean", "listen", "warm"),
            tracks=aa.merge(
                {
                    "上半身": {
                        "rotation": [
                            aa.rot(0, (0, 0, 0)),
                            aa.rot(1.0, (5, 0, 0)),
                            aa.rot(3.2, (4, 0, 0)),
                            aa.rot(4.2, (0, 0, 0)),
                        ]
                    },
                    "首": {"rotation": [aa.rot(0, (0, 0, 0)), aa.rot(1.0, (3, 2, 2)), aa.rot(3.2, (2, 1, 1)), aa.rot(4.2, (0, 0, 0))]},
                    "頭": {
                        "rotation": [
                            aa.rot(0, (1, 0, 2)),
                            aa.rot(1.0, (4, 5, 4)),
                            aa.rot(3.2, (3, 3, 3)),
                            aa.rot(4.2, (1, 0, 2)),
                        ]
                    },
                    "左腕": {"rotation": [aa.rot(0, (0, -50, -40)), aa.rot(1.0, (0, -56, -34)), aa.rot(4.2, (0, -50, -40))]},
                    "右腕": {"rotation": [aa.rot(0, (0, 50, 40)), aa.rot(1.0, (0, 56, 34)), aa.rot(4.2, (0, 50, 40))]},
                },
                aa.hair_sway(1.0, 1.9),
            ),
            morphs={
                "笑い": [aa.weight(0, 0.15), aa.weight(1.2, 0.42), aa.weight(3.2, 0.35), aa.weight(4.2, 0.15)],
                "まばたき": [aa.weight(0, 0), aa.weight(2.3, 0), aa.weight(2.4, 1), aa.weight(2.6, 0), aa.weight(4.2, 0)],
            },
            notes="前倾幅度很小，保持脚底和裙摆稳定。",
        )
    )

    return actions


def main() -> None:
    actions = build_new_actions()
    for action in actions:
        aa.write(action)
    pack_path = OUT / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    existing = list(pack.get("actions", []))
    for action in actions:
        if action["id"] not in existing:
            existing.append(action["id"])
    pack["actions"] = existing
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"added {len(actions)} actions; pack now lists {len(existing)}")


if __name__ == "__main__":
    main()
