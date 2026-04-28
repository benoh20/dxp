#!/usr/bin/env python
"""
Milestone F test suite — source dedup, scroll anchoring, and conversation
history (sidebar timestamps + rename + delete + drag-to-reorder).

Covers:
  1. extract_sources()  collapses duplicate sources, exposes count + date_range
  2. relative_time()    bucket coverage: just-now, minutes, hours, yesterday,
                        days, calendar fallback, defensive None/garbage
  3. partials/message.html renders the new ×N count badge and date_range
  4. chat.html sidebar markup carries draggable rows + data-conv-id +
                        delete button + inline-rename hooks + new CSS
  5. chat.html JS arms the rename / delete / drag handlers AND replaces
                        scrollToBottom with anchorUserPrompt on submit
  6. Backend views: rename / delete / reorder happy-paths + edge cases,
                        exercised through Django's RequestFactory and the
                        signed-cookie session backend so we don't need a
                        running server.

A single failed assertion crashes with a clear AssertionError. Each section
prints a PASS line with its assertion count so the bulk runner output is
greppable.
"""
from __future__ import annotations

import json
import os
import sys
import time

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")
django.setup()

from django.template.loader import render_to_string
from django.test import RequestFactory
from importlib import import_module

from chat.render_helpers import extract_sources, relative_time
from chat import views as chat_views


