"""Remove redundant files and directories left over from development.

Every target is checked against a protected list first, so private state
(``user_data``), the character assets and the action sources can never be
deleted by this script even if a glob is wrong.

Run a dry run first, then apply:
    .venv/Scripts/python.exe tools/clean_redundant.py
    .venv/Scripts/python.exe tools/clean_redundant.py --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Never touched, regardless of what the rules below match.
PROTECTED = (
    ROOT / "user_data",
    ROOT / "src" / "aideskpal" / "character",
    ROOT / "actions",
    ROOT / "sample_content",
    ROOT / "assets",
    ROOT / "schemas",
    ROOT / "plugins",
    ROOT / "tests",
    ROOT / "docs",
    ROOT / "tools",
    ROOT / "server",
)


def _protected(path: Path) -> bool:
    resolved = path.resolve()
    for guard in PROTECTED:
        guard_resolved = guard.resolve()
        if resolved == guard_resolved or guard_resolved in resolved.parents:
            return True
    return False


def _collect() -> list[tuple[Path, str]]:
    targets: list[tuple[Path, str]] = []

    # 1. Old per-feature state snapshots. Their unique settings/memory/secrets
    #    files are preserved in the backup archive; the 19.6 MB market bundle
    #    inside each one was byte-identical to the live copy.
    for snapshot in sorted(ROOT.glob("portable_data_backup*")):
        if snapshot.is_dir():
            targets.append((snapshot, "old state snapshot (archived in backup)"))

    # 2. Byte-code caches outside the virtualenv.
    for cache in sorted(ROOT.rglob("__pycache__")):
        if ".venv" in cache.parts:
            continue
        targets.append((cache, "byte-code cache"))

    # 3. Test scratch and pytest cache.
    for name in (".pytest_cache", "pytest-of-22089"):
        path = ROOT / name
        if path.exists():
            targets.append((path, "test scratch/cache"))

    # 4. Root-level run logs from earlier sessions.
    for log in sorted(ROOT.glob("*.log")):
        targets.append((log, "session log"))

    # 5. Scratch probes, except the current edge captures which stay as the
    #    visual reference for the edge poses.
    probes = ROOT / "probes"
    if probes.is_dir():
        for child in sorted(probes.iterdir()):
            if child.name == "edge":
                continue
            targets.append((child, "scratch probe output"))

    # 6. Screenshots of features that no longer exist (the lie/wide pose was
    #    removed) plus the throwaway A-K pose iteration series.
    artifacts = ROOT / "artifacts"
    if artifacts.is_dir():
        for image in sorted(artifacts.iterdir()):
            if not image.is_file():
                continue
            name = image.name.lower()
            if "lie" in name or name.startswith("edge_sit_test"):
                targets.append((image, "screenshot of a removed feature / iteration"))

    # Deduplicate by resolved path: the probe sweep can reach the same entry
    # through more than one rule (a directory and a glob over its children).
    seen: set[Path] = set()
    unique: list[tuple[Path, str]] = []
    for path, reason in targets:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append((path, reason))

    safe: list[tuple[Path, str]] = []
    for path, reason in unique:
        # Caches are always disposable, even inside otherwise protected trees.
        if path.name != "__pycache__" and _protected(path):
            print(f"  SKIP (protected): {path.relative_to(ROOT)}")
            continue
        safe.append((path, reason))
    return safe


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually delete")
    args = parser.parse_args()

    targets = _collect()
    total = sum(_size(path) for path, _ in targets)
    print(f"{len(targets)} targets, {total / 1e6:.1f} MB\n")
    for path, reason in targets:
        print(f"  {path.relative_to(ROOT)!s:60} {_size(path) / 1e6:8.2f} MB  {reason}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to delete.")
        return

    removed = 0
    for path, _ in targets:
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except OSError as exc:
            print(f"  FAILED {path.relative_to(ROOT)}: {exc}", file=sys.stderr)
    print(f"\nRemoved {removed}/{len(targets)} targets, freed about {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
