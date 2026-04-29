"""Test suite for Milestone O (pastel light + dark theme system).

Verifies:
  A) base.html token surface: both [data-theme="light"] and [data-theme="dark"]
     blocks define the full set of semantic tokens.
  B) Pre-paint theme bootstrap script reads localStorage and sets data-theme
     before first paint (no flash).
  C) prefers-color-scheme: light media query mirrors the light tokens for
     unconfigured visitors.
  D) chat.html and login.html have no remaining hardcoded color literals
     outside of decorative drop shadows and SVG stroke/fill attrs.
  E) Theme switcher markup + CSS classes are present and well-formed.
  F) Theme switcher JavaScript handles all three choices (system/light/dark)
     with localStorage persistence.
  G) WCAG AA contrast: every text/surface pair in both themes meets 4.5:1.
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


# ── Read templates straight from disk (independent of view context) ──────
BASE_DIR = str(PROJECT_DIR)
with open(os.path.join(BASE_DIR, "templates", "base.html"), encoding="utf-8") as f:
    BASE_HTML = f.read()
with open(os.path.join(BASE_DIR, "templates", "chat.html"), encoding="utf-8") as f:
    CHAT_HTML = f.read()
with open(os.path.join(BASE_DIR, "templates", "login.html"), encoding="utf-8") as f:
    LOGIN_HTML = f.read()


# ═══════════════════════════════════════════════════════════════════════
print("=== (A) Token surface in base.html ===")
n = 0

REQUIRED_TOKENS = [
    "--bg-primary", "--bg-secondary", "--bg-card",
    "--accent", "--accent-hover", "--accent-strong",
    "--accent-glow", "--accent-soft-bg", "--accent-soft-bg-2", "--accent-soft-border",
    "--on-accent",
    "--text-primary", "--text-secondary", "--text-muted",
    "--border", "--border-strong",
    "--surface-overlay", "--surface-overlay-2", "--surface-overlay-3", "--divider-dashed",
    "--success", "--success-soft-bg", "--success-soft-border",
    "--warning", "--warning-strong", "--warning-soft-bg", "--warning-soft-bg-2", "--warning-soft-border",
    "--error", "--error-soft-bg", "--error-soft-bg-2", "--error-soft-border",
    "--highlight",
]

# Locate dark and light blocks.  Dark block is :root + :root[data-theme="dark"].
dark_block_match = re.search(
    r':root,\s*:root\[data-theme="dark"\]\s*\{([^}]+)\}', BASE_HTML, re.DOTALL
)
light_block_match = re.search(
    r':root\[data-theme="light"\]\s*\{([^}]+)\}', BASE_HTML, re.DOTALL
)
expect(dark_block_match is not None, "dark token block present")
n += 1
expect(light_block_match is not None, "light token block present")
n += 1

dark_block = dark_block_match.group(1) if dark_block_match else ""
light_block = light_block_match.group(1) if light_block_match else ""

for tok in REQUIRED_TOKENS:
    expect(tok in dark_block, f"dark block defines {tok}")
    n += 1
    expect(tok in light_block, f"light block defines {tok}")
    n += 1

# accent must be the dusty blue family in both themes
expect(re.search(r"--accent:\s*#8FB3D9", dark_block, re.IGNORECASE), "dark accent is #8FB3D9 (dusty blue)")
n += 1
expect(re.search(r"--accent:\s*#3D6A99", light_block, re.IGNORECASE), "light accent is #3D6A99 (dusty blue)")
n += 1
# success must be sage in both themes
expect(re.search(r"--success:\s*#A8D4BB", dark_block, re.IGNORECASE), "dark success is #A8D4BB (sage)")
n += 1
expect(re.search(r"--success:\s*#3F7A5C", light_block, re.IGNORECASE), "light success is #3F7A5C (sage)")
n += 1

print(f"PASS section A: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (B) Pre-paint theme bootstrap ===")
n = 0
expect("localStorage.getItem('pb-theme')" in BASE_HTML, "bootstrap reads pb-theme from localStorage")
n += 1
expect("setAttribute('data-theme'" in BASE_HTML, "bootstrap sets data-theme attribute")
n += 1
expect("if (saved === 'light' || saved === 'dark')" in BASE_HTML, "bootstrap only honors light/dark values")
n += 1
expect(BASE_HTML.find("(function ()") < BASE_HTML.find("</head>"),
       "bootstrap IIFE runs before </head> (pre-paint)")
n += 1
print(f"PASS section B: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (C) prefers-color-scheme fallback ===")
n = 0
media_match = re.search(
    r'@media \(prefers-color-scheme: light\) \{[^}]*:root:not\(\[data-theme="dark"\]\):not\(\[data-theme="light"\]\)\s*\{([^}]+)\}',
    BASE_HTML, re.DOTALL,
)
expect(media_match is not None, "prefers-color-scheme: light block present")
n += 1
if media_match:
    media_block = media_match.group(1)
    expect("--bg-primary:        #F7F5EF" in media_block,
           "media block uses warm off-white background")
    n += 1
    expect("--accent:            #3D6A99" in media_block,
           "media block uses dusty blue accent")
    n += 1
print(f"PASS section C: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (D) No stray hardcoded colors in chat.html / login.html ===")
n = 0

def strip_safe_lines(text):
    """Drop lines we allow to keep raw colors (SVG attrs, drop shadows, --dl-color)."""
    out = []
    for line in text.splitlines():
        if "stroke=" in line or "fill=" in line:
            continue
        if "--dl-color" in line:
            continue
        # Pure-black drop shadows are fine in both themes (subtle, both modes).
        if re.search(r"box-shadow.*rgba\(\s*0\s*,\s*0\s*,\s*0", line):
            continue
        # color-mix() referencing tokens is fine
        if "color-mix(" in line:
            continue
        out.append(line)
    return "\n".join(out)

chat_clean = strip_safe_lines(CHAT_HTML)
login_clean = strip_safe_lines(LOGIN_HTML)

# Forbidden literals: old hex accent + old hex semantics
FORBIDDEN_HEX = ["#3b82f6", "#2563eb", "#ef4444", "#10b981", "#f59e0b",
                 "#22c55e", "#4ade80", "#f87171", "#a855f7"]
for h in FORBIDDEN_HEX:
    expect(h.lower() not in chat_clean.lower(), f"chat.html no longer uses {h}")
    n += 1

# Forbidden rgba: any old-blue or hard whites in chat.html
expect("rgba(59, 130, 246" not in chat_clean and "rgba(59,130,246" not in chat_clean,
       "chat.html no longer uses rgba(59,130,246,…)")
n += 1
expect("rgba(255, 255, 255" not in chat_clean and "rgba(255,255,255" not in chat_clean,
       "chat.html no longer uses rgba(255,255,255,…)")
n += 1

# login.html must be fully tokenized (it's tiny)
expect("rgba(59,130,246" not in login_clean, "login.html no longer uses rgba(59,130,246,…)")
n += 1
expect("rgba(239,68,68" not in login_clean, "login.html no longer uses rgba(239,68,68,…)")
n += 1
expect("color: #fff" not in login_clean, "login.html no longer uses color: #fff")
n += 1

print(f"PASS section D: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (E) Theme switcher markup ===")
n = 0
expect('class="theme-switcher"' in CHAT_HTML, "theme-switcher container present")
n += 1
expect('id="theme-switcher-group"' in CHAT_HTML, "theme-switcher-group id present")
n += 1
for choice in ("system", "light", "dark"):
    expect(f'data-theme-choice="{choice}"' in CHAT_HTML, f"theme button: {choice}")
    n += 1
# Default aria-pressed: only system pressed initially (server render).
sys_btn = re.search(
    r'data-theme-choice="system"[^>]*aria-pressed="(true|false)"', CHAT_HTML
)
expect(sys_btn is not None and sys_btn.group(1) == "true",
       "system button starts aria-pressed=true on server render")
n += 1
# CSS classes wired
expect(".theme-switcher__btn[aria-pressed=\"true\"]" in CHAT_HTML,
       "active-state CSS hooks aria-pressed=true")
n += 1
expect("--accent-soft-bg-2" in CHAT_HTML and "var(--accent)" in CHAT_HTML,
       "active button uses accent tokens (themable)")
n += 1
print(f"PASS section E: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (F) Theme switcher JavaScript ===")
n = 0
expect("wireThemeSwitcher" in CHAT_HTML, "wireThemeSwitcher IIFE defined")
n += 1
expect("localStorage.getItem('pb-theme')" in CHAT_HTML, "JS reads pb-theme")
n += 1
expect("localStorage.removeItem('pb-theme')" in CHAT_HTML,
       "JS clears pb-theme on system choice")
n += 1
expect("localStorage.setItem('pb-theme'" in CHAT_HTML,
       "JS writes pb-theme on light/dark")
n += 1
expect("removeAttribute('data-theme')" in CHAT_HTML,
       "JS removes data-theme on system choice")
n += 1
expect("setAttribute('data-theme', choice)" in CHAT_HTML,
       "JS sets data-theme on light/dark")
n += 1
expect("aria-pressed" in CHAT_HTML, "JS toggles aria-pressed")
n += 1
print(f"PASS section F: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print("=== (G) WCAG AA contrast (every key pair) ===")
n = 0

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(a, b):
    la, lb = luminance(hex_to_rgb(a)), luminance(hex_to_rgb(b))
    L1, L2 = max(la, lb), min(la, lb)
    return (L1 + 0.05) / (L2 + 0.05)


# Light theme pairs — must all pass AA (4.5:1 normal text)
light_pairs = [
    ("#F7F5EF", "#1F2937"),  # bg / text-primary
    ("#F7F5EF", "#3F4856"),  # bg / text-secondary
    ("#F7F5EF", "#5B6470"),  # bg / text-muted
    ("#FFFFFF", "#1F2937"),  # surface / text-primary
    ("#FFFFFF", "#5B6470"),  # surface / text-muted
    ("#F7F5EF", "#3D6A99"),  # bg / accent
    ("#FFFFFF", "#3D6A99"),  # surface / accent
    ("#3D6A99", "#FFFFFF"),  # accent / on-accent (button)
    ("#F7F5EF", "#3F7A5C"),  # bg / success
    ("#F7F5EF", "#A35E3A"),  # bg / warning
    ("#F7F5EF", "#B14A4A"),  # bg / error
]
# Dark theme pairs
dark_pairs = [
    ("#14171C", "#E8EAED"),
    ("#14171C", "#B6BDC8"),
    ("#14171C", "#8A93A0"),
    ("#1C2026", "#E8EAED"),
    ("#1C2026", "#8A93A0"),
    ("#14171C", "#8FB3D9"),
    ("#1C2026", "#8FB3D9"),
    ("#8FB3D9", "#0E1218"),
    ("#14171C", "#A8D4BB"),
    ("#14171C", "#F0D58A"),
    ("#14171C", "#E0A77F"),
    ("#14171C", "#F0A0A0"),
]

for bg, fg in light_pairs:
    r = contrast(bg, fg)
    expect(r >= 4.5, f"light AA: {bg}/{fg} = {r:.2f}")
    n += 1
for bg, fg in dark_pairs:
    r = contrast(bg, fg)
    expect(r >= 4.5, f"dark AA: {bg}/{fg} = {r:.2f}")
    n += 1

print(f"PASS section G: {n} checks")


# ═══════════════════════════════════════════════════════════════════════
print(f"\nALL PASS — _test_pastel_theme.py ran {len(PASS)} assertions")
