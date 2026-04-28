"""
Tests for chat.render_helpers: source extraction, plan-run heuristic, C3
footer text, and the agent pill label prettifier.

Usage:
    python scripts/_test_render_helpers.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Bootstrap Django (the helpers do not need it but the project convention is
# to have every test bootstrap settings so paths resolve consistently).
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")

import django  # noqa: E402

django.setup()

from chat.render_helpers import (  # noqa: E402
    extract_sources,
    is_plan_run,
    c3_footer_text,
    agent_pill_label,
    auto_title,
    download_thumb_kind,
    enrich_downloads,
)


# Sample memos shaped like what the researcher node returns.
MEMO_A = (
    "--- MEMO FROM SOURCE: Catalist | DATE: 2024-11-12 ---\n"
    "Latinx voters under 35 broke 62-37 D in Gwinnett County, with turnout up "
    "9 points compared to the prior midterm. Spanish-language door knocks "
    "showed strong contact rates in apartment-heavy precincts."
)
MEMO_B = (
    "--- MEMO FROM SOURCE: Pew Research | DATE: 2025-03-04 ---\n"
    "Naturalized voters cite affordability and healthcare as top concerns, "
    "tracking with the broader electorate."
)
MEMO_C_DUP = (
    "--- MEMO FROM SOURCE: Catalist | DATE: 2024-11-12 ---\n"
    "Same source, same date, different body. Should dedupe to one card."
)
MEMO_NO_HEADER = "Just a free-form research note without the standard header."


def main() -> int:
    failures: list[str] = []

    # 1. Empty / None inputs.
    if extract_sources(None) != []:
        failures.append("extract_sources(None) should return []")
    if extract_sources([]) != []:
        failures.append("extract_sources([]) should return []")

    # 2. Single memo parses cleanly.
    out = extract_sources([MEMO_A])
    if len(out) != 1:
        failures.append(f"single memo should yield 1 card, got {len(out)}")
    if out and out[0]["source"] != "Catalist":
        failures.append(f"source mis-parsed: {out[0]}")
    if out and out[0]["date"] != "2024-11-12":
        failures.append(f"date mis-parsed: {out[0]}")
    if out and "Latinx" not in out[0]["preview"]:
        failures.append(f"preview missing body text: {out[0]['preview'][:80]}")

    # 3. Two distinct memos produce two cards in original order.
    out2 = extract_sources([MEMO_A, MEMO_B])
    if len(out2) != 2:
        failures.append(f"two memos should yield 2 cards, got {len(out2)}")
    if out2 and out2[0]["source"] != "Catalist":
        failures.append("first card should be Catalist (order preserved)")
    if len(out2) > 1 and out2[1]["source"] != "Pew Research":
        failures.append("second card should be Pew Research")

    # 4. Duplicate (source, date) pairs collapse.
    out3 = extract_sources([MEMO_A, MEMO_C_DUP, MEMO_B])
    if len(out3) != 2:
        failures.append(
            f"duplicate (source,date) should dedupe to 2 cards, got {len(out3)}"
        )

    # 5. Header-less memos are skipped, not raised.
    out4 = extract_sources([MEMO_NO_HEADER, MEMO_A])
    if len(out4) != 1:
        failures.append(
            f"header-less memo should be skipped (got {len(out4)} cards)"
        )

    # 6. Non-string entries (None, dict) are tolerated.
    out5 = extract_sources([None, {"not": "a string"}, MEMO_A])
    if len(out5) != 1:
        failures.append(f"non-string entries should be skipped, got {len(out5)}")

    # 7. Long body gets a truncation ellipsis.
    long_memo = (
        "--- MEMO FROM SOURCE: LongSource | DATE: 2025-01-01 ---\n"
        + ("x" * 800)
    )
    out6 = extract_sources([long_memo])
    if not out6 or "\u2026" not in out6[0]["preview"]:
        failures.append(
            "long memo preview should end with the ellipsis character"
        )

    # 8. is_plan_run heuristic: 2+ plan agents -> True.
    if not is_plan_run(["win_number", "precincts", "researcher"]):
        failures.append("is_plan_run should be True for win_number+precincts")
    if not is_plan_run(["cost_calculator", "messaging"]):
        failures.append("is_plan_run should be True for cost_calculator+messaging")

    # 9. is_plan_run heuristic: 0-1 plan agents -> False.
    if is_plan_run(["researcher"]):
        failures.append("is_plan_run should be False for researcher only")
    if is_plan_run(["win_number"]):
        failures.append("is_plan_run should be False for a single plan agent")
    if is_plan_run([]):
        failures.append("is_plan_run([]) should be False")
    if is_plan_run(None):
        failures.append("is_plan_run(None) should be False")

    # 10. c3_footer_text() is the canonical disclosure string.
    txt = c3_footer_text()
    if "Nonpartisan" not in txt:
        failures.append(f"c3_footer_text missing 'Nonpartisan': {txt!r}")
    if "candidate" not in txt.lower():
        failures.append(f"c3_footer_text missing 'candidate' guard: {txt!r}")

    # 11. agent_pill_label prettifies snake_case.
    if agent_pill_label("opposition_research") != "Opposition Research":
        failures.append(
            f"agent_pill_label('opposition_research') wrong: "
            f"{agent_pill_label('opposition_research')!r}"
        )
    if agent_pill_label("researcher") != "Researcher":
        failures.append("agent_pill_label('researcher') wrong")
    if agent_pill_label("") != "":
        failures.append("agent_pill_label('') should be ''")

    # 12. auto_title strips filler, title-cases, preserves codes/hyphens.
    cases_title = [
        ("What is the win number for GA-07 in the midterm?",
         lambda t: "GA-07" in t and "Win" in t and "Number" in t),
        ("Please draft a Spanish door-knock script for Latinx voters",
         lambda t: "Spanish" in t and "Door-Knock" in t and "Latinx" in t),
        ("Show me the GOP opponent in GA-06",
         lambda t: "GOP" in t and "GA-06" in t),  # GOP stays uppercase
        ("",  lambda t: t == "New conversation"),
        ("   ", lambda t: t == "New conversation"),
        ("hi", lambda t: t.lower() == "hi"),  # short greetings still produce something
        ("how are you", lambda t: t == "New conversation" or len(t) <= 48),  # all stopwords -> fallback
    ]
    for q, check in cases_title:
        title = auto_title(q)
        if not check(title):
            failures.append(f"auto_title({q!r}) returned unexpected: {title!r}")

    # auto_title respects the 6-word cap.
    long_q = "Find the best Spanish door-knock script targeting Latinx voters in Gwinnett County for the November midterm election cycle"
    long_title = auto_title(long_q)
    word_count = len(long_title.split())
    if word_count > 6:
        failures.append(f"auto_title should cap at 6 words, got {word_count}: {long_title!r}")

    # auto_title respects the 48-char cap with ellipsis.
    huge_q = "Massachusetts Connecticut Pennsylvania Wisconsin Minnesota Iowa Nebraska Kansas"
    huge_title = auto_title(huge_q)
    if len(huge_title) > 48:
        failures.append(f"auto_title should cap at 48 chars, got {len(huge_title)}: {huge_title!r}")

    # 13. download_thumb_kind maps known extensions correctly.
    cases_thumb = [
        ("plan_2026.docx",       "DOCX", "#3b82f6"),
        ("target_list.csv",      "CSV",  "#22c55e"),
        ("budget.xlsx",          "XLSX", "#16a34a"),
        ("oppo_book.pdf",        "PDF",  "#ef4444"),
        ("unknown.zzz",          "FILE", "#6b7280"),
        ("no_extension",         "FILE", "#6b7280"),
        (None,                   "FILE", "#6b7280"),
    ]
    for fname, want_kind, want_color in cases_thumb:
        got = download_thumb_kind(fname)
        if got["kind"] != want_kind:
            failures.append(f"thumb_kind({fname!r}) kind={got['kind']!r}, expected {want_kind!r}")
        if got["color"] != want_color:
            failures.append(f"thumb_kind({fname!r}) color={got['color']!r}, expected {want_color!r}")

    # Case-insensitive on extension (.DOCX should still resolve).
    if download_thumb_kind("PLAN.DOCX")["kind"] != "DOCX":
        failures.append("thumb_kind should lowercase the extension")

    # 14. enrich_downloads attaches thumb_kind / thumb_color without mutating input.
    base = [
        {"filename": "plan.docx",   "label": "Download Word Doc"},
        {"filename": "targets.csv", "label": "Download CSV"},
    ]
    enriched = enrich_downloads(base)
    if len(enriched) != 2:
        failures.append(f"enrich_downloads should preserve count, got {len(enriched)}")
    if enriched and enriched[0].get("thumb_kind") != "DOCX":
        failures.append(f"enriched[0] missing/incorrect thumb_kind: {enriched[0]}")
    if enriched and enriched[1].get("thumb_kind") != "CSV":
        failures.append(f"enriched[1] missing/incorrect thumb_kind: {enriched[1]}")
    if "thumb_kind" in base[0]:
        failures.append("enrich_downloads must not mutate the input dicts")
    if enrich_downloads(None) != []:
        failures.append("enrich_downloads(None) should return []")
    if enrich_downloads([]) != []:
        failures.append("enrich_downloads([]) should return []")
    # Non-dict entries are tolerated/skipped.
    if enrich_downloads(["not a dict", {"filename": "a.csv", "label": "L"}]) == []:
        failures.append("enrich_downloads should keep valid dicts even with garbage neighbors")

    # Report.
    print("chat.render_helpers test: 32+ assertions across 14 cases.")
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: all assertion groups OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
