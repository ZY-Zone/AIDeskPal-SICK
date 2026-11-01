"""Create a consolidated safety backup before the redundancy cleanup.

Two archives, both outside the project so cleanup cannot touch them:

  project.zip       source, docs, tools, tests, schemas, plugins, root files
                    (excludes .venv, caches, probes, artifacts, user_data and the
                    old portable_data_backup_* snapshots)
  state.zip         the live user_data tree, plus the small unique state files
                    (settings/memory/secrets/sqlite/logs) from every old
                    portable_data_backup_* snapshot.  The 19.6 MB market bundle
                    inside each snapshot is byte-identical to the live one, so it
                    is stored once, via user_data, instead of eleven times.

Run from the repository root:
    .venv/Scripts/python.exe tools/make_backup.py
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / "aideskpal-sick.backup"

PROJECT_SKIP_DIRS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "probes",
    "artifacts",
    "user_data",
    "pytest-of-22089",
    ".git",
}
PROJECT_SKIP_PREFIX = ("portable_data_backup",)
STATE_FILES = ("settings.json", "memory.json", "secrets.dat", "long_term_memory.sqlite3")


def _skip_project(rel: Path) -> bool:
    parts = rel.parts
    if any(part in PROJECT_SKIP_DIRS for part in parts):
        return True
    return any(part.startswith(PROJECT_SKIP_PREFIX) for part in parts)


def _add_tree(archive: zipfile.ZipFile, base: Path, prefix: str, skip=None) -> int:
    count = 0
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if skip is not None and skip(rel):
            continue
        archive.write(path, f"{prefix}/{rel.as_posix()}")
        count += 1
    return count


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = DEST / stamp
    target.mkdir(parents=True, exist_ok=True)

    project_zip = target / "project.zip"
    with zipfile.ZipFile(project_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        files = _add_tree(archive, ROOT, "", _skip_project)
    print(f"project.zip  {files} files  {project_zip.stat().st_size / 1e6:.1f} MB")

    state_zip = target / "state.zip"
    with zipfile.ZipFile(state_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        files = _add_tree(archive, ROOT / "user_data", "user_data")
        snapshots = 0
        for snapshot in sorted(ROOT.glob("portable_data_backup*")):
            if not snapshot.is_dir():
                continue
            for name in STATE_FILES:
                source = snapshot / name
                if source.is_file():
                    archive.write(source, f"snapshots/{snapshot.name}/{name}")
                    files += 1
            snapshot_logs = snapshot / "logs"
            if snapshot_logs.is_dir():
                for log in sorted(snapshot_logs.glob("*")):
                    if log.is_file():
                        archive.write(log, f"snapshots/{snapshot.name}/logs/{log.name}")
                        files += 1
            snapshots += 1
    print(f"state.zip    {files} files  {state_zip.stat().st_size / 1e6:.1f} MB  ({snapshots} snapshots)")

    # Verify both archives are readable and every entry has a sane size.
    for archive_path in (project_zip, state_zip):
        with zipfile.ZipFile(archive_path) as archive:
            bad = archive.testzip()
            assert bad is None, f"{archive_path.name}: corrupt entry {bad}"
            names = archive.namelist()
            assert names, f"{archive_path.name}: empty"
            print(f"verified {archive_path.name}: {len(names)} entries, testzip clean")
    print(f"BACKUP OK -> {target}")


if __name__ == "__main__":
    main()
