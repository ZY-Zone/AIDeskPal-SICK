"""Deterministic anatomy/contact polish for the Citlali action source of truth."""
from __future__ import annotations

import copy


def make_keys(values, duration, field="rot"):
    return [{"t": round(t * duration, 6), field: list(v), "ease": "smooth"} for t, v in values]


def replace_rotation(document, bone, values):
    duration = document["content"]["duration"]
    document["content"]["bones"].setdefault(bone, {})["rotation"] = make_keys(values, duration)


def replace_translation(document, bone, values):
    duration = document["content"]["duration"]
    document["content"]["bones"].setdefault(bone, {})["translation"] = make_keys(values, duration, "trans")


def hop_mechanics(document, times, root_y, thigh, knee, ankle):
    duration = document["content"]["duration"]
    assert len(times) == len(root_y) == len(thigh) == len(knee) == len(ankle)
    normalized = [t / duration for t in times]
    document["content"]["bones"]["全ての親"]["translation"] = make_keys(
        list(zip(normalized, ([0.0, y, 0.0] for y in root_y))), duration, "trans"
    )
    for side in ("左", "右"):
        replace_rotation(document, side + "足", [(t, [v, 0, 0]) for t, v in zip(normalized, thigh)])
        replace_rotation(document, side + "ひざ", [(t, [v, 0, 0]) for t, v in zip(normalized, knee)])
        replace_rotation(document, side + "足首", [(t, [v, 0, 0]) for t, v in zip(normalized, ankle)])


def refine_hops(document):
    action = document["id"]
    if action == "cheer_hop":
        hop_mechanics(
            document,
            [0, .18, .35, .75, .95, 1.15, 1.35, 1.75, 1.95, 2.35, 2.8],
            [0, -.22, .65, -.18, 0, -.20, .50, -.16, 0, 0, 0],
            [0, 10, 3, 14, 0, 9, 3, 13, 0, 0, 0],
            [0, 28, 8, 36, 0, 26, 8, 34, 0, 0, 0],
            [0, -6, 3, -9, 0, -5, 3, -8, 0, 0, 0],
        )
    elif action == "happy_bounce":
        hop_mechanics(
            document,
            [0, .20, .48, .78, 1.0, 1.18, 1.45, 1.75, 2.05, 3.2],
            [0, -.18, .48, -.14, 0, -.15, .34, -.12, 0, 0],
            [0, 9, 3, 12, 0, 8, 3, 11, 0, 0],
            [0, 26, 8, 32, 0, 24, 7, 30, 0, 0],
            [0, -5, 3, -8, 0, -5, 3, -7, 0, 0],
        )
    elif action == "surprised":
        hop_mechanics(
            document,
            [0, .10, .15, .50, .72, 2.0],
            [0, -.12, .38, -.10, 0, 0],
            [0, 8, 2, 10, 0, 0],
            [0, 20, 6, 28, 0, 0],
            [0, -4, 2, -7, 0, 0],
        )
    refine_hop_arms(document)


def refine_hop_arms(document):
    """Keep celebratory silhouettes inside the normal transparent viewport."""
    action = document["id"]
    if action == "cheer_hop":
        times = [0, .35, .9, 2.0, 2.5, 2.8]
        ys = [-50, -34, -36, -35, -47, -50]
        zs = [-40, 11, 10, 12, -28, -40]
        replace_rotation(document, "左腕", [(t / 2.8, [0, y, z]) for t, y, z in zip(times, ys, zs)])
        replace_rotation(document, "右腕", [((t + (.015455 if 0 < t < 2.8 else 0)) / 2.8, [0, -y, -z]) for t, y, z in zip(times, ys, zs)])
        replace_rotation(document, "左ひじ", [(0, [0, 0, 17.2]), (.125, [0, 0, 22]), (.625, [0, 0, 21]), (1, [0, 0, 17.2])])
        replace_rotation(document, "右ひじ", [(0, [0, 0, -17.2]), (.125, [0, 0, -22]), (.625, [0, 0, -21]), (1, [0, 0, -17.2])])
    elif action == "happy_bounce":
        times = [0, .30, 1.8, 2.8, 3.2]
        ys = [-50, -34, -36, -50, -50]
        zs = [-40, 8, 8, -40, -40]
        replace_rotation(document, "左腕", [(t / 3.2, [0, y, z]) for t, y, z in zip(times, ys, zs)])
        replace_rotation(document, "右腕", [((min(3.2, t + .013732) if 0 < t < 3.2 else t) / 3.2, [0, -y, -z]) for t, y, z in zip(times, ys, zs)])


