#!/usr/bin/env python
"""
Milestone G test suite: plan-panel h1 grouping + demo tile config.

Covers:
  1. _group_sections_by_h1() — h1 ownership, orphan handling, empty edge,
                                no-h1 fallback, multi-h1 chains
  2. plan_outline() returns a 'groups' field alongside 'sections'
  3. partials/message.html renders <details> groups with caret + open
  4. chat.html ships .plan-panel-group CSS rules
  5. demo_tiles.get_demo_tiles() — happy path, defensive filtering of
                                    bad chip_kind / missing fields / dup ids
  6. chat.html template no longer hardcodes tile copy and instead
                                    iterates {% for tile in demo_tiles %}
  7. chat_view() exposes demo_tiles in the response context

86+ assertions across 7 sections, PASS line per section.
"""
from __future__ import annotations

import html
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
django.setup()

from django.template.loader import render_to_string
from django.test import RequestFactory
from importlib import import_module

from chat import demo_tiles
from chat import views as chat_views
from chat.render_helpers import _group_sections_by_h1, plan_outline


# ---------------------------------------------------------------------------
# 1. _group_sections_by_h1() — pure logic
# ---------------------------------------------------------------------------
def test_group_sections_by_h1():
    n = 0

    # Empty input: empty groups, never crashes
    assert _group_sections_by_h1([]) == []
    n += 1

    # Single h1, two children
    sections = [
        {"level": 1, "text": "Plan",  "slug": "plan"},
        {"level": 2, "text": "Field", "slug": "field"},
        {"level": 2, "text": "Comms", "slug": "comms"},
    ]
    groups = _group_sections_by_h1(sections)
    assert len(groups) == 1
    assert groups[0]["h1"]["text"] == "Plan"
    assert [c["text"] for c in groups[0]["children"]] == ["Field", "Comms"]
    n += 3

    # Multi-h1: each owns its trailing siblings only
    sections = [
        {"level": 1, "text": "A", "slug": "a"},
        {"level": 2, "text": "A1", "slug": "a1"},
        {"level": 1, "text": "B", "slug": "b"},
        {"level": 3, "text": "B1", "slug": "b1"},
        {"level": 2, "text": "B2", "slug": "b2"},
    ]
    groups = _group_sections_by_h1(sections)
    assert [g["h1"]["text"] for g in groups] == ["A", "B"]
    assert [c["text"] for c in groups[0]["children"]] == ["A1"]
    assert [c["text"] for c in groups[1]["children"]] == ["B1", "B2"]
    n += 3

    # Orphan top: sub-headings before any h1 land in synthetic 'h1=None' group
    sections = [
        {"level": 2, "text": "intro-a", "slug": "intro-a"},
        {"level": 2, "text": "intro-b", "slug": "intro-b"},
        {"level": 1, "text": "Real",   "slug": "real"},
        {"level": 2, "text": "child",  "slug": "child"},
    ]
    groups = _group_sections_by_h1(sections)
    assert len(groups) == 2
    assert groups[0]["h1"] is None
    assert [c["text"] for c in groups[0]["children"]] == ["intro-a", "intro-b"]
    assert groups[1]["h1"]["text"] == "Real"
    assert [c["text"] for c in groups[1]["children"]] == ["child"]
    n += 5

    # Zero h1s anywhere: single orphan group with everything
    sections = [
        {"level": 2, "text": "x", "slug": "x"},
        {"level": 3, "text": "y", "slug": "y"},
    ]
    groups = _group_sections_by_h1(sections)
    assert len(groups) == 1
    assert groups[0]["h1"] is None
    assert [c["text"] for c in groups[0]["children"]] == ["x", "y"]
    n += 3

    # Only h1s, no children: each group has empty children list
    sections = [
        {"level": 1, "text": "A", "slug": "a"},
        {"level": 1, "text": "B", "slug": "b"},
    ]
    groups = _group_sections_by_h1(sections)
    assert len(groups) == 2
    assert all(g["children"] == [] for g in groups)
    n += 2

    print(f"  group_sections_by_h1: {n} assertions passed")


# ---------------------------------------------------------------------------
# 2. plan_outline() returns the new 'groups' field
# ---------------------------------------------------------------------------
def test_plan_outline_groups_field():
    n = 0
    answer = (
        "# Plan\n"
        "## Field\n"
        "## Comms\n"
        "# Budget\n"
        "### Paid media\n"
    )
    out = plan_outline(answer, active_agents=["win_number", "precincts", "messaging"])
    # Existing fields still present (no regression)
    assert "sections" in out and len(out["sections"]) == 5
    assert "agents" in out and "show_panel" in out
    n += 3
    # New field present and well-shaped
    assert "groups" in out
    assert [g["h1"]["text"] for g in out["groups"]] == ["Plan", "Budget"]
    assert [c["text"] for c in out["groups"][0]["children"]] == ["Field", "Comms"]
    assert [c["text"] for c in out["groups"][1]["children"]] == ["Paid media"]
    n += 4
    print(f"  plan_outline groups field: {n} assertions passed")


