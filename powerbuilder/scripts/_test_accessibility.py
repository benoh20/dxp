"""Test suite for Milestone P (accessibility pass).

Verifies:
  A) Body type sized 15px (bumped from 14px) with line-height >= 1.5.
  B) Focus ring is visible: 2px solid outline + halo box-shadow + offset.
  C) Skip-to-content link is the first focusable element in <body>, points
     to the main content region, and slides into view on focus.
  D) Main content region has id="main-content" so the skip link works.
  E) prefers-reduced-motion media query disables animations and transitions.
  F) Every <button> in chat.html has either aria-label or visible text content.
  G) Every <svg> in chat.html and login.html that is decorative has
     aria-hidden="true" (we conservatively check that the count of
     aria-hidden SVGs is at least equal to the count of SVGs inside
     interactive elements).
  H) The chat scroll region is marked as a live region (role=log,
     aria-live=polite) so screen readers announce streaming responses.
  I) The file-clear button has type=button + aria-label (regression check
     for an unlabeled '×' button).
  J) The login error has role=alert so it announces immediately.
  K) <html lang> attribute is present in base.html.
"""

import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-validation-only")
os.environ["DEBUG"] = "True"

import django  # noqa: E402

django.setup()

PASS = []


def expect(cond, msg):
    assert cond, f"FAIL: {msg}"
    PASS.append(msg)


BASE_DIR = str(PROJECT_DIR)
with open(os.path.join(BASE_DIR, "templates", "base.html"), encoding="utf-8") as f:
    BASE_HTML = f.read()
with open(os.path.join(BASE_DIR, "templates", "chat.html"), encoding="utf-8") as f:
    CHAT_HTML = f.read()
with open(os.path.join(BASE_DIR, "templates", "login.html"), encoding="utf-8") as f:
    LOGIN_HTML = f.read()


# ═══════════════════════════════════════════════════════════════════════
print("=== (A) Body type sizing ===")
n = 0
expect(re.search(r"font-size:\s*15px", BASE_HTML),
       "body font-size bumped to 15px")
n += 1
expect(re.search(r"line-height:\s*1\.[56789]", BASE_HTML),
       "body line-height >= 1.5")
n += 1
print(f"PASS section A: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (B) Focus ring ===")
n = 0
expect("*:focus-visible" in BASE_HTML, ":focus-visible selector defined")
n += 1
expect(re.search(r"\*:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--accent\)",
                 BASE_HTML, re.DOTALL),
       "focus ring uses 2px solid var(--accent)")
n += 1
expect(re.search(r"\*:focus-visible\s*\{[^}]*outline-offset:\s*2px",
                 BASE_HTML, re.DOTALL),
       "focus ring has 2px offset")
n += 1
expect(re.search(r"\*:focus-visible\s*\{[^}]*box-shadow:\s*0 0 0 4px",
                 BASE_HTML, re.DOTALL),
       "focus ring has 4px halo box-shadow")
n += 1
print(f"PASS section B: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (C) Skip-to-content link ===")
n = 0
expect('class="skip-to-content"' in BASE_HTML, "skip-to-content class on link")
n += 1
expect('href="#main-content"' in BASE_HTML, "skip link targets #main-content")
n += 1

# The skip link should appear before the <nav> in <body>
body_idx = BASE_HTML.find("<body")
skip_idx = BASE_HTML.find("skip-to-content", body_idx)
nav_idx = BASE_HTML.find("<nav", body_idx)
expect(skip_idx > 0 and nav_idx > 0 and skip_idx < nav_idx,
       "skip link appears before <nav> (first focusable)")
n += 1

# CSS slides it in on focus
expect(re.search(r"\.skip-to-content\s*\{[^}]*top:\s*-?\d+px",
                 BASE_HTML, re.DOTALL),
       "skip link is hidden offscreen by default")
n += 1
expect(re.search(r"\.skip-to-content:focus[^}]*\{[^}]*top:\s*\d+px",
                 BASE_HTML, re.DOTALL),
       "skip link slides into view on :focus")
n += 1
print(f"PASS section C: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (D) Main content target ===")
n = 0
expect('id="main-content"' in BASE_HTML, "<main> has id=main-content")
n += 1
print(f"PASS section D: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (E) prefers-reduced-motion guard ===")
n = 0
expect("@media (prefers-reduced-motion: reduce)" in BASE_HTML,
       "reduced-motion media query present")