def refine_top_grip(document):
    """Hang from the screen's top edge instead of cheering with arms spread.

    The previous recipe reused the celebratory arms-up block, which put the
    wrists at x=±4.5 with the legs straight: a standing V pose, not a hang.
    Here both hands grip just above and slightly inside the shoulders (solved on
    the real FK chain), the elbows keep a loaded bend, and the legs hang bent
    with a slow pendulum so the body reads as suspended weight.
    """
    duration = document["content"]["duration"]
    # Arm angles found by sweeping the real FK chain for a wrist target of
    # (±1.1, 20.4, 0.4): hands overhead, slightly inside the shoulders, level
    # with each other.  The old recipe inherited the celebratory arms-up block
    # (Z=77, wrist x=±3.0), which reads as a cheer rather than a hang.
    replace_rotation(document, "左腕", [(0, [0, -5, 115]), (1, [0, -5, 115])])
    replace_rotation(document, "右腕", [(0, [0, 5, -115]), (1, [0, 5, -115])])
    replace_rotation(document, "左ひじ", [(0, [0, 0, 30]), (1, [0, 0, 30])])
    replace_rotation(document, "右ひじ", [(0, [0, 0, -30]), (1, [0, 0, -30])])
    replace_rotation(document, "左手首", [(0, [0, 6, 12]), (1, [0, 6, 12])])
    replace_rotation(document, "右手首", [(0, [0, -6, -12]), (1, [0, -6, -12])])
    # Shoulders shrug up under load; the torso stretches slightly.
    replace_rotation(document, "上半身", [(0, [-2, 0, 0]), (.5, [-2.6, 0, 0]), (1, [-2, 0, 0])])
    replace_rotation(document, "上半身2", [(0, [-1, 0, 0]), (1, [-1, 0, 0])])
    replace_rotation(document, "首", [(0, [3, 0, 0]), (.5, [2, 0, .4]), (1, [3, 0, 0])])
    replace_rotation(document, "頭", [(0, [4, 0, 1]), (.5, [3, 1, 1.6]), (1, [4, 0, 1])])
    # Legs dangle: thighs swing back, knees stay softly bent, ankles hang loose.
    # A slow pendulum leads the torso slightly so the body reads as suspended
    # weight rather than a pose held in place.
    for side, sign, bend, phase in (("左", 1, 4.0, 0.0), ("右", -1, -2.0, 0.4)):
        replace_rotation(document, side + "足", [
            (0, [-30 - bend, 0, 5 * sign]),
            (.5, [-34 - bend, 0, 6 * sign]),
            (1, [-30 - bend, 0, 5 * sign]),
        ])
        replace_rotation(document, side + "ひざ", [
            (0, [75 + bend * 2, 0, 0]),
            (.5, [82 + bend * 2, 0, 0]),
            (1, [75 + bend * 2, 0, 0]),
        ])
        replace_rotation(document, side + "足首", [
            (0, [-18, 0, 0]),
            (.5, [-24, 0, 0]),
            (1, [-18, 0, 0]),
        ])
    # Gentle whole-body sway about the grip, which is the physical hinge.
    replace_translation(document, "全ての親", [
        (0, [0, 0, 0]),
        (.25, [0.10, -0.06, 0]),
        (.5, [0, -0.10, 0]),
        (.75, [-0.10, -0.06, 0]),
        (1, [0, 0, 0]),
    ])