# ---------------------------------------------------------------------------
# 3. partials/message.html renders <details> groups
# ---------------------------------------------------------------------------
def test_partial_renders_groups():
    n = 0
    # Build outline with multiple h1 groups so the template renders them
    outline = plan_outline(
        "# Plan\n## Field\n## Comms\n# Budget\n### Paid media\n",
        active_agents=["win_number", "precincts", "messaging"],
    )
    assert outline["show_panel"], "expected show_panel for this fixture"
    n += 1

    rendered = render_to_string("partials/message.html", {
        "answer_html":   "<h1 id=\"b-x-plan\">Plan</h1><h2 id=\"b-x-field\">Field</h2>",
        "active_agents": ["win_number", "precincts", "messaging"],
        "errors":        [],
        "bubble_id":     "b-x",
        "outline":       outline,
        "source_cards":  [],
    })
    rendered = html.unescape(rendered)

    # <details> wrapper present, open by default
    assert "<details class=\"plan-panel-group\" open" in rendered, \
        "details/group element missing or not open"
    # data-group-h1 carries the slug
    assert 'data-group-h1="plan"' in rendered
    assert 'data-group-h1="budget"' in rendered
    n += 3
    # Caret SVG inside summary
    assert "plan-panel-group-caret" in rendered
    # Group title link uses the bubble-prefixed anchor
    assert 'href="#b-x-plan"' in rendered
    assert 'href="#b-x-budget"' in rendered
    # Children list class
    assert "plan-panel-group-list" in rendered
    n += 4
    # Old flat <ul> at top level should be gone (no <ul> directly under
    # plan-panel-nav anymore — they live inside <details>)
    nav_idx = rendered.find('class="plan-panel-nav"')
    assert nav_idx != -1
    # The first thing inside the nav should be a <details ... or an orphan <ul ... --orphan
    after_nav = rendered[nav_idx:nav_idx + 600]
    assert "<details" in after_nav, "nav should contain at least one details element"
    n += 1

    # Orphan-only outline (no h1) renders the orphan-list class
    orphan_outline = plan_outline(
        "## Just a sub\n## Another sub\n",
        active_agents=["win_number", "precincts", "messaging"],
    )
    orphan_html = render_to_string("partials/message.html", {
        "answer_html": "<h2>x</h2>",
        "active_agents": ["win_number", "precincts", "messaging"],
        "errors": [], "bubble_id": "b-y", "outline": orphan_outline,
        "source_cards": [],
    })
    assert "plan-panel-group-list--orphan" in html.unescape(orphan_html)
    n += 1

    print(f"  partial renders groups: {n} assertions passed")


# ---------------------------------------------------------------------------
# 4. chat.html ships the new CSS
# ---------------------------------------------------------------------------
def test_chat_html_group_css():
    n = 0
    chat_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "chat.html",
    )
    src = open(chat_path).read()
    for selector in (
        ".plan-panel-group",
        ".plan-panel-group > summary",
        ".plan-panel-group-head",
        ".plan-panel-group-caret",
        ".plan-panel-group[open]",
        ".plan-panel-group-title",
        ".plan-panel-group-list",
        ".plan-panel-group-list--orphan",
    ):
        assert selector in src, f"missing CSS selector: {selector}"
        n += 1
    # Caret rotates when open
    assert "transform: rotate(90deg)" in src, "open-state caret rotation missing"
    n += 1
    # Native marker hidden so our caret SVG is the only indicator
    assert "::-webkit-details-marker" in src, "native details marker not hidden"
    n += 1
    print(f"  chat.html group CSS: {n} assertions passed")


