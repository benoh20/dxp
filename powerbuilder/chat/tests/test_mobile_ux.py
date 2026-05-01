# powerbuilder/chat/tests/test_mobile_ux.py
"""
Milestone R.1: regression tests for the mobile UX wiring in chat.html.

These are static-file checks (no headless browser, no Django runtime).
They guard the four behaviors documented on the fellowship-pitch slides:

    1. --tap-min CSS variable exists and is set to 44px (WCAG 2.5.5)
    2. env(safe-area-inset-bottom) padding lives on the input bar
    3. The mobile drawer pattern is implemented at a 768 px breakpoint
       with translateX(-100%) off-canvas + transform-on-checked
    4. The drawer accessibility hook (scroll lock + focus trap + ESC)
       is present in the inline JS

Why static checks: chat.html keeps all CSS and JS inline as a single
template, so the cheapest, most stable signal is "is the source of
truth still saying the right thing?". A future refactor that moves
this into a stylesheet would break these tests and that is the point:
they should be re-pointed at the new file, not silently removed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

CHAT_TEMPLATE = (
    Path(__file__).resolve().parent.parent.parent / "templates" / "chat.html"
)


@pytest.fixture(scope="module")
def chat_html() -> str:
    assert CHAT_TEMPLATE.exists(), f"missing template: {CHAT_TEMPLATE}"
    return CHAT_TEMPLATE.read_text(encoding="utf-8")


# ── 1. --tap-min token ────────────────────────────────────────────────────────


def test_tap_min_token_defined(chat_html):
    """--tap-min: 44px is declared exactly once at :root."""
    assert re.search(r"--tap-min:\s*44px\s*;", chat_html), (
        "expected --tap-min: 44px; declared in :root"
    )


def test_tap_min_used_on_input_icon_buttons(chat_html):
    """
    The send/icon buttons opt into the tap-target floor via the var,
    not via hardcoded sizing.
    """
    # Capture the .input-icon-btn rule and assert it references the var.
    block = re.search(
        r"\.input-icon-btn\s*\{[^}]*\}", chat_html, re.DOTALL
    )
    assert block, ".input-icon-btn rule must exist"
    body = block.group(0)
    assert "min-width: var(--tap-min)" in body
    assert "min-height: var(--tap-min)" in body


def test_tap_min_used_on_hamburger(chat_html):
    """The mobile hamburger respects the same tap-target floor."""
    block = re.search(
        r"\.sidebar-hamburger\s*\{[^}]*\}", chat_html, re.DOTALL
    )
    assert block, ".sidebar-hamburger rule must exist"
    body = block.group(0)
    assert "min-width: var(--tap-min)" in body
    assert "min-height: var(--tap-min)" in body


# ── 2. safe-area-inset-bottom ─────────────────────────────────────────────────


def test_safe_bottom_token_defined(chat_html):
    """--safe-bottom resolves env(safe-area-inset-bottom) with a 0 fallback."""
    assert re.search(
        r"--safe-bottom:\s*env\(\s*safe-area-inset-bottom\s*,\s*0px\s*\)",
        chat_html,
    ), "expected --safe-bottom: env(safe-area-inset-bottom, 0px)"


def test_input_bar_uses_safe_bottom(chat_html):
    """The input bar pads its bottom by the safe-area inset."""
    block = re.search(r"\.input-bar\s*\{[^}]*\}", chat_html, re.DOTALL)
    assert block, ".input-bar rule must exist"
    body = block.group(0)
    assert "var(--safe-bottom)" in body, (
        "input bar bottom padding should add var(--safe-bottom)"
    )


# ── 3. drawer pattern at 768 px ───────────────────────────────────────────────


def test_breakpoint_at_768(chat_html):
    """One @media (max-width: 768px) block defines the mobile layout."""
    assert "@media (max-width: 768px)" in chat_html


def test_drawer_is_offcanvas_translatex(chat_html):
    """
    The closed drawer is translateX(-100%) and the open drawer is
    translateX(0). That is the entire point of the off-canvas pattern.
    """
    assert "transform: translateX(-100%)" in chat_html
    assert re.search(
        r"#sidebar-toggle:checked\s*~\s*\.chat-root\s*\.sidebar\s*\{\s*"
        r"transform:\s*translateX\(0\)",
        chat_html,
    ), "expected :checked sibling rule to translateX(0)"


# ── 4. drawer accessibility hook ──────────────────────────────────────────────


def test_drawer_open_class_locks_body(chat_html):
    """body.drawer-open freezes scroll (overflow:hidden + position:fixed)."""
    block = re.search(
        r"body\.drawer-open\s*\{[^}]*\}", chat_html, re.DOTALL
    )
    assert block, "body.drawer-open rule must exist"
    body = block.group(0)
    assert "overflow: hidden" in body
    assert "position: fixed" in body  # iOS rubber-band guard


def test_drawer_hook_listens_for_escape(chat_html):
    """The drawer JS hook handles Escape to close the drawer."""
    # Check that the wireMobileDrawer hook exists and references Escape.
    assert "wireMobileDrawer" in chat_html
    # The hook adds a keydown listener and acts on e.key === 'Escape'.
    assert re.search(r"e\.key\s*===\s*['\"]Escape['\"]", chat_html), (
        "drawer hook should branch on Escape"
    )


def test_drawer_hook_traps_tab(chat_html):
    """The drawer JS hook constrains Tab to focusables inside the drawer."""
    assert re.search(r"e\.key\s*===\s*['\"]Tab['\"]", chat_html), (
        "drawer hook should branch on Tab to implement the focus trap"
    )
    assert "focusableInsideDrawer" in chat_html


def test_drawer_hook_toggles_body_class(chat_html):
    """The hook adds/removes the body.drawer-open class on toggle change."""
    assert "classList.add('drawer-open')" in chat_html
    assert "classList.remove('drawer-open')" in chat_html


def test_drawer_hook_releases_lock_on_resize(chat_html):
    """
    Growing the viewport past 768 px while the drawer is open releases
    the body lock so desktop layout takes over cleanly.
    """
    assert re.search(
        r"matchMedia\(\s*['\"]\(max-width:\s*768px\)['\"]\s*\)"
        r"\.addEventListener\(\s*['\"]change['\"]",
        chat_html,
    ), "expected a matchMedia listener that releases the lock at desktop width"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