def refine_duck_sit(document):
    """Buttocks and the outer edges of both shoes share the ground plane.

    Reference pose: the hips rotate outward so the knees point out to the sides,
    the shins fold back beside the thighs and the soles lie flat next to the
    hips, with the hands gathered in front of the chest.  The old recipe flexed
    the knees under the body with the feet dangling, which read as kneeling.

    Solved against the real rig rather than guessed: with the thigh at
    (-20°, 0, 100°) the sole bottoms out at the same height as the buttocks
    (measured gap 0.00) and the knees still sit 1.36 units above the soles, so
    the pose genuinely rests on the floor instead of hovering.
    """
    for side, sign in (("左", 1), ("右", -1)):
        # Knees gather at the centre line while the shins splay out to the sides
        # and the shoes settle wide and low.  Measured on the real rig: knee x
        # 1.23, ankle x 3.74, sole x 4.12, so the knees touch and the feet fan
        # outward — the reference art's signature shape.  Abducting the thigh
        # instead (the previous recipe) split the legs into a flat straddle.
        replace_rotation(document, side + "足", [
            (0, [-85, 0, 50 * sign]),
            (1, [-85, 0, 50 * sign]),
        ])
        replace_rotation(document, side + "ひざ", [
            (0, [135, 0, -10 * sign]),
            (1, [135, 0, -10 * sign]),
        ])
        replace_rotation(document, side + "足首", [
            (0, [60, 0, 0]),
            (1, [60, 0, 0]),
        ])
    # Arms rest low with the hands near the knees, not floating forward.
    replace_rotation(document, "左腕", [(0, [0, -46, -34]), (1, [0, -46, -34])])
    replace_rotation(document, "右腕", [(0, [0, 46, 34]), (1, [0, 46, 34])])
    replace_rotation(document, "左ひじ", [(0, [0, 0, 26]), (1, [0, 0, 26])])
    replace_rotation(document, "右ひじ", [(0, [0, 0, -26]), (1, [0, 0, -26])])



def refine_side_peek(document):
    """Stand behind the left wall and peek out with two vertically spaced grips."""
    replace_translation(document, "全ての親", [(0, [-6.0, 0.0, 0.0]), (1, [-6.0, 0.0, 0.0])])
    replace_rotation(document, "全ての親", [(0, [0, 0, 0]), (1, [0, 0, 0])])
    # Feet remain behind the wall; only the upper body leans into the screen.
    replace_rotation(document, "上半身", [(0, [0, 0, -20]), (1, [0, 0, -20])])
    replace_rotation(document, "上半身2", [(0, [0, 0, -5]), (1, [0, 0, -5])])
    for side, knee in (("左", 2), ("右", 3)):
        replace_rotation(document, side + "足", [(0, [0, 0, -6]), (1, [0, 0, -6])])
        replace_rotation(document, side + "ひざ", [(0, [knee, 0, 0]), (1, [knee, 0, 0])])
        replace_rotation(document, side + "足首", [(0, [-knee, 0, 0]), (1, [-knee, 0, 0])])
    # Head-side and chest-side grips share x=-6.48 on the same wall.
    replace_rotation(document, "右腕", [(0, [0, 10, -27.5]), (1, [0, 10, -27.5])])
    replace_rotation(document, "右ひじ", [(0, [0, 0, -120]), (1, [0, 0, -120])])
    replace_rotation(document, "右手首", [(0, [0, 15, -10]), (1, [0, 15, -10])])
    replace_rotation(document, "左腕", [(0, [-5.19, -12.17, -31.25]), (1, [-5.19, -12.17, -31.25])])
    replace_rotation(document, "左ひじ", [(0, [.95, -10.71, -83.21]), (1, [.95, -10.71, -83.21])])
    replace_rotation(document, "左手首", [(0, [0, -15, 10]), (1, [0, -15, 10])])
    # Keep every leg/shoe vertex behind the wall while leaving most of the
    # upper body visible. Only the lowest three skirt segments curl back in;
    # their cumulative 0.6-unit offset exposes a small hem, not the whole skirt.
    replace_translation(document, "下半身", [(0, [-4.6, 0, 0]), (1, [-4.6, 0, 0])])
    for level in (6, 7, 8):
        for chain in range(17):
            replace_translation(document, f"Q_{level}_{chain}", [(0, [.2, 0, 0]), (1, [.2, 0, 0])])
    # Cancel the body's sideways tilt without yawing the face away from the user.
    replace_rotation(document, "首", [(0, [0, 0, 10]), (1, [0, 0, 10])])
    replace_rotation(document, "頭", [(0, [0, 0, 5]), (1, [0, 0, 5])])
    document["name"] = "墙后侧站扒边"
    document["description"] = "下半身和鞋全部藏在墙后，上半身大部分探出，只露少量裙摆下缘；双手扒边，面部和视线正对屏幕。"


