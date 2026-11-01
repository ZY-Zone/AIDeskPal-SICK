"""First-run dependency bootstrap for AIDeskPal-SICK.

This file intentionally uses only the Python standard library.  It runs before
PySide6 exists, shows a small Tk window, creates .venv, installs the project,
and then starts the real application.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
DATA = ROOT / "user_data"
LOG = DATA / "bootstrap.log"
# The "with dependencies" release ships a pre-installed package tree here, so
# first run needs neither a virtualenv nor network access.
VENDOR_SITE = ROOT / "vendor" / "site-packages"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def venv_python() -> Path:
    return VENV / "Scripts" / "python.exe"


def venv_pythonw() -> Path:
    return VENV / "Scripts" / "pythonw.exe"


def has_vendor_site() -> bool:
    return (VENDOR_SITE / "PySide6").is_dir()


def vendor_python_tag() -> str:
    """Python ``major.minor`` the vendored tree was built for (empty if unknown).

    The bundled packages contain compiled extensions, so the archive only works
    with that exact interpreter version.  Reading it lets us say so plainly
    instead of surfacing a numpy C-extension traceback.
    """
    marker = ROOT / "vendor" / "PYTHON_VERSION"
    try:
        return marker.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def vendor_version_ok() -> bool:
    expected = vendor_python_tag()
    if not expected:
        return True
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    return actual == expected


def launch_env() -> dict[str, str]:
    """Environment that puts the app and its dependencies on sys.path."""
    parts = [str(ROOT / "src")]
    if has_vendor_site():
        parts.append(str(VENDOR_SITE))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["AIDESKPAL_DATA_DIR"] = str(DATA)
    return env


class BootstrapWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AIDeskPal-SICK · 首次启动")
        self.root.geometry("560x280")
        self.root.resizable(False, False)
        self.root.configure(bg="#12101c")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.closed = False
        self.running = True

        title = tk.Label(
            self.root,
            text="首次启动 · 安装运行环境",
            bg="#12101c",
            fg="#f3efff",
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        title.pack(anchor="w", padx=28, pady=(28, 6))
        hint = tk.Label(
            self.root,
            text="正在安装 PySide6、Pillow、httpx 等依赖。\n"
            "第一次安装可能需要几分钟，请保持网络连接。",
            justify="left",
            bg="#12101c",
            fg="#a9a3c2",
            font=("Microsoft YaHei UI", 10),
        )
        hint.pack(anchor="w", padx=28, pady=(0, 18))

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=500)
        self.progress.pack(fill="x", padx=28)
        self.progress.start(12)

        self.status = tk.Label(
            self.root,
            text="准备中…",
            anchor="w",
            bg="#12101c",
            fg="#b9a7ff",
            font=("Microsoft YaHei UI", 10),
        )
        self.status.pack(fill="x", padx=28, pady=(12, 0))

        self.detail = tk.Label(
            self.root,
            text=str(LOG),
            anchor="w",
            bg="#12101c",
            fg="#6f6885",
            font=("Microsoft YaHei UI", 8),
        )
        self.detail.pack(fill="x", padx=28, pady=(6, 0))

    def _on_close(self) -> None:
        if self.running and not messagebox.askyesno(
            "AIDeskPal-SICK", "依赖仍在安装，确定要退出吗？"
        ):
            return
        self.closed = True
        self.root.destroy()

    def set_status(self, text: str) -> None:
        if self.closed:
            return

        def apply() -> None:
            if not self.closed:
                self.status.configure(text=text)

        # _install runs on a worker thread; Tk must only be touched here.
        self.root.after(0, apply)

    def finish(self) -> None:
        if self.closed:
            return
        self.running = False
        self.progress.stop()
        self.set_status("安装完成，正在启动 AIDeskPal-SICK…")
        python = venv_pythonw() if venv_pythonw().is_file() else venv_python()
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            subprocess.Popen([str(python), "-m", "aideskpal"], cwd=str(ROOT), env=launch_env())
        except Exception as exc:
            messagebox.showerror("AIDeskPal-SICK", f"启动失败：\n{exc}")
            self.closed = True
            self.root.destroy()
            return
        self.closed = True
        self.root.after(700, self.root.destroy)

    def fail(self, error: str) -> None:
        if self.closed:
            return
        self.running = False
        self.progress.stop()
        self.set_status("安装失败")
        messagebox.showerror(
            "AIDeskPal-SICK",
            "依赖安装失败。\n\n"
            f"{error}\n\n"
            f"详细日志：\n{LOG}",
        )
        self.closed = True
        self.root.destroy()

    def run(self) -> None:
        threading.Thread(target=self._install, daemon=True).start()
        self.root.mainloop()

    def _install(self) -> None:
        try:
            if sys.version_info < (3, 11):
                raise RuntimeError("需要 Python 3.11 或更高版本")
            DATA.mkdir(parents=True, exist_ok=True)
            with LOG.open("w", encoding="utf-8") as log:
                log.write(f"root={ROOT}\npython={sys.executable}\n")
                if not venv_python().is_file():
                    self.set_status("创建虚拟环境 .venv…")
                    result = subprocess.run(
                        [sys.executable, "-m", "venv", str(VENV)],
                        cwd=str(ROOT),
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        creationflags=NO_WINDOW,
                    )
                    if result.returncode != 0:
                        raise RuntimeError("创建 .venv 失败")

                self.set_status("安装项目依赖（可能需要几分钟）…")
                uv = shutil.which("uv")
                if uv:
                    command = [
                        uv,
                        "pip",
                        "install",
                        "--python",
                        str(venv_python()),
                        "-e",
                        ".",
                    ]
                else:
                    command = [
                        str(venv_python()),
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "-e",
                        ".",
                    ]
                log.write("command=" + " ".join(command) + "\n")
                log.flush()
                result = subprocess.run(
                    command,
                    cwd=str(ROOT),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=NO_WINDOW,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"pip/uv 返回 {result.returncode}")
            self.root.after(0, self.finish)
        except Exception as exc:
            self.root.after(0, lambda error=str(exc): self.fail(error))


def _launch(executable: Path) -> bool:
    try:
        subprocess.Popen([str(executable), "-m", "aideskpal"], cwd=str(ROOT), env=launch_env())
        return True
    except Exception:
        return False


def _report_version_mismatch() -> None:
    expected = vendor_python_tag()
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    message = (
        f"这个版本自带已编译的依赖，只能用 Python {expected}（64 位）运行。\n"
        f"当前解释器是 Python {actual}。\n\n"
        f"请安装 Python {expected} 后重试，或改用「纯代码版」压缩包"
        f"（它会用你现有的 Python 现场安装依赖）。"
    )
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("AIDeskPal-SICK", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    # The "with dependencies" release carries vendor/site-packages, so there is
    # nothing to install: start the app with the system interpreter directly.
    if has_vendor_site():
        if not vendor_version_ok():
            _report_version_mismatch()
            return 2
        candidate = Path(sys.executable)
        pythonw = candidate.with_name("pythonw.exe")
        for executable in (pythonw, candidate):
            if executable.is_file() and _launch(executable):
                return 0

    if venv_pythonw().is_file() and _launch(venv_pythonw()):
        return 0
    BootstrapWindow().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