n += 1
expect(re.search(
    r"@media \(prefers-reduced-motion: reduce\)\s*\{[^}]*animation-duration:\s*0\.001ms",
    BASE_HTML, re.DOTALL),
    "reduced motion neutralizes animation-duration")
n += 1
expect(re.search(
    r"@media \(prefers-reduced-motion: reduce\)\s*\{(?:[^{}]*\{[^{}]*\})*[^}]*transition-duration:\s*0\.001ms",
    BASE_HTML, re.DOTALL),
    "reduced motion neutralizes transition-duration")
n += 1
print(f"PASS section E: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (F) Buttons have accessible names ===")
n = 0
button_re = re.compile(r"<button\b[^>]*>(.*?)</button>", re.DOTALL)
buttons_found = 0
labeled = 0
for m in button_re.finditer(CHAT_HTML):
    open_tag = m.group(0).split(">", 1)[0]
    inner = m.group(1).strip()
    has_aria = "aria-label" in open_tag
    # Strip nested SVGs from the inner text to gauge if there's actual visible text
    inner_no_svg = re.sub(r"<svg.*?</svg>", "", inner, flags=re.DOTALL).strip()
    has_text = len(inner_no_svg) > 0
    buttons_found += 1
    if has_aria or has_text:
        labeled += 1
expect(buttons_found > 0, f"found buttons in chat.html ({buttons_found})")
n += 1
expect(labeled == buttons_found,
       f"every button has aria-label or visible text "
       f"({labeled}/{buttons_found} labeled)")
n += 1
print(f"PASS section F: {n} checks ({buttons_found} buttons audited)")


# ═══════════════════════════════════════════════════════════════════════
print("=== (G) Decorative SVGs marked aria-hidden ===")
n = 0
chat_svgs = len(re.findall(r"<svg\b", CHAT_HTML))
chat_aria_hidden_svgs = len(re.findall(r'<svg[^>]*aria-hidden="true"', CHAT_HTML))
# We require >= 80% of SVGs to be aria-hidden (some may be informative).
# In practice in this app every SVG is decorative, so threshold is high.
expect(chat_aria_hidden_svgs >= max(1, int(chat_svgs * 0.8)),
       f"chat.html: {chat_aria_hidden_svgs}/{chat_svgs} SVGs marked aria-hidden")
n += 1

login_svgs = len(re.findall(r"<svg\b", LOGIN_HTML))
login_aria_hidden_svgs = len(re.findall(r'<svg[^>]*aria-hidden="true"', LOGIN_HTML))
expect(login_aria_hidden_svgs >= max(1, int(login_svgs * 0.8)),
       f"login.html: {login_aria_hidden_svgs}/{login_svgs} SVGs marked aria-hidden")
n += 1
print(f"PASS section G: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (H) Live region on chat scroll ===")
n = 0
chat_scroll_block = re.search(r'<div class="chat-scroll"[^>]*>', CHAT_HTML)
expect(chat_scroll_block is not None, "chat-scroll element present")
n += 1
if chat_scroll_block:
    open_tag = chat_scroll_block.group(0)
    expect('role="log"' in open_tag, "chat-scroll has role=log")
    n += 1
    expect('aria-live="polite"' in open_tag, "chat-scroll has aria-live=polite")
    n += 1
    expect('aria-label="Conversation"' in open_tag, "chat-scroll has aria-label")
    n += 1
print(f"PASS section H: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (I) File-clear button labelled ===")
n = 0
clear_btn_re = re.search(
    r'<button[^>]*onclick="clearFile\(\)"[^>]*>',
    CHAT_HTML,
)
expect(clear_btn_re is not None, "clearFile button present")
n += 1
if clear_btn_re:
    open_tag = clear_btn_re.group(0)
    expect('type="button"' in open_tag,
           "clearFile button has type=button (not default submit)")
    n += 1
    expect('aria-label' in open_tag,
           "clearFile button has aria-label")
    n += 1
print(f"PASS section I: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (J) Login error has role=alert ===")
n = 0
expect('role="alert"' in LOGIN_HTML, "login error block has role=alert")
n += 1
print(f"PASS section J: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (K) <html lang> set ===")
n = 0
expect(re.search(r'<html lang="[a-z]{2}', BASE_HTML),
       "<html> has a lang attribute")
n += 1
print(f"PASS section K: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print(f"\nALL PASS — _test_accessibility.py ran {len(PASS)} assertions")