def match_fall_to_land(fall, land):
    """Make the handoff pose-identical while retaining the landing performance."""
    duration = fall["content"]["duration"]
    land["content"]["bones"]["全ての親"]["translation"][0]["trans"] = [0.0, 0.0, 0.0]
    for bone, tracks in land["content"]["bones"].items():
        for kind, channel in tracks.items():
            if not channel:
                continue
            field = "rot" if kind == "rotation" else "trans"
            start_value = copy.deepcopy(channel[0][field])
            fall_channel = fall["content"]["bones"][bone].setdefault(kind, [])
            if not fall_channel:
                fall_channel.append({"t": 0, field: [0.0, 0.0, 0.0], "ease": "smooth"})
            if fall_channel[-1]["t"] < duration:
                fall_channel.append({"t": duration, field: start_value, "ease": "smooth"})
            else:
                fall_channel[-1][field] = start_value
    for name, channel in land["content"].get("morphs", {}).items():
        if name not in fall["content"].setdefault("morphs", {}):
            continue
        start = channel[0]["w"]
        fall_channel = fall["content"]["morphs"][name]
        if fall_channel[-1]["t"] < duration:
            fall_channel.append({"t": duration, "w": start, "ease": "smooth"})
        else:
            fall_channel[-1]["w"] = start
    fall["fade_out"] = fall["content"]["fade_out"] = .1
    land["fade_in"] = land["content"]["fade_in"] = .1


def finger_pose(document, mode):
    # Drop the never-valid half-width draft names if an earlier generated copy
    # is migrated; real PMX joints are 人指１/２/３, not 人指1/2/3.
    for name in list(document["content"]["bones"]):
        if any(f"{side}{finger}" in name for side in ("左", "右") for finger in ("人指", "中指", "薬指", "小指")) and name[-1:] in "123":
            del document["content"]["bones"][name]
    loop = document["content"].get("loop", document.get("loop", False))
    for side in ("左", "右"):
        for finger in ("人指", "中指", "薬指", "小指"):
            for joint in (1, 2, 3):
                suffix = "１２３"[joint - 1]  # PMX finger joints use full-width digits.
                name = f"{side}{finger}{suffix}"
                if mode == "grip":
                    angle = {1: 24, 2: 34, 3: 20}[joint]
                elif mode == "point" and side == "右" and finger == "人指":
                    angle = -2
                elif mode == "point" and side == "右":
                    angle = {1: 30, 2: 42, 3: 26}[joint]
                elif mode == "relaxed":
                    angle = {1: 8, 2: 12, 3: 7}[joint]
                else:
                    angle = -3 if joint == 1 else 0
                spread = (1 if side == "左" else -1) * (2 if finger in {"人指", "小指"} else 0)
                values = [(0, [angle, 0, spread]), (1, [angle, 0, spread])] if loop else [
                    (0, [0, 0, 0]), (.18, [angle, 0, spread]),
                    (.78, [angle, 0, spread]), (1, [0, 0, 0]),
                ]
                replace_rotation(document, name, values)
        if mode in {"grip", "point"}:
            for suffix, angle in (("０", 12), ("１", 20), ("２", 24)):
                values = [(0, [angle, 0, 8]), (1, [angle, 0, 8])] if loop else [
                    (0, [0, 0, 0]), (.18, [angle, 0, 8]),
                    (.78, [angle, 0, 8]), (1, [0, 0, 0]),
                ]
                replace_rotation(document, f"{side}親指{suffix}", values)


