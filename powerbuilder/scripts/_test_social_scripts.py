"""
Milestone H tests: research-backed social media script pack.

Covers:
  1. messaging.py exposes the three new format keys with section markers,
     labels, descriptions, and template-file entries
  2. FORMAT_DESCRIPTIONS for each platform variant cites the underlying
     research (Wesleyan 2024, TFC 2024, Bryan/Walton/Rogers/Dweck 2011,
     Chmel et al. 2024)
  3. check_social_format() flags long output and flat openers
  4. check_social_format() leaves well-formed output alone
  5. _strip_leading_direction() handles bracketed timing cues
  6. Prompt assembly includes all eight section markers
  7. demo_tiles.py exposes the new 'social' chip kind and the
     'social-pack-ga07-youth' tile renders through get_demo_tiles()
  8. chat.html ships the .demo-tile-chip--social CSS rule
"""
import os
import sys
from pathlib import Path

# Make the Django app importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")

import django  # noqa: E402

django.setup()

from chat.agents import messaging  # noqa: E402
from chat.agents.messaging import (  # noqa: E402
    FORMAT_DESCRIPTIONS,
    FORMAT_LABELS,
    SECTION_MARKERS,
    SOCIAL_LENGTH_LIMITS,
    TEMPLATE_FILES,
    _strip_leading_direction,
    check_social_format,
)
from chat.demo_tiles import CHIP_KINDS, DEMO_TILES, get_demo_tiles  # noqa: E402

assertions = 0


def assert_(cond, msg):
    global assertions
    assert cond, msg
    assertions += 1


# ---------------------------------------------------------------------------
# 1. messaging.py exposes all three new keys
# ---------------------------------------------------------------------------
section = 0
for key in ("meta_post", "youtube_script", "tiktok_script"):
    assert_(key in SECTION_MARKERS, f"{key} missing from SECTION_MARKERS")
    assert_(key in FORMAT_LABELS, f"{key} missing from FORMAT_LABELS")
    assert_(key in FORMAT_DESCRIPTIONS, f"{key} missing from FORMAT_DESCRIPTIONS")
    assert_(key in TEMPLATE_FILES, f"{key} missing from TEMPLATE_FILES")
    section += 1
assert_(SECTION_MARKERS["meta_post"] == "===META_POST===", "meta_post marker wrong")
assert_(SECTION_MARKERS["youtube_script"] == "===YOUTUBE_SCRIPT===", "youtube marker wrong")
assert_(SECTION_MARKERS["tiktok_script"] == "===TIKTOK_SCRIPT===", "tiktok marker wrong")
assert_("Mobilization" in FORMAT_LABELS["meta_post"], "meta label missing kind")
assert_("Persuasion" in FORMAT_LABELS["youtube_script"], "youtube label missing kind")
assert_("Attention" in FORMAT_LABELS["tiktok_script"], "tiktok label missing kind")
print(f"PASS section 1 (registration): {section} keys, 6 metadata checks")

# ---------------------------------------------------------------------------
# 2. Citations live in the format descriptions (so the LLM sees the rationale)
# ---------------------------------------------------------------------------
checks = [
    ("meta_post", "Wesleyan", "Meta cites Wesleyan"),
    ("meta_post", "TFC 2024", "Meta cites TFC mobilization data"),
    ("meta_post", "Bryan", "Meta cites identity-as-noun PNAS 2011"),
    ("youtube_script", "Wesleyan", "YouTube cites Wesleyan"),
    ("youtube_script", "persuasion", "YouTube describes persuasion role (case-insensitive)"),
    ("tiktok_script", "Chmel", "TikTok cites Chmel et al. 2024"),
    ("tiktok_script", "lifestyle", "TikTok references lifestyle framing"),
]
for key, needle, label in checks:
    text = FORMAT_DESCRIPTIONS[key].lower()
    assert_(needle.lower() in text, f"{label}: '{needle}' missing from {key} description")
print(f"PASS section 2 (research citations in prompts): {len(checks)} checks")

# ---------------------------------------------------------------------------
# 3. Length warnings fire correctly
# ---------------------------------------------------------------------------
long_tiktok = "X" * (SOCIAL_LENGTH_LIMITS["tiktok_script"] + 200)
warns = check_social_format({"tiktok_script": long_tiktok})
assert_("tiktok_script" in warns, "long tiktok did not warn")
assert_(any("runs" in w for w in warns["tiktok_script"]), "missing length warning text")

long_meta = "X" * (SOCIAL_LENGTH_LIMITS["meta_post"] + 50)
warns = check_social_format({"meta_post": long_meta})
assert_("meta_post" in warns, "long meta did not warn")

long_yt = "X" * (SOCIAL_LENGTH_LIMITS["youtube_script"] + 100)
warns = check_social_format({"youtube_script": long_yt})
assert_("youtube_script" in warns, "long youtube did not warn")
print("PASS section 3 (length warnings): 3 checks")

# ---------------------------------------------------------------------------
# 4. Hook warnings on flat openers
# ---------------------------------------------------------------------------
flat_examples = [
    "Hello everyone, my name is Maria",
    "Hi there, I'm a longtime resident",
    "In this video we will explain",
    "Welcome to our channel",
    "Thanks for watching",
]
for body in flat_examples:
    warns = check_social_format({"tiktok_script": body})
    assert_("tiktok_script" in warns, f"flat opener missed: {body!r}")
    assert_(
        any("flat intro" in w for w in warns["tiktok_script"]),
        f"flat-opener message missing: {body!r}",
    )

