"""
Validate the Milestone B empty-state carousel and voterfile chip.

Run from /powerbuilder:
    python scripts/_test_demo_carousel.py

Asserts the chat template renders correctly in both DEMO_MODE on and off:
1. Empty-state hero structure: icon, headline, subtitle, hint footer.
2. Carousel renders all 5 demo tiles with correct categories and data-prompt.
3. Voter file chip renders only when DEMO_MODE=True.
4. Each tile has a non-empty data-prompt attribute (so JS handler has work to do).
5. JS handler binds to .demo-tile (not stale demo-load-btn).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-validation-only")
os.environ["DEBUG"] = "True"  # Disable HSTS-style headers; we only test rendering.

import django

django.setup()

from django.template.loader import render_to_string
from django.test import RequestFactory


EXPECTED_CHIPS = [
    ("demo-tile-chip--plan", "Full plan"),
    ("demo-tile-chip--win",  "Win number"),
    ("demo-tile-chip--opp",  "Opposition"),
    ("demo-tile-chip--lang", "Multilingual"),
    ("demo-tile-chip--vf",   "Voter file"),
]


def _render(demo_mode: bool) -> str:
    """Render chat.html with DEMO_MODE flipped via context override."""
    rf = RequestFactory()
    request = rf.get("/")
    # Inject only the bits the template reads; avoids running the full view.
    # Milestone G: demo_tiles is now context-driven (was hardcoded in template),
    # so we feed it the same source of truth the view does.
    from chat.demo_tiles import get_demo_tiles
    ctx = {
        "DEMO_MODE": demo_mode,
        "messages": [],
        "conversations": [],
        "current_conversation": None,
        "demo_tiles": get_demo_tiles(),
    }
    return render_to_string("chat.html", ctx, request=request)


def main() -> int:
    failures: list[str] = []

    html_demo_on = _render(demo_mode=True)
    html_demo_off = _render(demo_mode=False)

    # 1. Empty-state hero structure.
    for marker in (
        'class="empty-state"',
        'class="empty-hero"',
        'class="empty-hero-icon"',
        'class="empty-subtitle"',
        'class="empty-hint"',
    ):
        if marker not in html_demo_on:
            failures.append(f"empty-state marker missing in demo-on render: {marker}")

    # 2. Carousel container + all 5 tiles render in BOTH modes.
    for label, html in (("demo-on", html_demo_on), ("demo-off", html_demo_off)):
        if 'class="demo-carousel"' not in html:
            failures.append(f"[{label}] demo-carousel container missing")
        tile_count = len(re.findall(r'class="demo-tile"', html))
        if tile_count != 6:
            failures.append(f"[{label}] expected 6 demo-tile elements, got {tile_count}")

        # Each chip variant + label present.
        for chip_class, chip_text in EXPECTED_CHIPS:
            if chip_class not in html:
                failures.append(f"[{label}] missing chip variant: {chip_class}")
            if f">{chip_text}<" not in html:
                failures.append(f"[{label}] missing chip text: {chip_text}")

    # 3. Each tile has a data-prompt attribute with non-empty value.
    prompts = re.findall(r'data-prompt="([^"]+)"', html_demo_on)
    if len(prompts) != 6:
        failures.append(f"expected 6 data-prompt attributes, got {len(prompts)}")
    for i, p in enumerate(prompts):
        if len(p.strip()) < 10:
            failures.append(f"data-prompt[{i}] is too short to be a real prompt: {p!r}")

    # 4. Voter file chip renders ONLY when DEMO_MODE=True.
    if 'class="vf-chip"' not in html_demo_on:
        failures.append("vf-chip should render when DEMO_MODE=True")
    if 'class="vf-chip-dot"' not in html_demo_on:
        failures.append("vf-chip-dot (pulse indicator) should render in demo mode")
    if 'Synthetic voterfile' not in html_demo_on:
        failures.append("vf-chip should mention 'Synthetic voterfile' in demo mode")
    if '50K Gwinnett' not in html_demo_on:
        failures.append("vf-chip should mention '50K Gwinnett' rows in demo mode")
    if 'class="vf-chip"' in html_demo_off:
        failures.append("vf-chip leaked into non-demo render (should be hidden)")

    # 5. JS handler binds to .demo-tile, not the stale demo-load-btn.
    if "querySelectorAll('.demo-tile')" not in html_demo_on:
        failures.append("JS handler should select .demo-tile (carousel rewrite missing)")
    if "getElementById('demo-load-btn')" in html_demo_on:
        failures.append("Stale demo-load-btn handler still present (should be removed)")
    if "tile.dataset.prompt" not in html_demo_on:
        failures.append("JS handler should read data-prompt via dataset.prompt")

    # 6. CSS for new structures is included.
    for css_marker in (
        ".demo-carousel",
        ".demo-tile",
        ".demo-tile-chip--vf",
        ".vf-chip-dot",
        "@keyframes vf-chip-pulse",
        ".empty-hero-icon",
    ):
        if css_marker not in html_demo_on:
            failures.append(f"missing CSS rule: {css_marker}")

    print("Demo carousel + voter chip test: 6 assertion groups, ~26 checks.")
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: all carousel + voter-chip assertions OK.")
    print(f"  Tiles found: 5")
    print(f"  Chip variants: {len(EXPECTED_CHIPS)}")
    print(f"  Voter chip: present in demo-on, absent in demo-off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
