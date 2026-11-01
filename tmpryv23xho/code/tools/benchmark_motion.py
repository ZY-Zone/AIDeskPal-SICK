"""Reproducible CPU-only motion benchmark; never exports private model data.

Run: .venv/Scripts/python tools/benchmark_motion.py --frames 240 --profile
Timings exclude model/JSON loading, GL, morph application and vertex skinning.
"""
from __future__ import annotations

import argparse
import cProfile
import copy
from pathlib import Path
import platform
import pstats
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from aideskpal.animation.action import load_action
from aideskpal.pmx.model import load_pmx
from aideskpal.pmx.skeleton import Skeleton


def measure(call, frames):
    for i in range(12):
        call(i)
    samples = np.empty(frames)
    cpu = np.empty(frames)
    for i in range(frames):
        start = time.perf_counter_ns()
        cpu_start = time.process_time_ns()
        call(i)
        cpu[i] = (time.process_time_ns() - cpu_start) / 1e6
        samples[i] = (time.perf_counter_ns() - start) / 1e6
    return f'{np.median(samples):7.3f} / {np.percentile(samples,95):7.3f}; CPU mean {np.mean(cpu):7.3f}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=ROOT / 'dist/AIDeskPal-SICK/user_data/market/bundles/citlali_summer/1.0.0/model/model.pmx')
    parser.add_argument('--frames', type=int, default=240)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    if args.frames < 1:
        parser.error('--frames must be positive')
    model = load_pmx(args.model)
    model.to_render_space()
    rig = Skeleton(model)
    print(f'Python {platform.python_version()}; numpy {np.__version__}; {platform.processor()}')
    print(f'{rig.count} bones; {sum(bool(b.flags & 0x300) for b in model.bones)} grant bones; frames={args.frames}')
    print('Timings milliseconds, median / p95. Sampling t spans the full clip; pose-only stages use precomputed poses.')
    selected = ['idle_starlight', 'wave_hello', 'dance_spin', 'edge/edge_top_grip', 'edge/edge_bottom_sit']
    profile_clips = []
    for name in selected:
        clip = load_action(ROOT / 'actions/citlali_summer' / (name + '.json'), model)
        times = [(i+.37) / args.frames * clip.duration for i in range(args.frames)]
        poses = [clip.sample(t) for t in times]
        sample = lambda i: clip.sample(times[i % args.frames])
        matrices = lambda i: rig.skin_matrices(poses[i % args.frames])
        grants = lambda i: rig._granted_transforms(poses[i % args.frames])
        combined = lambda i: rig.skin_matrices(sample(i))
        smooth = copy.deepcopy(clip)
        for track in smooth.bone_tracks:
            track.rotation_easings = ['smooth' if e == 'flow' else e for e in track.rotation_easings]
            track.translation_easings = ['smooth' if e == 'flow' else e for e in track.translation_easings]
        for track in smooth.morph_tracks:
            track.easings = ['smooth' if e == 'flow' else e for e in track.easings]
        print(f'\n{name}: {len(clip.bone_tracks)} bone tracks, {sum(e=="flow" for t in clip.bone_tracks for e in t.rotation_easings)} rotation flow keys')
        print(' sample       ', measure(sample, args.frames))
        print(' smooth-only* ', measure(lambda i: smooth.sample(times[i % args.frames]), args.frames))
        print(' grants       ', measure(grants, args.frames))
        print(' skin matrices', measure(matrices, args.frames))
        print(' sample + skin', measure(combined, args.frames))
        profile_clips.append((clip, times))
    print('\n*In-memory diagnostic baseline only; substitutes easing, not equivalent motion.')
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        for clip, times in profile_clips:
            for t in times:
                rig.skin_matrices(clip.sample(t))
        profiler.disable()
        pstats.Stats(profiler).strip_dirs().sort_stats('cumulative').print_stats(28)


if __name__ == '__main__':
    main()