# Bracketed direction should be stripped before checking
warns = check_social_format(
    {"tiktok_script": "[HOOK 0 to 1.5s] Hello everyone, my name is foo"}
)
assert_("tiktok_script" in warns, "flat opener after [direction] missed")

# Curiosity hooks should pass clean
good_examples = [
    "[HOOK] What if your vote in Gwinnett actually flipped this seat?",
    "Three numbers explain GA-07. The first one will surprise you.",
    "[0:00] Cost of rent in Lawrenceville went up 19% since 2020.",
]
for body in good_examples:
    warns = check_social_format({"tiktok_script": body})
    assert_(
        "tiktok_script" not in warns,
        f"good hook flagged incorrectly: {body!r} \u2192 {warns}",
    )

# YouTube hook check fires too
warns = check_social_format({"youtube_script": "Hi there, I'm a candidate"})
assert_("youtube_script" in warns, "youtube flat opener missed")
print(f"PASS section 4 (hook warnings): {len(flat_examples) + len(good_examples) + 2} checks")

# ---------------------------------------------------------------------------
# 5. _strip_leading_direction handles edge cases
# ---------------------------------------------------------------------------
cases = [
    ("[HOOK] Body", "Body"),
    ("  [0:00 to 0:05]  Body", "Body"),
    ("Body without direction", "Body without direction"),
    ("[unclosed Body", "[unclosed Body"),
    ("", ""),
]
for inp, expected in cases:
    out = _strip_leading_direction(inp)
    assert_(out == expected, f"strip mismatch: {inp!r} \u2192 {out!r}, expected {expected!r}")
print(f"PASS section 5 (direction stripping): {len(cases)} checks")

# ---------------------------------------------------------------------------
# 6. Empty-section short circuit + non-social keys ignored
# ---------------------------------------------------------------------------
warns = check_social_format({})
assert_(warns == {}, "empty input should yield no warnings")
warns = check_social_format({"tiktok_script": ""})
assert_(warns == {}, "empty tiktok content should yield no warnings")
warns = check_social_format({"canvassing_script": "X" * 10000})
assert_(warns == {}, "non-social keys must be ignored by the social checker")
warns = check_social_format({"meta_post": "Be a Gwinnett voter. Polls open Tuesday. [LINK]"})
assert_(warns == {}, f"clean meta post flagged: {warns}")
print("PASS section 6 (defensive defaults): 4 checks")

# ---------------------------------------------------------------------------
# 7. Demo tile config exposes the social tile + chip kind
# ---------------------------------------------------------------------------
assert_("social" in CHIP_KINDS, "social chip kind missing from CHIP_KINDS")
ids = {t["id"] for t in DEMO_TILES}
assert_("social-pack-ga07-youth" in ids, "social-pack-ga07-youth tile missing from DEMO_TILES")
tiles = get_demo_tiles()
out_ids = [t["id"] for t in tiles]
assert_("social-pack-ga07-youth" in out_ids, "social tile dropped by get_demo_tiles()")
social_tile = next(t for t in tiles if t["id"] == "social-pack-ga07-youth")
assert_(social_tile["chip_kind"] == "social", "social tile chip_kind wrong")
assert_("Social pack" in social_tile["chip"], "social tile chip label wrong")
prompt_lower = social_tile["prompt"].lower()
for needle in ("meta", "youtube", "tiktok"):
    assert_(needle in prompt_lower, f"social tile prompt missing platform mention: {needle}")
print("PASS section 7 (demo tile wiring): 7 checks")

# ---------------------------------------------------------------------------
# 8. chat.html CSS for the new chip color
# ---------------------------------------------------------------------------
chat_html = (ROOT / "templates" / "chat.html").read_text()
assert_(
    ".demo-tile-chip--social" in chat_html,
    "missing .demo-tile-chip--social CSS in chat.html",
)
# Milestone O: social chip is now tokenized to --success-soft-* so it tracks
# the active theme (sage in light + dark). Accept either the legacy teal rgba
# or the new token reference.
assert_(
    "20, 184, 166" in chat_html
    or (".demo-tile-chip--social" in chat_html and "--success-soft" in chat_html),
    "social chip should use a distinct success/teal color or token",
)
print("PASS section 8 (CSS for social chip): 2 checks")

# ---------------------------------------------------------------------------
# 9. Prompt template lists all eight markers
# ---------------------------------------------------------------------------
src = (ROOT / "chat" / "agents" / "messaging.py").read_text()
for marker in SECTION_MARKERS.values():
    assert_(
        marker in src or marker.replace("===", "") in src,
        f"section marker {marker!r} not referenced in messaging.py prompt",
    )
assert_("all eight sections" in src.lower(), "prompt copy not updated to 'all eight sections'")
assert_("EIGHT MESSAGING SECTIONS" in src, "language directive not updated to eight sections")
assert_("/8 messaging formats" in src, "logger summary not updated to /8")
print(f"PASS section 9 (prompt assembly): {len(SECTION_MARKERS) + 3} checks")

print()
print(f"OK Milestone H suite: {assertions} assertions")