# ---------------------------------------------------------------------------
# 5. demo_tiles config: happy + defensive paths
# ---------------------------------------------------------------------------
def test_demo_tiles_config():
    n = 0
    tiles = demo_tiles.get_demo_tiles()
    assert len(tiles) == 5, f"expected 5 default tiles, got {len(tiles)}"
    n += 1

    required = {"id", "chip", "chip_kind", "headline", "preview", "prompt"}
    ids = set()
    for t in tiles:
        assert required.issubset(t.keys()), f"tile missing fields: {t}"
        assert t["chip_kind"] in demo_tiles.CHIP_KINDS, \
            f"unknown chip_kind {t['chip_kind']!r} in tile {t['id']!r}"
        assert t["id"] not in ids, f"duplicate id {t['id']!r}"
        ids.add(t["id"])
        # Style: no em dashes
        for field in ("headline", "preview", "prompt"):
            assert "—" not in t[field], \
                f"em dash in tile {t['id']!r}.{field}: {t[field]!r}"
    n += 1

    # Specific tiles known to exist (acts as a smoke test against accidental drops)
    for needed in ("gwinnett-gotv-latinx", "win-number-ga07-midterm",
                   "voterfile-segment-and-match"):
        assert needed in ids, f"missing expected tile id {needed!r}"
        n += 1

    # ---- Defensive filtering ----
    # Inject a bad tile (unknown chip_kind) and confirm it's dropped
    original = list(demo_tiles.DEMO_TILES)
    try:
        demo_tiles.DEMO_TILES.append({  # type: ignore[arg-type]
            "id": "bad-color", "chip": "x", "chip_kind": "rainbow",
            "headline": "h", "preview": "p", "prompt": "q",
        })
        out = demo_tiles.get_demo_tiles()
        assert "bad-color" not in {t["id"] for t in out}
        n += 1

        # Inject a tile with missing required field
        demo_tiles.DEMO_TILES.append({  # type: ignore[arg-type]
            "id": "no-headline", "chip": "x", "chip_kind": "plan",
            "headline": "", "preview": "p", "prompt": "q",
        })
        out = demo_tiles.get_demo_tiles()
        assert "no-headline" not in {t["id"] for t in out}
        n += 1

        # Duplicate id is also dropped
        demo_tiles.DEMO_TILES.append({  # type: ignore[arg-type]
            "id": "gwinnett-gotv-latinx", "chip": "Dup", "chip_kind": "plan",
            "headline": "Duplicate", "preview": "p", "prompt": "q",
        })
        out = demo_tiles.get_demo_tiles()
        assert sum(1 for t in out if t["id"] == "gwinnett-gotv-latinx") == 1
        n += 1
    finally:
        demo_tiles.DEMO_TILES[:] = original

    print(f"  demo_tiles config: {n} assertions passed")


# ---------------------------------------------------------------------------
# 6. chat.html template iterates demo_tiles instead of hardcoding them
# ---------------------------------------------------------------------------
def test_chat_html_uses_iteration():
    n = 0
    chat_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "chat.html",
    )
    src = open(chat_path).read()

    # New iteration construct present
    assert "{% for tile in demo_tiles %}" in src, \
        "demo tiles for-loop missing"
    assert "{{ tile.prompt }}" in src
    assert "{{ tile.headline }}" in src
    assert "{{ tile.chip }}" in src
    assert "{{ tile.chip_kind }}" in src
    assert 'data-tile="{{ tile.id }}"' in src
    n += 6

    # Hardcoded prompt strings should be GONE from this template. Sample
    # check: the unique demo prompt about Vietnamese-language texts should
    # no longer be inlined.
    assert "Draft a Vietnamese-language text message to AAPI voters" not in src, \
        "hardcoded Vietnamese prompt still in chat.html"
    assert "Build a Gwinnett County GOTV plan" not in src, \
        "hardcoded GOTV prompt still in chat.html"
    n += 2

    print(f"  chat.html iteration: {n} assertions passed")


# ---------------------------------------------------------------------------
# 7. chat_view() puts demo_tiles in context and template renders all 5
# ---------------------------------------------------------------------------
def test_chat_view_exposes_tiles():
    n = 0
    rf = RequestFactory()
    req = rf.get("/chat/")
    engine = import_module("django.contrib.sessions.backends.signed_cookies")
    req.session = engine.SessionStore()
    req.session["authenticated"] = True

    resp = chat_views.chat_view(req)
    body = resp.content.decode("utf-8")
    body_unescaped = html.unescape(body)

    # All five tile ids should land in the rendered HTML
    expected_ids = {t["id"] for t in demo_tiles.get_demo_tiles()}
    for tid in expected_ids:
        assert f'data-tile="{tid}"' in body, f"tile {tid!r} missing from response"
        n += 1

    # Each tile's prompt text must appear in the rendered data-prompt attr
    for t in demo_tiles.get_demo_tiles():
        # Django escapes apostrophes inside attribute values, so unescape first
        assert t["prompt"] in body_unescaped, \
            f"prompt for tile {t['id']!r} not in response body"
        n += 1

    # And the chip kind class fires
    for t in demo_tiles.get_demo_tiles():
        assert f"demo-tile-chip--{t['chip_kind']}" in body, \
            f"chip class missing for {t['id']!r}"
        n += 1

    print(f"  chat_view exposes tiles: {n} assertions passed")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Milestone G: plan-panel h1 grouping + demo tile config")
    test_group_sections_by_h1()
    test_plan_outline_groups_field()
    test_partial_renders_groups()
    test_chat_html_group_css()
    test_demo_tiles_config()
    test_chat_html_uses_iteration()
    test_chat_view_exposes_tiles()
    print("PASS: all assertion groups OK.")
