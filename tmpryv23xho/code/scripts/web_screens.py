"""Capture the three market portals with Playwright + installed Edge."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

EDGE = os.environ.get("EDGE_PATH", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
BASE = os.environ.get("CW_LOCAL_URL", "http://127.0.0.1:8010")
ADMIN_PASSWORD = os.environ.get("CW_ADMIN_PASSWORD", "")
USER_PASSWORD = os.environ.get("CW_SCREEN_USER_PASSWORD", "")
USERNAME = os.environ.get("CW_SCREEN_USER", "downloaduser")
CREATOR_PASSWORD = os.environ.get("CW_SCREEN_CREATOR_PASSWORD", "")
CREATOR_NAME = os.environ.get("CW_SCREEN_CREATOR", "creator1")
if not ADMIN_PASSWORD:
    raise SystemExit("Set CW_ADMIN_PASSWORD to capture the admin page.")
OUT = Path("probes/web")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=EDGE, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        page.goto(BASE + "/cw", wait_until="networkidle")
        page.screenshot(path=str(OUT / "landing.png"), full_page=False)
        print("landing")

        page.goto(BASE + "/cwwlc", wait_until="networkidle")
        page.screenshot(path=str(OUT / "creator_login.png"), full_page=False)
        if CREATOR_PASSWORD:
            page.fill("#username", CREATOR_NAME)
            page.fill("#password", CREATOR_PASSWORD)
            page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(OUT / "creator_dashboard.png"), full_page=False)
        print("creator")

        page.goto(BASE + "/cwwlc/upload/bundle", wait_until="networkidle")
        page.screenshot(path=str(OUT / "creator_upload.png"), full_page=True)
        print("upload")

        page.goto(BASE + "/cwadmin", wait_until="networkidle")
        page.fill("#password", ADMIN_PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(OUT / "admin_dashboard.png"), full_page=False)
        print("admin")

        page.goto(BASE + "/cwusr", wait_until="networkidle")
        if USER_PASSWORD:
            page.fill("#username", USERNAME)
            page.fill("#password", USER_PASSWORD)
            page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(OUT / "market.png"), full_page=False)
        page.goto(BASE + "/cwusr/plugins", wait_until="networkidle")
        page.screenshot(path=str(OUT / "plugins.png"), full_page=False)
        print("user")

        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
