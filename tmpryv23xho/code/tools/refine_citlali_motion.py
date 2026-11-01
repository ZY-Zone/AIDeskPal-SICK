"""Last-stage Citlali motion direction and normalization.

Run AFTER author_actions.py/add_citlali_actions.py/add_edge_actions.py. This is
an authored-motion pass, not an IK/contact solver. Existing generators may be
rerun, but this pass must be last. Revision markers make reruns byte-stable;
regenerating an original document removes its marker and reapplies this pass.
No PMX asset or optional numerical library is required.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

# Tests load this script by file location; make its sibling polish pass importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from polish_citlali_motion import match_fall_to_land, polish_document

REVISION = "citlali-motion-direction-3"
AMPLITUDE_REVISIONS = {"citlali-motion-direction-1", REVISION}
ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aideskpal"
    / "character"
    / "茜特菈莉"
    / "actions"
)
DESCRIPTIONS = {
    "angry_pout": "微微偏头鼓起脸，双臂克制地收近身体，再放松。适合表达轻微不满。",
    "bow_greet": "上身缓缓前倾致意，手臂保持低位，停留后从容直起。适合礼貌问候。",
    "cheer_hop": "两次欢呼跳跃都有下蹲蓄力、空中小幅收膝和落地屈膝缓冲，双臂错开抬起，最后站稳。适合庆祝。",
    "curious_tilt": "头部轻轻侧倾，视线与肩部略有先后地跟随，再回到放松姿态。适合好奇观察。",
    "dance_spin": "小幅踏步配合原地转圈，膝盖与脚踝参与重心转换，头发和裙摆延迟跟随，最后减速停稳。适合简短表演。",
    "focus_company": "以低幅呼吸、轻微偏头和自然垂臂安静陪伴，循环首尾闭合。适合专注工作时陪伴。",
    "happy_bounce": "两次轻巧弹跳都有短暂蓄力、空中收膝与落地缓冲，双臂有先后地回应，最后恢复放松。适合表达开心。",
    "headpat_reaction": "轻轻缩肩并偏头，表情逐渐柔和，手臂贴近身体后放松。适合被摸头的反应。",
    "humming_sway": "以克制的上身左右摇摆配合略有时差的双臂和头部，形成缓慢循环。适合轻声哼唱。",
    "idle_starlight": "自然垂臂，肘部保留轻微弯曲，以缓慢呼吸和细小头发摆动循环待机。",
    "idle_watch": "保持放松站姿，头与视线缓缓转向旁侧再回来，手臂不过度摆动。适合安静观察。",
    "laugh_soft": "轻轻低头笑，肩膀和胸口有细小起伏，手臂收近后恢复放松。适合温和的笑意。",
    "nod_yes": "头部清楚但不过猛地点动，躯干仅轻微跟随，再平稳回正。适合肯定回应。",
    "point_there": "一侧手臂以适中的幅度向旁前方示意，另一侧保持低位，停留后收回。适合指示方向。",
    "poke_reaction": "短暂缩肩偏头，手臂做小幅回应，再柔和回到站姿。适合被轻戳的惊讶反应。",
    "proud_humph": "微微抬头并侧转，双臂略收，短暂停留后恢复自然。适合带点得意的回应。",
    "reach_out": "一侧手臂缓缓向前伸出作邀请姿态，另一侧略晚跟随，停留后收回；不保证与外物接触。",
    "relieved_sigh": "肩部缓慢下沉，头与胸口做一次轻微呼气起伏，再回到放松姿态。适合松一口气。",
    "shake_no": "头部小幅左右摇动，肩部保持稳定，最后平稳回正。适合温和否定。",
    "shy_fidget": "头部略低，双臂以不同节奏小幅收近与放松，保持内敛的害羞姿态。",
    "shy_glance": "先略微低头，再悄悄偏向一侧看去，手臂保持低位并逐渐回正。适合害羞偷看。",
    "sleepy_doze": "以很慢的小幅低头和呼吸表现困意，双臂低垂，循环末端回到同一姿态。",
    "sleepy_nod": "缓慢低头，短暂停住后轻轻抬起，肩部仅做细微跟随。适合打瞌睡。",
    "soft_lean": "头与上身稍有先后地轻倾向一侧，双臂小幅回应，再慢慢回正。适合温柔靠近的示意。",
    "starlight_guard": "双臂适度抬起并收近胸前，头部保持关注，停留后缓缓放下。适合安抚或守护的示意。",
    "starlit_gaze": "头部缓缓上仰并侧望，配合微小呼吸与头发摆动，形成安静的仰望循环。",
    "stretch_yawn": "双臂错开地适度抬起舒展，头部轻仰后收回，不做大幅离地位移。适合疲倦时伸展。",
    "surprised": "短暂抬肩并轻轻弹起，双臂小幅张开，落地时膝踝吸收冲击，随后迅速但柔和地回稳。适合轻度惊讶。",
    "think_hmm": "头部轻偏，一侧前臂收近身体作思考示意，停留后放松；不保证手与下巴接触。",
    "wave_both": "双臂以适中高度先后抬起，左右错拍地轻摆，再逐渐放下。适合热情但克制的招呼。",
    "wave_hello": "一侧手臂抬到适中高度，前臂轻摆几次，另一侧保持放松，最后缓缓放下。适合打招呼。",
    "drag_dangle": "被拖动时保持轻微屈膝和低位双臂，左右腿做幅度有限的交替摆动，循环首尾闭合。",
    "drag_land": "轻轻屈膝缓冲，再逐渐伸展恢复站姿，双臂仅做小幅平衡动作。适合拖动结束。",
    "edge_bottom_sit": "屁股着地、双膝向外折开的鸭子坐：大腿外展外旋、小腿折回身侧，双臂低放，仅保留细微呼吸；由程序按蒙皮支撑面对齐屏幕底边。",
    "edge_fall": "短暂抬臂作失去平衡的反应，再收近身体并屈膝准备缓冲；末帧与落地首帧完全一致，窗口按重力感下落。",
    "edge_land_sit": "从摔落末帧无缝接地，双腿逐步收拢屈曲，上身与膝踝吸收冲击，最后停在与坐姿循环完全相同的姿态。",
    "edge_side_hang": "下半身和鞋全部藏在墙后，上半身大部分探出，只露少量裙摆下缘；双手扒边，面部和视线正对屏幕。",
    "edge_top_grip": "双手举过头顶扒住屏幕顶边、手距窄于肩宽，双腿屈膝下垂并缓慢摆荡，面部朝前。",
}


def keys(values, duration, field="rot"):
    return [{"t": round(t * duration, 6), field: list(v), "ease": "smooth"} for t, v in values]


def normalize_channel(channel, duration, loop):
    """Rescale whole overlong channels, never truncate their closing key."""
    if not channel:
        return
    maximum = max(k["t"] for k in channel)
    if maximum > duration:
        for key in channel:
            key["t"] = round(key["t"] * duration / maximum, 6)
    channel.sort(key=lambda key: key["t"])
    unique = {key["t"]: key for key in channel}
    channel[:] = list(unique.values())
    if channel[0]["t"] != 0:
        channel.insert(0, dict(copy.deepcopy(channel[0]), t=0.0))
    if loop:
        close = dict(copy.deepcopy(channel[0]), t=duration)
        if channel[-1]["t"] == duration:
            channel[-1] = close
        else:
            channel.append(close)


def direct_flow(channel, field):
    """Flow through directional passes, but retain holds and reversals."""
    for index, key in enumerate(channel[:-1]):
        if index == 0:
            continue  # explicit ease into a gesture/loop extremum
        previous, current, following = (channel[i][field] for i in (index - 1, index, index + 1))
        if not isinstance(current, list):
            previous, current, following = [previous], [current], [following]
        before = [b - a for a, b in zip(previous, current)]
        after = [b - a for a, b in zip(current, following)]
        if sum(a * b for a, b in zip(before, after)) > 1e-6:
            key["ease"] = "flow"
        elif before == [0] * len(before) or after == [0] * len(after):
            key["ease"] = "smooth"


def refine(document):
    if document.get("motion_revision") in AMPLITUDE_REVISIONS:
        d = copy.deepcopy(document)
        support_direction(d)
        continuous_bone_flow(d)
        # The anatomical pass lives in polish_citlali_motion; a migrated document
        # must be brought to the same final state as a freshly built one, or a
        # second run silently keeps the old (pre-polish) pose.
        polish_document(d)
        continuous_bone_flow(d)
        d["description"] = DESCRIPTIONS[d["id"]]
        d["motion_revision"] = REVISION
        return d
    d = copy.deepcopy(document)
    c = d["content"]
    duration = float(c.get("duration", d["duration"]))
    loop = c.get("loop", d.get("loop", False))
    bones = c["bones"]
    # Ordinary controls own each transform. Never animate a grant destination
    # alongside its source once the renderer evaluates PMX append transforms.
    for name in list(bones):
        if name.endswith("D") and name[:-1] in bones:
            bones[name[:-1]] = bones.pop(name)
    hanging = d["id"] in {"edge_side_hang", "edge_top_grip"}
    for name, track in bones.items():
        for kind, channel in track.items():
            if not isinstance(channel, list):
                continue
            normalize_channel(channel, duration, loop)
            if kind == "rotation":
                if name in {"左腕", "右腕"} and not hanging:
                    sign = 1 if name.startswith("左") else -1
                    baseline = [0, -50 * sign, -40 * sign]
                    for key in channel:
                        key["rot"] = [round(base + (value - base) * .76, 4) for base, value in zip(baseline, key["rot"])]
                elif name in {"左ひじ", "右ひじ"}:
                    sign = 1 if name.startswith("左") else -1
                    for key in channel:
                        key["rot"][2] = round(sign * min(68, 10 + .72 * abs(key["rot"][2])), 4)
                elif name in {"上半身", "上半身2", "首", "頭"}:
                    for key in channel:
                        key["rot"] = [round(value * .85, 4) for value in key["rot"]]
                # Delay the right arm's interior gesture landmarks slightly;
                # leave endpoints and hold topology unchanged.
                if name in {"右腕", "右ひじ", "右手首"} and not hanging:
                    for key in channel[1:-1]:
                        fraction = key["t"] / duration
                        key["t"] = round(duration * (fraction + .025 * fraction * (1 - fraction)), 6)
            if kind == "translation" and name == "全ての親" and d["id"] not in {"edge_bottom_sit", "edge_land_sit", "cheer_hop", "happy_bounce", "surprised", "edge_side_hang", "edge_side_hang_right"}:
                for key in channel:
                    key["trans"] = [round(max(-.12, min(.12, v)), 4) for v in key["trans"]]
            field = "rot" if kind == "rotation" else "trans"
            direct_flow(channel, field)
    for channel in c.get("morphs", {}).values():
        normalize_channel(channel, duration, loop)
        direct_flow(channel, "w" if "w" in channel[0] else "weight")
    if d["id"] == "edge_top_grip":
        # Arms and legs are authored by polish_citlali_motion.refine_top_grip from
        # solved FK contact targets; overwriting them here silently undid the
        # hanging silhouette and produced the old arms-spread cheer pose.
        pass
    if d["id"] == "dance_spin":
        bones["全ての親"]["rotation"] = keys([(0, [0, 0, 0]), (.16, [0, 45, 0]), (.36, [0, 145, 0]), (.56, [0, 245, 0]), (.76, [0, 335, 0]), (.9, [0, 360, 0]), (1, [0, 360, 0])], duration)
        for key in bones["全ての親"]["rotation"][1:5]:
            key["ease"] = "flow"
    support_direction(d)
    continuous_bone_flow(d)
    d["description"] = DESCRIPTIONS[d["id"]]
    c["notes"] = "动作方向修订：低幅度、左右错拍、连续经过点与停留点分开；仅关键帧示意，未进行接触约束或视觉解剖验证。"
    d["motion_revision"] = REVISION
    return d


def continuous_bone_flow(d):
    """Use shared tangents on BOTH sides of every continuous bone key.

    The sampler supplies zero endpoint/hold/reversal tangents and periodic loop
    tangents. Mixing incoming cosine with outgoing flow would stop on one side
    only, so do not selectively mark pass-through source keys. Explicit steps
    and author-tagged impact segments retain their authored timing semantics.
    Morph weights intentionally retain their independent blink/settle curves.
    """
    for track in d["content"]["bones"].values():
        for kind in ("rotation", "translation"):
            for key in track.get(kind, []):
                if key.get("ease") not in {"constant", "step"} and not key.get("impact", False):
                    key["ease"] = "flow"


def support_direction(d):
    """Absolute support recipes, safe to reapply without amplitude drift.

    Only the seated root height is set here.  The ``edge_bottom_sit`` legs are
    authored by ``polish_citlali_motion.refine_duck_sit`` from measured contact
    targets; rewriting them with a generic recipe made this pass non-idempotent,
    because a second run silently reverted the polished knee to a tucked value.
    """
    if d["id"] != "edge_bottom_sit":
        return
    duration = d["content"]["duration"]
    d["content"]["bones"]["全ての親"]["translation"] = keys(
        [(0, [0, -8.6, 0]), (1, [0, -8.6, 0])], duration, "trans"
    )


def match_landing(landing, sitting):
    """Set every final bone/morph channel to the exact sit entry state."""
    duration = landing["content"]["duration"]
    target = sitting["content"]
    for name in set(landing["content"]["bones"]) | set(target["bones"]):
        dest = landing["content"]["bones"].setdefault(name, {})
        for kind in set(dest) | set(target["bones"].get(name, {})):
            field = "rot" if kind == "rotation" else "trans"
            value = target["bones"].get(name, {}).get(kind, [{field: [0, 0, 0]}])[0][field]
            channel = dest.setdefault(kind, [{"t": 0, field: [0, 0, 0], "ease": "smooth"}])
            channel[:] = [key for key in channel if key["t"] < duration * .72]
            channel.extend([{"t": round(duration * .82, 6), field: copy.deepcopy(value), "ease": "smooth"}, {"t": duration, field: copy.deepcopy(value), "ease": "smooth"}])
    for name in set(landing["content"].get("morphs", {})) | set(target.get("morphs", {})):
        channel = landing["content"].setdefault("morphs", {}).setdefault(name, [{"t": 0, "w": 0}])
        value = target.get("morphs", {}).get(name, [{"w": 0}])[0].get("w", 0)
        channel[:] = [key for key in channel if key["t"] < duration * .72]
        channel.extend([{"t": round(duration * .82, 6), "w": value, "ease": "smooth"}, {"t": duration, "w": value, "ease": "smooth"}])


def mirror_side_peek(document):
    """Create the right-wall action from the final left-wall performance."""
    mirrored = copy.deepcopy(document)
    mirrored["id"] = "edge_side_hang_right"
    mirrored["name"] = "墙右侧站扒边"
    mirrored["description"] = "左侧最终姿态的严格镜像：下半身和鞋全部藏在墙后，上半身大部分探出，只露少量裙摆下缘，面部和视线正对屏幕。"

    def mirror_name(name):
        if name.startswith("左"):
            return "右" + name[1:]
        if name.startswith("右"):
            return "左" + name[1:]
        if name.endswith("_L"):
            return name[:-2] + "_R"
        if name.endswith("_R"):
            return name[:-2] + "_L"
        return name

    bones = mirrored["content"]["bones"]
    mirrored_bones = {}
    for old_name, source_track in bones.items():
        track = copy.deepcopy(source_track)
        for key in track.get("rotation", []):
            key["rot"] = [key["rot"][0], -key["rot"][1], -key["rot"][2]]
        for key in track.get("translation", []):
            key["trans"] = [-key["trans"][0], key["trans"][1], key["trans"][2]]
        mirrored_bones[mirror_name(old_name)] = track
    mirrored["content"]["bones"] = mirrored_bones
    return mirrored


def build_documents(root=ROOT):
    docs = {
        path: refine(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(root.rglob("*.json"))
        if path.name not in {"pack.json", "character.json", "edge_side_hang_right.json"}
    }
    by_id = {d["id"]: d for d in docs.values()}
    for document in docs.values():
        polish_document(document)
    right_path = root / "edge" / "edge_side_hang_right.json"
    docs[right_path] = mirror_side_peek(by_id["edge_side_hang"])
    by_id["edge_side_hang_right"] = docs[right_path]
    match_fall_to_land(by_id["edge_fall"], by_id["edge_land_sit"])
    match_landing(by_id["edge_land_sit"], by_id["edge_bottom_sit"])
    # Absolute support recipes and landing matching introduce fresh keys: this
    # must stay last, including on already-refined/migrated documents.
    for document in docs.values():
        continuous_bone_flow(document)
    return docs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the last-stage pass would change files")
    args = parser.parse_args()
    changed = []
    for path, document in build_documents().items():
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if not path.exists() or text != path.read_text(encoding="utf-8"):
            changed.append(path)
            if not args.check:
                path.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(changed)} motion documents {'need refinement' if args.check else 'refined'}")
    if args.check and changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
