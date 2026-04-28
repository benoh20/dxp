"""
Test the paid-media estimator that reads file 07 benchmarks.

Verifies:
  1. query_mentions_paid_media catches the expected keywords and ignores
     unrelated queries.
  2. Budget tiers select the right channel mix (under $25K, $25K-$75K,
     $75K-$200K, $200K+).
  3. Channel allocations sum to 1.0 within each tier (digital + non-digital).
  4. Spend per channel = budget * share_pct (within rounding).
  5. Impressions and reach are computed and positive for each digital channel.
  6. In-language pricing reduces CPMs by ~22.5 percent.
  7. Persuasion-point lift is set for Meta, YouTube, CTV; not for Spotify, etc.
  8. The narrative formatter returns a markdown section with expected headers.
  9. Below-$25K budgets skip CTV, YouTube, and podcast host-reads.
 10. Returns None for budget=None or budget<=0.

Usage:
    python scripts/_test_paid_media_estimator.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")

import django  # noqa: E402

django.setup()

from chat.agents.paid_media import (  # noqa: E402
    estimate_paid_media,
    format_paid_media_section,
    query_mentions_paid_media,
    CPM_RANGES,
    IN_LANGUAGE_DISCOUNT,
)


def main() -> int:
    failures: list[str] = []

    # 1. Keyword detection
    paid_yes = [
        "What does $50,000 buy me on Meta and YouTube?",
        "Plan my paid media mix for Gwinnett",
        "What CPM should I expect on CTV?",
        "boost a post on Facebook",
        "media plan for $100k digital ad budget",
    ]
    paid_no = [
        "How many doors can I knock with $10,000?",
        "Show me Latinx 18-35 voters in Gwinnett",
        "What is the win number for state senate 41?",
    ]
    for q in paid_yes:
        if not query_mentions_paid_media(q):
            failures.append(f"keyword check: should match (paid media): '{q}'")
    for q in paid_no:
        if query_mentions_paid_media(q):
            failures.append(f"keyword check: should NOT match: '{q}'")

    # 2. Tier selection
    tiers = [
        (15_000,   "Under $25K"),
        (50_000,   "$25K to $75K"),
        (150_000,  "$75K to $200K"),
        (500_000,  "$200K+"),
    ]
    for budget, expected_substr in tiers:
        est = estimate_paid_media(budget=budget)
        if est is None:
            failures.append(f"tier {budget}: estimator returned None")
            continue
        if expected_substr not in est["tier_label"]:
            failures.append(
                f"tier {budget}: expected '{expected_substr}' in label, got "
                f"'{est['tier_label']}'"
            )

    # 3. Allocations sum to ~1.0 per tier
    for budget, _ in tiers:
        est = estimate_paid_media(budget=budget)
        digital_total = sum(c["share_pct"] for c in est["channels"])
        non_digital_total = sum(n["share_pct"] for n in est["non_digital"])
        total = digital_total + non_digital_total
        if not (99.5 <= total <= 100.5):
            failures.append(
                f"tier {budget}: shares sum to {total:.1f}%, expected ~100.0"
            )

    # 4. Spend per channel = budget * share_pct
    est = estimate_paid_media(budget=100_000)
    for c in est["channels"]:
        expected_spend = 100_000 * c["share_pct"] / 100.0
        if abs(c["spend"] - expected_spend) > 1.0:
            failures.append(
                f"channel {c['channel']}: spend {c['spend']} != expected "
                f"{expected_spend}"
            )

    # 5. Impressions and reach are positive
    est = estimate_paid_media(budget=100_000)
    for c in est["channels"]:
        if c["impressions"]["mid"] <= 0:
            failures.append(f"channel {c['channel']}: zero impressions at $100K")
        if c["channel"] in {"meta_feed", "youtube_trueview", "ctv"} and c["reach"] <= 0:
            failures.append(f"channel {c['channel']}: zero reach at $100K")

    # 6. In-language pricing reduces CPMs
    est_en = estimate_paid_media(budget=100_000, language_intent="en")
    est_es = estimate_paid_media(budget=100_000, language_intent="es")
    en_meta = next(c for c in est_en["channels"] if c["channel"] == "meta_feed")
    es_meta = next(c for c in est_es["channels"] if c["channel"] == "meta_feed")
    expected_es_cpm_low = en_meta["cpm_low"] * (1.0 - IN_LANGUAGE_DISCOUNT)
    if abs(es_meta["cpm_low"] - expected_es_cpm_low) > 0.5:
        failures.append(
            f"in-language CPM: en=${en_meta['cpm_low']}, es=${es_meta['cpm_low']}, "
            f"expected es ~ ${expected_es_cpm_low:.2f}"
        )
    if not est_es["in_language_pricing"]:
        failures.append("in_language_pricing flag not set when language_intent='es'")
    if est_en["in_language_pricing"]:
        failures.append("in_language_pricing flag set when language_intent='en'")

    # 7. Persuasion lift on Meta/YouTube/CTV; none on Spotify
    est = estimate_paid_media(budget=150_000)
    for c in est["channels"]:
        if c["channel"] in {"meta_feed", "youtube_trueview", "ctv"}:
            if not c.get("points_lift"):
                failures.append(f"{c['channel']}: missing points_lift")
            elif c["points_lift"]["low"] <= 0:
                failures.append(f"{c['channel']}: points_lift low = 0 at $150K")
        if c["channel"] == "spotify_audio" and c.get("points_lift"):
            failures.append("spotify_audio should not have points_lift")

    # 8. Narrative formatter returns markdown with expected headers
    section = format_paid_media_section(est)
    must_contain = [
        "### Paid Media Plan",
        "**Digital channels**",
        "Meta (Facebook + Instagram",
        "YouTube TrueView",
        "Connected TV",
        "Source: Powerbuilder corpus file 07",
    ]
    for needle in must_contain:
        if needle not in section:
            failures.append(f"narrative missing: '{needle}'")

    # 9. Below-$25K skips CTV/YouTube/podcast
    est_small = estimate_paid_media(budget=15_000)
    digital_channels_small = {c["channel"] for c in est_small["channels"]}
    forbidden = {"ctv", "youtube_trueview", "podcast_hostread"}
    leaks = digital_channels_small & forbidden
    if leaks:
        failures.append(
            f"below-$25K tier should not include {forbidden}, got {leaks}"
        )

    # 10. Edge cases
    if estimate_paid_media(budget=None) is not None:
        failures.append("budget=None should return None")
    if estimate_paid_media(budget=0) is not None:
        failures.append("budget=0 should return None")
    if estimate_paid_media(budget=-100) is not None:
        failures.append("budget<0 should return None")

    # 11. Saturation cap: $100K spend on a 5,000-voter universe should
    # saturate every digital channel, capping reach at the universe and
    # firing the saturation warning.
    est_sat = estimate_paid_media(budget=100_000, target_universe=5_000)
    if not any(c.get("saturated") for c in est_sat["channels"]):
        failures.append("saturation: at least one channel should saturate at $100K vs 5K universe")
    for c in est_sat["channels"]:
        if c["reach"] > 5_000:
            failures.append(
                f"saturation: {c['channel']} reach {c['reach']} > universe 5,000"
            )
    if not any("Saturation warning" in n for n in est_sat["notes"]):
        failures.append("saturation: warning note missing from notes list")

    # 11b. No saturation when universe is large.
    est_big = estimate_paid_media(budget=100_000, target_universe=2_000_000)
    if any(c.get("saturated") for c in est_big["channels"]):
        failures.append("no-saturation case: should not saturate at 2M universe")

    # Reporting
    print(
        f"Paid-media estimator test: {len(CPM_RANGES)} CPM channels, "
        f"in-language discount {IN_LANGUAGE_DISCOUNT*100:.1f}%."
    )
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: all 11 assertion groups OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
