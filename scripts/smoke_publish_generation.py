"""Smoke test for the publish package generation flow.

Prerequisites:
- Backend is running on http://127.0.0.1:8001
- Frontend is running on http://127.0.0.1:5178
- Python Playwright is installed and browsers are available
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


BASE_API = "http://127.0.0.1:8001"
FRONTEND_URL = "http://127.0.0.1:5178/"


def request_json(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.load(resp)


def delete_draft(draft_id: int) -> None:
    req = urllib.request.Request(f"{BASE_API}/api/drafts/{draft_id}", method="DELETE")
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 204:
            raise RuntimeError(f"cleanup failed: HTTP {resp.status}")


def choose_topic_title(preferred: str = "") -> str:
    if preferred:
        return preferred
    data = request_json(f"{BASE_API}/api/topics?limit=50")
    items = data.get("items", data) if isinstance(data, dict) else data
    for item in items:
        if item.get("status") == "generated" and int(item.get("score") or 0) >= 60:
            return item["title"]
    raise RuntimeError("no generated topic with score >= 60 found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic-title", default="", help="Exact topic title to select in the sidebar.")
    parser.add_argument("--screenshot", default="/tmp/ai-content-agent-smoke-publish.png")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        print(f"Playwright import failed: {exc}", file=sys.stderr)
        return 2

    topic_title = choose_topic_title(args.topic_title)
    created_draft_id: int | None = None
    console_errors: list[str] = []
    page_errors: list[str] = []
    responses: list[dict] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type in ("error", "warning") else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            def on_response(resp) -> None:
                if "/generate-variant" not in resp.url:
                    return
                item = {"url": resp.url, "status": resp.status}
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        item["draft_id"] = data.get("draft", {}).get("id")
                        item["cards"] = len(data.get("cards", []))
                except Exception as exc:
                    item["error"] = repr(exc)
                responses.append(item)

            page.on("response", on_response)
            page.goto(FRONTEND_URL, wait_until="networkidle")
            page.locator("a.nav-item").filter(has_text="发布包编辑").click(timeout=10000)
            page.wait_for_selector(".draft-topic-sidebar", timeout=10000)
            page.locator(".draft-topic-sidebar").get_by_text(topic_title, exact=True).click(timeout=10000)
            page.wait_for_selector(".variant-panel", timeout=15000)
            page.get_by_role("button", name="生成匹配卡片", exact=True).click(timeout=10000)
            page.wait_for_timeout(5000)

            body_text = page.locator("body").inner_text(timeout=5000)
            card_count = page.locator(".xhs-card").count()
            screenshot = Path(args.screenshot)
            page.screenshot(path=str(screenshot), full_page=False)
            browser.close()

        if responses and responses[-1].get("draft_id"):
            created_draft_id = int(responses[-1]["draft_id"])
        if not responses:
            raise RuntimeError("generate-variant response was not captured")
        if responses[-1].get("status") != 200:
            raise RuntimeError(f"generate-variant failed: {responses[-1]}")
        if "页面渲染遇到问题" in body_text:
            raise RuntimeError("error fallback rendered")
        if "发布包编辑" not in body_text or "生成新发布方案" not in body_text:
            raise RuntimeError("publish editor content missing after generation")
        if card_count < 2:
            raise RuntimeError(f"expected generated cards, got {card_count}")
        if page_errors or console_errors:
            raise RuntimeError(f"page errors={page_errors}, console errors={console_errors}")

        print(json.dumps({
            "ok": True,
            "topic_title": topic_title,
            "created_draft_id": created_draft_id,
            "card_count": card_count,
            "screenshot": args.screenshot,
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        if created_draft_id:
            delete_draft(created_draft_id)


if __name__ == "__main__":
    raise SystemExit(main())