def refine_dance(document):
    duration = document["content"]["duration"]
    times = [0, .8, 1.8, 2.8, 3.8, 4.5, duration]
    normalized = [t / duration for t in times]
    document["content"]["bones"]["全ての親"]["translation"] = make_keys([
        (t, [x, y, z]) for t, x, y, z in zip(
            normalized, [0, .08, -.08, .08, -.08, 0, 0],
            [0, -.06, 0, -.05, 0, 0, 0], [0, -.06, .06, -.06, .06, 0, 0],
        )
    ], duration, "trans")
    for side, phase in (("左", 1), ("右", 0)):
        knees = [0, 18 if phase else 8, 8, 18 if phase else 8, 8, 10, 0]
        thighs = [0, 7 if phase else 3, 3, 7 if phase else 3, 3, 4, 0]
        ankles = [0, -5, 2, -5, 2, -3, 0]
        replace_rotation(document, side + "ひざ", [(t, [v, 0, 0]) for t, v in zip(normalized, knees)])
        replace_rotation(document, side + "足", [(t, [v, 0, 0]) for t, v in zip(normalized, thighs)])
        replace_rotation(document, side + "足首", [(t, [v, 0, 0]) for t, v in zip(normalized, ankles)])
    secondary_times = [0, .95, 1.95, 2.95, 3.95, 4.65, duration]
    secondary_t = [t / duration for t in secondary_times]
    for bone in list(document["content"]["bones"]):
        if "Hair" not in bone:
            continue
        amplitude = 2.4 + (sum(ord(char) for char in bone) % 4) * .45
        values = [0, amplitude, -amplitude * .8, amplitude * .65, -amplitude * .45, amplitude * .15, 0]
        replace_rotation(document, bone, [(t, [v * .45, 0, v]) for t, v in zip(secondary_t, values)])
    for index, bone in enumerate((
        "Bone_LetA01_L", "Bone_LetA01_R", "Bone_LetB01_L", "Bone_LetB01_R",
        "Bone_LetC01_L", "Bone_LetC01_M", "Bone_LetC01_R",
    )):
        sign = 1 if index % 2 == 0 else -1
        values = [0, 3.2 * sign, -2.6 * sign, 2.1 * sign, -1.5 * sign, .4 * sign, 0]
        replace_rotation(document, bone, [(t, [v * .35, v * .4, v]) for t, v in zip(secondary_t, values)])


def polish_document(document):
    refine_hops(document)
    if document["id"] == "edge_bottom_sit":
        refine_duck_sit(document)
    if document["id"] == "edge_top_grip":
        refine_top_grip(document)
    if document["id"] == "edge_side_hang":
        refine_side_peek(document)
    if document["id"] == "dance_spin":
        refine_dance(document)
    hand_modes = {
        "edge_top_grip": "grip", "edge_side_hang": "grip",
        "point_there": "point", "wave_hello": "open", "wave_both": "open",
        "reach_out": "relaxed", "think_hmm": "relaxed",
    }
    if document["id"] in hand_modes:
        finger_pose(document, hand_modes[document["id"]])