"""Build the two GitHub release archives.

    source    client program only, no dependencies (small)
    with-deps the same tree plus offline dependency wheels in vendor/wheels, so
              first run installs without network access

Both archives are produced from the current git commit, so a release can never
contain uncommitted local edits.  Run from the repository root:

    .venv/Scripts/python.exe tools/make_release.py            # build both
    .venv/Scripts/python.exe tools/make_release.py --source   # source only
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WHEELS = ROOT / "vendor" / "wheels"
REQUIREMENTS = ROOT / "requirements.txt"

OFFLINE_NOTE = """AIDeskPal-SICK {version} · 含依赖版
=================================================

这个压缩包已经包含全部运行依赖的 wheel 文件，首次启动**不需要联网**。

使用步骤
---------
1. 需要本机已安装 Python 3.11 或更高版本（仅此一项前置条件）。
2. 双击 `bootstrap.cmd`。
   它会创建 .venv、从 `vendor/wheels` 离线安装依赖，然后启动桌宠。
3. 之后日常启动双击 `run.cmd` 即可。

说明
-----
- 首次安装的日志写在 `user_data/bootstrap.log`。
- 角色资源（PMX / 贴图 / 动作）不随包提供：可在客户端内的资源市场安装，
  或把自包含角色包放进 `src/aideskpal/character/<model_id>/`。
- 本包不含测试；二次开发请自行编写。
"""


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def _export(commit: str, target: Path) -> None:
    """Extract the committed tree into ``target`` with git archive."""
    target.mkdir(parents=True, exist_ok=True)
    archive = target.parent / "_export.zip"
    with archive.open("wb") as handle:
        result = subprocess.run(
            ["git", "archive", "--format=zip", commit],
            cwd=ROOT,
            stdout=handle,
        )
        if result.returncode != 0:
            raise SystemExit("git archive failed")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(target)
    archive.unlink()


def _download_wheels() -> int:
    """Fetch every runtime dependency as a wheel for win_amd64 / cp313."""
    if WHEELS.exists():
        shutil.rmtree(WHEELS)
    WHEELS.mkdir(parents=True, exist_ok=True)
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    executable = str(python) if python.is_file() else sys.executable
    command = [
        executable,
        "-m",
        "pip",
        "download",
        "-r",
        str(REQUIREMENTS),
        "--dest",
        str(WHEELS),
        "--only-binary",
        ":all:",
        "--platform",
        "win_amd64",
        "--python-version",
        "313",
        "--implementation",
        "cp",
        "--disable-pip-version-check",
    ]
    print("downloading wheels…")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit("pip download failed")
    return sum(1 for _ in WHEELS.glob("*.whl"))


def _zip_tree(base: Path, prefix: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, f"{prefix}/{path.relative_to(base).as_posix()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true", help="only build the code archive")
    args = parser.parse_args()

    commit = _git("rev-parse", "HEAD")
    short = _git("rev-parse", "--short", "HEAD")
    if _git("status", "--porcelain"):
        print("warning: working tree has uncommitted changes; archives use HEAD only")
    version = _version()
    name = f"AIDeskPal-SICK-{version}"
    DIST.mkdir(parents=True, exist_ok=True)
    print(f"commit {short} · version {version}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        code_dir = tmp_path / "code"
        _export(commit, code_dir)

        source_zip = DIST / f"{name}-source.zip"
        _zip_tree(code_dir, name, source_zip)
        print(f"  {source_zip.name}  {source_zip.stat().st_size / 1e6:.1f} MB")

        if args.source:
            return

        count = _download_wheels()
        wheel_mb = sum(p.stat().st_size for p in WHEELS.glob("*.whl")) / 1e6
        print(f"  {count} wheels, {wheel_mb:.1f} MB")

        deps_dir = tmp_path / "deps"
        shutil.copytree(code_dir, deps_dir)
        shutil.copytree(WHEELS, deps_dir / "vendor" / "wheels")
        (deps_dir / "README-离线安装.txt").write_text(
            OFFLINE_NOTE.format(version=version), encoding="utf-8"
        )
        with_deps_zip = DIST / f"{name}-with-deps.zip"
        _zip_tree(deps_dir, name, with_deps_zip)
        print(f"  {with_deps_zip.name}  {with_deps_zip.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