# ---------------------------------------------------------------------------
# 1. extract_sources() dedup
# ---------------------------------------------------------------------------
def test_extract_sources_dedup():
    assertions = 0

    # Defensive
    assert extract_sources(None) == []
    assert extract_sources([]) == []
    assertions += 2

    # Three memos, same source, three different dates -> one card with
    # count=3 and a date_range covering the span.
    memos = [
        "--- MEMO FROM SOURCE: Powerbuilder curated corpus | DATE: 2025-08-22 ---\nBody one.",
        "--- MEMO FROM SOURCE: Powerbuilder curated corpus | DATE: 2025-09-15 ---\nBody two.",
        "--- MEMO FROM SOURCE: Powerbuilder curated corpus | DATE: 2025-11-02 ---\nBody three.",
    ]
    cards = extract_sources(memos)
    assert len(cards) == 1, f"expected 1 collapsed card, got {len(cards)}"
    c = cards[0]
    assert c["source"] == "Powerbuilder curated corpus"
    assert c["count"] == 3
    assert c["date"] == "2025-11-02", f"date should be most recent, got {c['date']}"
    assert c["date_range"] == "2025-08-22 → 2025-11-02", c["date_range"]
    # Preview comes from the FIRST memo we saw for this source
    assert c["preview"].startswith("Body one"), c["preview"]
    assertions += 6

    # Source variations (case + whitespace) collapse to one card
    memos = [
        "--- MEMO FROM SOURCE: ProPublica | DATE: 2025-04-01 ---\nA",
        "--- MEMO FROM SOURCE: propublica  | DATE: 2025-05-01 ---\nB",
        "--- MEMO FROM SOURCE: ProPublica | DATE: 2025-04-01 ---\nC",  # exact dup, no count++
    ]
    cards = extract_sources(memos)
    assert len(cards) == 1, f"case/ws should collapse, got {len(cards)}"
    assert cards[0]["count"] == 2, f"duplicate date should not double-count, got {cards[0]['count']}"
    assertions += 2

    # Single-date source: count == 1, date_range empty string
    cards = extract_sources(["--- MEMO FROM SOURCE: Census ACS | DATE: 2024-12-01 ---\nX"])
    assert cards[0]["count"] == 1
    assert cards[0]["date"] == "2024-12-01"
    assert cards[0]["date_range"] == "", cards[0]["date_range"]
    assertions += 3

    # Mixed sources stay separate, in first-seen order
    memos = [
        "--- MEMO FROM SOURCE: AAA | DATE: 2025-01-01 ---\n",
        "--- MEMO FROM SOURCE: BBB | DATE: 2025-02-01 ---\n",
        "--- MEMO FROM SOURCE: AAA | DATE: 2025-03-01 ---\n",
    ]
    cards = extract_sources(memos)
    assert [c["source"] for c in cards] == ["AAA", "BBB"]
    assert cards[0]["count"] == 2 and cards[1]["count"] == 1
    assertions += 2

    # Header-less memos are skipped, not crashed on
    cards = extract_sources(["no header here", None, 123])
    assert cards == []
    assertions += 1

    print(f"  extract_sources dedup: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 2. relative_time() buckets
# ---------------------------------------------------------------------------
def test_relative_time_buckets():
    assertions = 0
    now = int(time.time())

    # Defensive
    assert relative_time(None) == ""
    assert relative_time("not-a-number") == ""
    assertions += 2

    # < 60s
    assert relative_time(now - 5,  now) == "Just now"
    assert relative_time(now - 59, now) == "Just now"
    # Future timestamp clamps to "Just now" (clock skew tolerance)
    assert relative_time(now + 5,  now) == "Just now"
    assertions += 3

    # < 60m
    assert relative_time(now - 60,    now) == "1m ago"
    assert relative_time(now - 5*60,  now) == "5m ago"
    assert relative_time(now - 59*60, now) == "59m ago"
    assertions += 3

    # < 24h
    assert relative_time(now - 60*60,    now) == "1h ago"
    assert relative_time(now - 5*60*60,  now) == "5h ago"
    assertions += 2

    # Yesterday: 36h ago crosses the calendar boundary on most clocks; pin
    # the comparison by computing 'now' at noon and 'ts' at noon yesterday.
    noon_today = int(time.mktime(time.strptime(
        time.strftime("%Y-%m-%d") + " 12:00", "%Y-%m-%d %H:%M")))
    yest_noon  = noon_today - 86400
    assert relative_time(yest_noon, noon_today) == "Yesterday"
    assertions += 1

    # Nd ago (within the week)
    three_days = noon_today - 3 * 86400
    assert relative_time(three_days, noon_today) == "3d ago"
    assertions += 1

    # Calendar fallback: > 7 days returns "Mon DD"
    out = relative_time(noon_today - 30 * 86400, noon_today)
    # Should look like "Mar 29" or similar — three letters, space, two digits
    assert len(out) == 6 and out[3] == " " and out[:3].isalpha() and out[4:].isdigit(), out
    assertions += 1

    print(f"  relative_time: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 3. partials/message.html renders dedup affordances
# ---------------------------------------------------------------------------
def test_partial_renders_dedup_badge():
    assertions = 0

    ctx = {
        "answer_html":  "<p>x</p>",
        "active_agents": ["researcher"],
        "errors": [],
        "bubble_id": "b-test1234",
        "outline": {"show_panel": False},
        "source_cards": [
            {
                "source": "Powerbuilder curated corpus",
                "date": "2025-11-02",
                "date_range": "2025-08-22 → 2025-11-02",
                "count": 3,
                "preview": "Some preview text.",
            },
            {
                "source": "Census ACS",
                "date": "2024-12-01",
                "date_range": "",
                "count": 1,
                "preview": "Single memo preview.",
            },
        ],
    }
    html = render_to_string("partials/message.html", ctx)

    # Count badge present only when count > 1
    assert "source-card-count" in html, "count CSS class missing"
    assert "×3" in html or "&#xd7;3" in html or "&times;3" in html, \
        "×3 count not rendered"
    assertions += 2

    # date_range surfaces when present
    assert "2025-08-22" in html and "2025-11-02" in html, \
        "date range not surfaced"
    assertions += 1

    # Single-memo source must NOT render a count pill (×1 would be noise)
    # We assert there is exactly one count-pill on the page.
    assert html.count("source-card-count") == 1, \
        f"expected 1 count badge, got {html.count('source-card-count')}"
    assertions += 1

    print(f"  partial dedup markup: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 4. chat.html sidebar markup
# ---------------------------------------------------------------------------
def test_chat_html_sidebar_markup():
    assertions = 0
    chat_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "chat.html",
    )
    src = open(chat_path).read()

    # New row container with id, delegated handlers will hook this
    assert 'id="sidebar-conv-list"' in src, "sidebar list container missing id"
    assert "sidebar-conv-row" in src, "draggable row class missing"
    assert 'draggable="true"' in src, "draggable attribute missing"
    assert 'data-conv-id=' in src, "data-conv-id attribute missing"
    assert 'data-conv-title=' in src, "data-conv-title attribute missing"
    assertions += 5

    # Inline rename + delete hooks
    assert 'data-action="rename-conv"' in src, "rename hook missing"
    assert 'data-action="delete-conv"' in src, "delete hook missing"
    assertions += 2

    # Relative-time label rendered (server-side computed)
    assert "conv.time_label" in src, "relative time field not used in template"
    assertions += 1

    # CSS rules for the new states
    assert ".sidebar-conv-row" in src, "row CSS missing"
    assert ".sidebar-conv-row.dragging" in src, "drag visual cue CSS missing"
    assert ".sidebar-conv-row.drag-over" in src, "drag-over visual cue CSS missing"
    assert ".sidebar-conv-delete" in src, "delete button CSS missing"
    assert "[contenteditable=\"true\"]" in src, "rename edit-state CSS missing"
    assertions += 5

    # Old simple anchor markup is GONE — no bare `class="sidebar-conv "` link.
    # The new layout wraps it in .sidebar-conv-link inside .sidebar-conv-row.
    assert "sidebar-conv-link" in src, "new link wrapper class missing"
    # Old single-anchor pattern: class="sidebar-conv {% if ... %}active". The
    # row carries 'active' now, not the anchor.
    assert 'class="sidebar-conv ' not in src, \
        "legacy single-anchor sidebar markup still present"
    assertions += 2

    print(f"  sidebar markup: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 5. chat.html JS handlers + scroll anchoring
# ---------------------------------------------------------------------------
def test_chat_html_js_wiring():
    assertions = 0
    chat_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "chat.html",
    )
    src = open(chat_path).read()

    # Scroll anchoring helper (Milestone F first half)
    assert "function anchorUserPrompt(" in src, "anchorUserPrompt helper missing"
    assert "anchorUserPrompt(row)" in src, "anchorUserPrompt not invoked on submit"
    assertions += 2

    # CSRF helper present
    assert "X-CSRFToken" in src, "CSRF header missing in fetch calls"
    assert "csrftoken" in src, "CSRF cookie read missing"
    assertions += 2

    # Rename: contenteditable swap + Enter/Escape keys
    assert "function startRename(" in src, "startRename missing"
    assert "function commitRename(" in src, "commitRename missing"
    assert "function cancelRename(" in src, "cancelRename missing"
    assert "'Enter'" in src and "'Escape'" in src, "key handling missing"
    assertions += 4

    # Rename POSTs to the rename endpoint
    assert "/api/conv/" in src and "/rename/" in src, "rename endpoint not called"
    assertions += 1

    # Delete: confirm() then optimistic remove + POST
    assert "window.confirm(" in src, "delete confirm() missing"
    assert "/delete/" in src, "delete endpoint not called"
    assertions += 2

    # Drag handlers cover all four DnD events we rely on
    for ev in ("dragstart", "dragover", "drop", "dragend"):
        assert f"'{ev}'" in src, f"DnD {ev} handler missing"
    # And POSTs the new order
    assert "/api/conv/reorder/" in src, "reorder endpoint not called"
    assertions += 5

    print(f"  chat.html JS wiring: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 6. Backend views: rename / delete / reorder
# ---------------------------------------------------------------------------
def _make_authed_request(rf, path, body=None, content_type="application/json"):
    """
    Build a POST request with a real session that says authenticated=True.
    Skips the @demo_login_required guard the same way a logged-in browser would.
    Returns the request after attaching a saved SessionStore.
    """
    if body is None:
        payload = b""
    elif isinstance(body, (dict, list)):
        payload = json.dumps(body).encode("utf-8")
    else:
        payload = body
    req = rf.post(path, data=payload, content_type=content_type)
    engine = import_module("django.contrib.sessions.backends.signed_cookies")
    req.session = engine.SessionStore()
    req.session["authenticated"] = True
    return req


def test_backend_rename_delete_reorder():
    assertions = 0
    rf = RequestFactory()

    # Seed three conversations into a session and run them through the views
    convs = [
        {"id": "id-A", "title": "Alpha", "timestamp": "2026-04-28 09:00",
         "created_at": int(time.time()) - 600, "messages": []},
        {"id": "id-B", "title": "Bravo", "timestamp": "2026-04-28 09:10",
         "created_at": int(time.time()) - 300, "messages": []},
        {"id": "id-C", "title": "Charlie", "timestamp": "2026-04-28 09:20",
         "created_at": int(time.time()) - 60, "messages": []},
    ]

    # ---- rename happy path ----
    req = _make_authed_request(rf, "/api/conv/id-B/rename/", {"title": "Bravo Plus"})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.rename_conv_view(req, conv_id="id-B")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    data = json.loads(resp.content)
    assert data["ok"] is True and data["title"] == "Bravo Plus", data
    # Side effect: title flipped in the session list
    assert any(c["id"] == "id-B" and c["title"] == "Bravo Plus"
               for c in req.session["conversations"])
    assertions += 3

    # ---- rename validation: empty title rejected ----
    req = _make_authed_request(rf, "/api/conv/id-B/rename/", {"title": "   "})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.rename_conv_view(req, conv_id="id-B")
    assert resp.status_code == 400, f"empty title should 400, got {resp.status_code}"
    assertions += 1

    # ---- rename validation: 80-char cap ----
    long_title = "X" * 200
    req = _make_authed_request(rf, "/api/conv/id-B/rename/", {"title": long_title})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.rename_conv_view(req, conv_id="id-B")
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert len(data["title"]) == 80, f"title not capped at 80, got {len(data['title'])}"
    assertions += 2

    # ---- rename: missing id -> 404 ----
    req = _make_authed_request(rf, "/api/conv/id-MISSING/rename/", {"title": "x"})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.rename_conv_view(req, conv_id="id-MISSING")
    assert resp.status_code == 404
    assertions += 1

    # ---- delete happy path: removes the row ----
    req = _make_authed_request(rf, "/api/conv/id-B/delete/", {})
    req.session["conversations"] = [dict(c) for c in convs]
    req.session["current_conv_id"] = "id-A"
    resp = chat_views.delete_conv_view(req, conv_id="id-B")
    assert resp.status_code == 200
    assert [c["id"] for c in req.session["conversations"]] == ["id-A", "id-C"]
    # Active conv was id-A, should NOT have been cleared
    assert req.session["current_conv_id"] == "id-A"
    assertions += 3

    # ---- delete: clears current_conv_id when active row removed ----
    req = _make_authed_request(rf, "/api/conv/id-A/delete/", {})
    req.session["conversations"] = [dict(c) for c in convs]
    req.session["current_conv_id"] = "id-A"
    resp = chat_views.delete_conv_view(req, conv_id="id-A")
    assert resp.status_code == 200
    assert req.session["current_conv_id"] is None
    assertions += 2

    # ---- delete: missing id -> 404 ----
    req = _make_authed_request(rf, "/api/conv/id-NOPE/delete/", {})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.delete_conv_view(req, conv_id="id-NOPE")
    assert resp.status_code == 404
    assertions += 1

    # ---- reorder happy path ----
    req = _make_authed_request(rf, "/api/conv/reorder/",
                                {"order": ["id-C", "id-A", "id-B"]})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.reorder_conv_view(req)
    assert resp.status_code == 200
    assert [c["id"] for c in req.session["conversations"]] == ["id-C", "id-A", "id-B"]
    assertions += 2

    # ---- reorder: partial order keeps unmentioned items at the tail ----
    req = _make_authed_request(rf, "/api/conv/reorder/", {"order": ["id-C"]})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.reorder_conv_view(req)
    assert resp.status_code == 200
    assert [c["id"] for c in req.session["conversations"]] == ["id-C", "id-A", "id-B"]
    assertions += 2

    # ---- reorder: bogus body -> 400 ----
    req = _make_authed_request(rf, "/api/conv/reorder/", {"order": "not-a-list"})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.reorder_conv_view(req)
    assert resp.status_code == 400
    assertions += 1

    # ---- reorder: unknown ids are silently dropped (don't bring them in) ----
    req = _make_authed_request(rf, "/api/conv/reorder/",
                                {"order": ["ghost-id", "id-B", "id-A"]})
    req.session["conversations"] = [dict(c) for c in convs]
    resp = chat_views.reorder_conv_view(req)
    assert resp.status_code == 200
    new_ids = [c["id"] for c in req.session["conversations"]]
    assert new_ids == ["id-B", "id-A", "id-C"], new_ids
    assertions += 1

    print(f"  backend rename/delete/reorder: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# 7. URL routes wired up
# ---------------------------------------------------------------------------
def test_url_routes_resolve():
    assertions = 0
    from django.urls import reverse
    assert reverse("conv_rename", kwargs={"conv_id": "abc"}).endswith("/api/conv/abc/rename/")
    assert reverse("conv_delete", kwargs={"conv_id": "abc"}).endswith("/api/conv/abc/delete/")
    assert reverse("conv_reorder").endswith("/api/conv/reorder/")
    assertions += 3
    print(f"  URL routes: {assertions} assertions passed")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Milestone F: source dedup + scroll anchor + conversation history")
    test_extract_sources_dedup()
    test_relative_time_buckets()
    test_partial_renders_dedup_badge()
    test_chat_html_sidebar_markup()
    test_chat_html_js_wiring()
    test_backend_rename_delete_reorder()
    test_url_routes_resolve()
    print("PASS: all assertion groups OK.")
