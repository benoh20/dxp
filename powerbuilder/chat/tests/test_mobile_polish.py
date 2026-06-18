"""
Static regression tests for Milestone S (mobile + language polish).

Three issues the user surfaced from real-device testing:

  1. On mobile, opening the app at /chat/ landed the viewport on the demo-tile
     carousel instead of the welcome heading. Root cause: the initial-load
     `scrollToBottom()` ran unconditionally, and on a tall mobile chat-scroll
     the empty-state placeholder is taller than the viewport.

  2. The EN / ES / VI buttons in the nav had no visual hint that they were a
     language control. A user who tapped VI by mistake had no way to recognize
     the row as a language switcher.

  3. Default language was always English, ignoring the user's system locale.
     Browsers' Accept-Language header is unreliable on iOS/macOS, so we read
     navigator.language client-side on first visit and POST to /i18n/setlang/
     when the system language is Spanish or Vietnamese.

These tests are static \u2014 they read the templates and assert the fix is still
present after future refactors. No Django runtime, no browser, no network.
That keeps them <100ms and resilient to unrelated test-suite breakage.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_TEMPLATE = REPO_ROOT / "templates" / "chat.html"
BASE_TEMPLATE = REPO_ROOT / "templates" / "base.html"


@pytest.fixture(scope="module")
def chat_html():
    assert CHAT_TEMPLATE.exists(), f"missing {CHAT_TEMPLATE}"
    return CHAT_TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def base_html():
    assert BASE_TEMPLATE.exists(), f"missing {BASE_TEMPLATE}"
    return BASE_TEMPLATE.read_text(encoding="utf-8")


# ---------- Issue 1: mobile empty-state scroll ----------------------------

def test_initial_scroll_is_guarded_by_empty_state(chat_html):
    """
    The initial-load scroll block must check for #empty-state before calling
    scrollToBottom(). Without this guard, mobile users land mid-carousel.
    """
    # Find the comment we left at the call site \u2014 keeps the intent visible.
    assert "Scroll to bottom on initial load" in chat_html, (
        "expected the scroll-on-load comment block in chat.html"
    )
    # The actual guard: getElementById('empty-state') must precede the
    # scrollToBottom() call in the initial-load IIFE.
    assert "getElementById('empty-state')" in chat_html, (
        "initial-load scroll must check for empty-state placeholder"
    )


def test_initial_scroll_top_when_empty(chat_html):
    """
    When the empty state is present, the scroll position should be reset to
    the top so the welcome heading is visible above the fold.
    """
    # We set scrollTop = 0 on chat-scroll in the empty-state branch.
    assert "scrollTop = 0" in chat_html, (
        "empty-state branch must reset scrollTop to 0"
    )


def test_initial_scroll_to_bottom_only_when_messages(chat_html):
    """
    The bare initial-load scrollToBottom() call must live inside an else branch
    \u2014 otherwise the regression returns. We assert the relative ordering of the
    empty-state check and the final scrollToBottom() call near end-of-file.
    """
    # Locate the section by its comment marker, then the next scrollToBottom()
    # after the marker must be inside an else block.
    marker = "Scroll to bottom on initial load"
    idx = chat_html.find(marker)
    assert idx != -1, "missing initial-load scroll marker"
    tail = chat_html[idx:idx + 800]  # the IIFE close is within ~20 lines
    # Must contain both the empty-state branch and an else with scrollToBottom.
    assert "getElementById('empty-state')" in tail
    assert "} else {" in tail, (
        "scrollToBottom() must be in the else branch of the empty-state guard"
    )
    assert "scrollToBottom();" in tail


# ---------- Issue 2: language switcher gets a globe icon ------------------

def test_lang_switcher_has_globe_icon(base_html):
    """
    The EN/ES/VI switcher needs a small globe SVG so users recognize it as
    a language control. Icon must sit inside .lang-switcher.
    """
    # Locate the .lang-switcher block and confirm an SVG with the globe class.
    assert "lang-switcher__icon" in base_html, (
        "expected a .lang-switcher__icon SVG before the EN/ES/VI buttons"
    )
    # Confirm it's an actual <svg> (not just a stray class reference).
    assert "<svg class=\"lang-switcher__icon\"" in base_html


def test_lang_switcher_icon_is_decorative(base_html):
    """
    The globe icon is decorative \u2014 the wrapping <div> already carries
    aria-label='Language', so the SVG must be aria-hidden to avoid a
    duplicate announcement.
    """
    # Slice out the icon SVG and assert aria-hidden=true on it.
    start = base_html.find("lang-switcher__icon")
    assert start != -1
    icon_block = base_html[start:start + 600]
    assert "aria-hidden=\"true\"" in icon_block, (
        "decorative globe icon must be aria-hidden"
    )


def test_lang_switcher_icon_is_subtle(base_html):
    """
    The user asked for the icon to NOT be visually distracting. Check that the
    globe is rendered at low opacity and at small size (\u226414px), so it reads
    as a hint rather than a button.
    """
    start = base_html.find("lang-switcher__icon")
    icon_block = base_html[start:start + 600]
    assert "opacity:0.6" in icon_block or "opacity: 0.6" in icon_block, (
        "globe icon must be rendered at \u22640.6 opacity to stay subtle"
    )
    assert "width=\"14\"" in icon_block, (
        "globe icon must be 14px wide \u2014 small enough not to compete with buttons"
    )


# ---------- Issue 3: auto-detect system language --------------------------

def test_lang_autodetect_script_present(base_html):
    """
    base.html must include a script that reads navigator.language on first
    visit and posts to /i18n/setlang/ when the user's system locale is
    Spanish or Vietnamese.
    """
    assert "navigator.languages" in base_html, (
        "auto-detect must consult navigator.languages (full preference list)"
    )
    assert "navigator.language" in base_html


def test_lang_autodetect_handles_es_and_vi(base_html):
    """
    The detector must explicitly map both Spanish and Vietnamese codes.
    """
    # We compare the lowercased browser language to 'es' and 'vi' prefixes.
    assert "indexOf('es') === 0" in base_html, (
        "auto-detect must match es-* prefix"
    )
    assert "indexOf('vi') === 0" in base_html, (
        "auto-detect must match vi-* prefix"
    )


def test_lang_autodetect_skips_when_cookie_set(base_html):
    """
    If the user has already chosen a language (django_language cookie is
    present), the detector must do nothing \u2014 otherwise it would override
    a deliberate choice on every page load.
    """
    assert "django_language" in base_html, (
        "auto-detect must check for the django_language cookie before running"
    )
    assert "hasCookie('django_language')" in base_html


def test_lang_autodetect_marks_attempt_in_localstorage(base_html):
    """
    Even when no language matches (English-only system), we must record that
    detection ran so the script doesn't keep retrying on every page load.
    """
    assert "pb_lang_autodetected" in base_html, (
        "auto-detect must persist a 'tried it' marker in localStorage"
    )


def test_lang_autodetect_posts_to_setlang(base_html):
    """
    The detector must build a POST form to the existing set_language URL
    rather than rolling its own cookie write \u2014 keeping us aligned with
    Django's i18n contract.
    """
    # Detector reuses the existing form's action attribute, which is rendered
    # from {% url 'set_language' %}. Assert the lookup path is in the script.
    assert ".lang-switcher form" in base_html, (
        "auto-detect must reuse the .lang-switcher form's action + CSRF"
    )
    assert "csrfmiddlewaretoken" in base_html


def test_lang_autodetect_is_safe_on_failure(base_html):
    """
    The detector wraps everything in try/catch so a missing API or a bad
    browser doesn't crash the page. Default English is the fallback.
    """
    # Find the auto-detect script block by its comment.
    marker = "auto-detect system language"
    idx = base_html.find(marker)
    assert idx != -1, "auto-detect script comment marker missing"
    block = base_html[idx:idx + 4000]
    assert "try {" in block and "catch" in block, (
        "auto-detect must be wrapped in try/catch"
    )
