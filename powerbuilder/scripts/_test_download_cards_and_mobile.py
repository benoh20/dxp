"""
Validate the Milestone C download-card layout and mobile drawer markup.

Run from /powerbuilder:
    python scripts/_test_download_cards_and_mobile.py

Asserts:
1. partials/message.html renders typed download cards (thumb + label + filename)
   with the right thumb_kind text and a --dl-color CSS variable.
2. Legacy single-file fallback (generated_file_path without downloads list)
   still renders a card.
3. chat.html includes the mobile drawer scaffolding: hidden checkbox,
   hamburger label, scrim label, sidebar slideout via :checked.
4. chat.html includes a 768px @media block that adjusts sidebar/thread.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-validation-only")
os.environ["DEBUG"] = "True"

import django

django.setup()

from django.template.loader import render_to_string
from django.test import RequestFactory


def _render_message(downloads=None, generated_file_path=None,
                    generated_filename=None, download_label=None) -> str:
    return render_to_string("partials/message.html", {
        "answer_html":         "<p>Here is your plan.</p>",
        "active_agents":       ["researcher", "messaging"],
        "source_cards":        [],
        "c3_footer":           None,
        "downloads":           downloads or [],
        "generated_file_path": generated_file_path,
        "generated_filename":  generated_filename,
        "download_label":      download_label,
        "errors":              [],
    })


def _render_chat() -> str:
    rf = RequestFactory()
    request = rf.get("/")
    return render_to_string("chat.html", {
        "DEMO_MODE":           True,
        "messages":            [],
        "conversations":       [],
        "current_conversation": None,
    }, request=request)


def main() -> int:
    failures: list[str] = []

    # 1. Two-card render with mixed types: DOCX + CSV.
    downloads = [
        {"filename": "plan.docx",   "label": "Download Word Doc",
         "thumb_kind": "DOCX", "thumb_color": "#3b82f6"},
        {"filename": "targets.csv", "label": "Download CSV",
         "thumb_kind": "CSV",  "thumb_color": "#22c55e"},
    ]
    html = _render_message(downloads=downloads)
    if 'class="dl-row"' not in html:
        failures.append("dl-row container missing")
    if html.count('class="dl-card"') != 2:
        failures.append(f"expected 2 dl-card, got {html.count('class=\"dl-card\"')}")
    if 'class="dl-thumb"' not in html or ">DOCX<" not in html or ">CSV<" not in html:
        failures.append("dl-thumb badges missing or wrong text")
    if "--dl-color: #3b82f6" not in html:
        failures.append("DOCX --dl-color CSS variable missing")
    if "--dl-color: #22c55e" not in html:
        failures.append("CSV --dl-color CSS variable missing")
    if 'class="dl-label">Download Word Doc' not in html:
        failures.append("dl-label text missing for Word doc")
    if 'class="dl-filename"' not in html or "plan.docx" not in html:
        failures.append("dl-filename missing or filename not rendered")
    if 'class="dl-arrow"' not in html:
        failures.append("dl-arrow svg missing")
    # Old style (legacy btn-download or inline style) should be gone for cards.
    if 'class="btn-download"' in html:
        failures.append("legacy btn-download still rendered alongside dl-card")

    # 2. Legacy single-file fallback (no downloads list, just generated_file_path).
    html_legacy = _render_message(
        generated_file_path="/tmp/exports/old.csv",
        generated_filename="old.csv",
        download_label="Download CSV",
    )
    if 'class="dl-card"' not in html_legacy:
        failures.append("legacy single-file fallback should render as dl-card")
    if "old.csv" not in html_legacy:
        failures.append("legacy fallback missing filename")
    if "Download CSV" not in html_legacy:
        failures.append("legacy fallback missing label")

    # 3. Empty (no downloads, no generated_file_path) renders no card.
    html_empty = _render_message()
    if 'class="dl-card"' in html_empty:
        failures.append("empty render should not include dl-card")

    # 4. Mobile drawer scaffolding in chat.html.
    chat_html = _render_chat()
    for marker in (
        'id="sidebar-toggle"',                       # hidden checkbox
        'class="sidebar-hamburger"',                 # toggle label
        'class="sidebar-scrim"',                     # outside-click closer
        'for="sidebar-toggle"',                      # at least one label points at it
        '#sidebar-toggle:checked ~ .chat-root .sidebar',  # CSS slideout rule
        '@media (max-width: 768px)',                 # responsive block exists
    ):
        if marker not in chat_html:
            failures.append(f"mobile drawer marker missing: {marker}")

    # 5. dl-card CSS rules present so the rendered cards are styled.
    for css_marker in (
        ".dl-card",
        ".dl-thumb",
        ".dl-meta",
        ".dl-label",
        ".dl-filename",
        ".dl-arrow",
    ):
        if css_marker not in chat_html:
            failures.append(f"dl-card CSS rule missing: {css_marker}")

    # 6. Mobile breakpoint touches the right elements.
    media_block_start = chat_html.find("@media (max-width: 768px)")
    media_block = chat_html[media_block_start: media_block_start + 1600] if media_block_start >= 0 else ""
    for inside in (".sidebar", ".chat-scroll", ".dl-card", ".demo-carousel"):
        if inside not in media_block:
            failures.append(f"@media block does not adjust {inside}")

    print(f"Download cards + mobile drawer test: 6 assertion groups, ~24 checks.")
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: download-card + mobile-drawer assertions OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
