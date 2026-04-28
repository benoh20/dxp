# powerbuilder/chat/agents/paid_media.py
"""
Paid-media budget estimator.

Pure helper module that converts a paid-digital budget into:
  1. A tier-appropriate channel mix (Meta, YouTube, CTV, SMS, audio, print).
  2. Per-channel impressions, reach, frequency, and persuasion-point estimates.
  3. A markdown narrative section that drops cleanly into the finance memo.

The benchmarks are codified from `tool_templates/best_practices/07_paid_media_digital_benchmarks.md`,
which is the source of truth for CPM ranges, frequency caps, and channel mix
recommendations by budget tier. When file 07 is updated, update the constants
in this module so the two stay aligned.

This module makes no LLM calls and no network calls. Determinism matters: the
same budget input produces the same channel allocation, impressions, and
persuasion estimates every run, which is the only way the demo and the
end-of-cycle reporting line up.

Public surface:
  - estimate_paid_media(budget, query=None, language_intent=None,
                        district_label=None) -> dict | None
  - format_paid_media_section(estimate: dict) -> str
  - PAID_MEDIA_KEYWORDS  (regex used by callers to gate the estimator)

The c3-safe framing in file 07 is preserved: civic engagement context only,
no candidate or party persuasion targeting copy.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source-of-truth benchmarks from file 07
# ---------------------------------------------------------------------------
#
# CPM ranges are (low, high) USD per 1,000 impressions for civic-engagement
# inventory in the 2024 cycle. Midpoints drive impression math; both bounds
# are surfaced in the narrative so the operator sees the uncertainty band.

CPM_RANGES = {
    "meta_feed":          (7.0,  14.0),   # broad civic awareness
    "meta_geo":           (14.0, 28.0),   # narrow geo (county/precinct cluster)
    "youtube_trueview":   (9.0,  18.0),
    "youtube_bumper":     (18.0, 32.0),
    "ctv":                (35.0, 65.0),
    "programmatic":       (2.0,  6.0),
    "tiktok":             (8.0,  16.0),
    "snap":               (6.0,  12.0),
    "spotify_audio":      (14.0, 22.0),
    "podcast_hostread":   (25.0, 50.0),
}

# In-language inventory clears 15-30 percent under English CPMs in the same DMA.
# Use the midpoint of that range (22.5 percent) when language_intent is set.
IN_LANGUAGE_DISCOUNT = 0.225

# Persuasion CPM (USD per percentage point of attitudinal lift in target universe),
# from Analyst Institute / partner RCT meta-analyses 2018 to 2024.
PERSUASION_CPM = {
    "meta_video":     (35_000.0,  70_000.0),
    "youtube":        (40_000.0,  90_000.0),
    "ctv":            (80_000.0, 160_000.0),
    "direct_mail":    (90_000.0, 180_000.0),
    "door_knock":     (25_000.0,  55_000.0),
}

# Frequency caps: max impressions per person per week, and per flight (assumed
# 6-week flight). Used to derive reach from total impressions.
FREQUENCY_CAPS = {
    "meta_feed":        {"per_week": 3, "per_flight": 8},
    "youtube_trueview": {"per_week": 4, "per_flight": 12},
    "ctv":              {"per_week": 5, "per_flight": 25},
    "programmatic":     {"per_week": 10, "per_flight": 25},
    "tiktok":           {"per_week": 3, "per_flight": 8},
    "spotify_audio":    {"per_week": 4, "per_flight": 12},
    "podcast_hostread": {"per_week": 1, "per_flight": 3},
}

# Default flight length used for reach math (weeks).
DEFAULT_FLIGHT_WEEKS = 6

# ---------------------------------------------------------------------------
# Channel mix by budget tier (file 07 recommendations)
# ---------------------------------------------------------------------------
#
# Each tier is (max_budget_usd, allocations_dict). Allocations sum to 1.0.
# The three percentages from file 07 that are NOT digital paid (SMS, print,
# door literature) are tracked separately so the digital impression math is
# only applied to the digital portion.

TIER_ALLOCATIONS = [
    # (upper_budget, digital_mix, non_digital_mix, label)
    (
        25_000,
        {"meta_feed": 0.70},
        {"sms": 0.20, "print": 0.10},
        "Under $25K - doors do persuasion, digital is awareness",
    ),
    (
        75_000,
        {"meta_feed": 0.50, "youtube_trueview": 0.20, "spotify_audio": 0.10},
        {"sms": 0.15, "print": 0.05},
        "$25K to $75K - add YouTube once Meta saturates (about week 4)",
    ),
    (
        200_000,
        {"meta_feed": 0.35, "youtube_trueview": 0.25, "ctv": 0.20,
         "spotify_audio": 0.05},
        {"sms": 0.10, "print": 0.05},
        "$75K to $200K - CTV in last 2 weeks of GOTV",
    ),
    (
        float("inf"),
        {"meta_feed": 0.30, "youtube_trueview": 0.25, "ctv": 0.20,
         "spotify_audio": 0.05, "podcast_hostread": 0.05},
        {"sms": 0.10, "print": 0.05},
        "$200K+ - add partnership podcast host-reads and community radio",
    ),
]

# Friendly labels for narrative output.
CHANNEL_LABELS = {
    "meta_feed":        "Meta (Facebook + Instagram, feed + reels)",
    "meta_geo":         "Meta (geo-targeted county/precinct cluster)",
    "youtube_trueview": "YouTube TrueView (skippable in-stream)",
    "youtube_bumper":   "YouTube Bumper (6s non-skippable)",
    "ctv":              "Connected TV (Hulu, Roku, programmatic)",
    "programmatic":     "Programmatic display (awareness only)",
    "tiktok":           "TikTok (in-feed video)",
    "snap":             "Snap (under-25 registration)",
    "spotify_audio":    "Spotify and Pandora (30s civic audio)",
    "podcast_hostread": "Podcast host-reads (civic-aligned shows)",
    "sms":              "SMS (peer-to-peer)",
    "print":            "Print (door literature, mailers)",
}

# Persuasion CPM lookup by digital channel (used to estimate point lift).
CHANNEL_TO_PERSUASION_CPM = {
    "meta_feed":        PERSUASION_CPM["meta_video"],
    "youtube_trueview": PERSUASION_CPM["youtube"],
    "youtube_bumper":   PERSUASION_CPM["youtube"],
    "ctv":              PERSUASION_CPM["ctv"],
}

# ---------------------------------------------------------------------------
# Trigger keywords (callers use this to decide whether to invoke the estimator)
# ---------------------------------------------------------------------------

PAID_MEDIA_KEYWORDS = re.compile(
    r"\b("
    r"paid\s*media|paid\s*ads?|digital\s*ad|digital\s*media|"
    r"meta\s*ad|facebook\s*ad|instagram\s*ad|"
    r"youtube\s*ad|youtube|ctv|connected\s*tv|programmatic|"
    r"cpm|ctr|impressions?|frequency\s*cap|"
    r"ad\s*budget|media\s*budget|media\s*plan|media\s*mix|"
    r"channel\s*mix|spend\s*plan|"
    r"boost(?:ed|ing)?(?:\s+\w+){0,2}\s+post|"
    r"tiktok\s*ad|snap\s*ad|spotify\s*ad|"
    # Platform names paired with budget/spend/buy/ad-shaped intent.
    r"meta\s+(?:and|or|\+)?\s*(?:youtube|instagram|facebook|tiktok|ctv)|"
    r"(?:on|via)\s+meta\b"
    r")\b",
    re.IGNORECASE,
)


def query_mentions_paid_media(query: Optional[str]) -> bool:
    """True if the query asks for paid-digital planning."""
    if not query:
        return False
    return bool(PAID_MEDIA_KEYWORDS.search(query))


# ---------------------------------------------------------------------------
# Core estimator
# ---------------------------------------------------------------------------


def _select_tier(budget: float) -> dict:
    """Return the tier dict for a given total program budget."""
    for upper, digital_mix, non_digital_mix, label in TIER_ALLOCATIONS:
        if budget <= upper:
            return {
                "upper":             upper,
                "digital_mix":       digital_mix,
                "non_digital_mix":   non_digital_mix,
                "label":             label,
            }
    # Should be unreachable because the last tier is float('inf').
    last = TIER_ALLOCATIONS[-1]
    return {
        "upper":           last[0],
        "digital_mix":     last[1],
        "non_digital_mix": last[2],
        "label":           last[3],
    }


def _apply_in_language_discount(cpm_low: float, cpm_high: float) -> tuple[float, float]:
    """Apply the 22.5 percent in-language inventory discount."""
    factor = 1.0 - IN_LANGUAGE_DISCOUNT
    return (cpm_low * factor, cpm_high * factor)


def _impressions(spend: float, cpm_low: float, cpm_high: float) -> dict:
    """Convert spend at a CPM range into impressions (low, mid, high)."""
    if cpm_low <= 0 or cpm_high <= 0 or spend <= 0:
        return {"low": 0, "mid": 0, "high": 0}
    # Higher CPM means fewer impressions, so flip the bounds.
    impressions_low  = (spend / cpm_high) * 1000.0
    impressions_high = (spend / cpm_low)  * 1000.0
    impressions_mid  = (impressions_low + impressions_high) / 2.0
    return {
        "low":  int(impressions_low),
        "mid":  int(impressions_mid),
        "high": int(impressions_high),
    }


def _reach_from_impressions(impressions_mid: int, channel: str,
                            flight_weeks: int = DEFAULT_FLIGHT_WEEKS) -> int:
    """
    Approximate unique reach assuming impressions are distributed at the
    per-flight frequency cap. This is a planning estimate, not a measured reach.
    """
    cap = FREQUENCY_CAPS.get(channel)
    if not cap or impressions_mid <= 0:
        return 0
    avg_freq = min(cap["per_flight"], cap["per_week"] * flight_weeks)
    if avg_freq <= 0:
        return 0
    return int(impressions_mid / avg_freq)


def _points_lift(spend: float, channel: str) -> Optional[dict]:
    """Estimated percentage-point lift in target universe at this spend."""
    rng = CHANNEL_TO_PERSUASION_CPM.get(channel)
    if not rng or spend <= 0:
        return None
    cpm_low, cpm_high = rng
    # spend / cpm gives the number of points; flip the bounds (higher cost per
    # point means fewer points).
    return {
        "low":  round(spend / cpm_high, 2),
        "high": round(spend / cpm_low,  2),
    }


def estimate_paid_media(
    budget: float,
    query: Optional[str] = None,
    language_intent: Optional[str] = None,
    district_label: Optional[str] = None,
    target_universe: Optional[int] = None,
    flight_weeks: int = DEFAULT_FLIGHT_WEEKS,
) -> Optional[dict]:
    """
    Build a paid-media plan for the given total program budget.

    Args:
      budget:            total program budget in USD. The estimator does not
                         allocate the full budget to digital; it follows the
                         file-07 mix that includes SMS and print.
      query:             original user query, for context only. The caller is
                         responsible for deciding whether to invoke this
                         estimator using query_mentions_paid_media().
      language_intent:   ISO 639-1 code (e.g. "es", "vi", "ko"). When set, the
                         English CPMs are reduced by 22.5 percent to reflect
                         in-language inventory pricing in the same DMA.
      district_label:    free-text label used in the narrative.
      target_universe:   approximate persuadable universe size. When set,
                         reach is capped at the universe and a saturation
                         warning is added if frequency exceeds the per-flight
                         cap.
      flight_weeks:      assumed flight length for reach math. Default 6.

    Returns:
      dict with keys:
        budget, tier_label, language_intent, district_label, flight_weeks,
        digital_spend_total, non_digital_spend_total,
        channels: list of dicts with channel, label, spend, cpm_low, cpm_high,
                  impressions, reach, points_lift,
        non_digital: list of dicts with channel, label, spend,
        total_points_lift_low, total_points_lift_high,
        notes: list of strings (frequency caps, in-language discount, etc.)
      Returns None when budget is None or non-positive.
    """
    if budget is None or budget <= 0:
        return None

    tier = _select_tier(budget)
    digital_mix     = tier["digital_mix"]
    non_digital_mix = tier["non_digital_mix"]

    # Total digital spend = sum of digital mix percentages * budget.
    digital_share_pct = sum(digital_mix.values())
    digital_spend     = budget * digital_share_pct

    in_language = bool(language_intent and language_intent.lower() != "en")

    channels: list[dict] = []
    total_lift_low  = 0.0
    total_lift_high = 0.0

    for channel_key, share_pct in digital_mix.items():
        spend = budget * share_pct
        cpm_low, cpm_high = CPM_RANGES.get(channel_key, (0.0, 0.0))
        if in_language:
            cpm_low, cpm_high = _apply_in_language_discount(cpm_low, cpm_high)

        impressions = _impressions(spend, cpm_low, cpm_high)
        reach_uncapped = _reach_from_impressions(
            impressions["mid"], channel_key, flight_weeks
        )
        # Cap reach at the persuadable universe when one is provided. Without
        # the cap the math implies reaching audiences much larger than the
        # district, which mis-states the program. Saturation flag fires when
        # the cap had to apply.
        saturated = False
        if target_universe and reach_uncapped > target_universe:
            reach = target_universe
            saturated = True
        else:
            reach = reach_uncapped
        lift = _points_lift(spend, channel_key)

        if lift:
            total_lift_low  += lift["low"]
            total_lift_high += lift["high"]

        channels.append({
            "channel":      channel_key,
            "label":        CHANNEL_LABELS.get(channel_key, channel_key),
            "share_pct":    round(share_pct * 100, 1),
            "spend":        round(spend, 2),
            "cpm_low":      round(cpm_low,  2),
            "cpm_high":     round(cpm_high, 2),
            "impressions":  impressions,
            "reach":        reach,
            "reach_uncapped": reach_uncapped,
            "saturated":    saturated,
            "points_lift":  lift,
        })

    non_digital_spend = budget * sum(non_digital_mix.values())
    non_digital = [
        {
            "channel":   k,
            "label":     CHANNEL_LABELS.get(k, k),
            "share_pct": round(v * 100, 1),
            "spend":     round(budget * v, 2),
        }
        for k, v in non_digital_mix.items()
    ]

    notes = [
        "Frequency caps applied per file 07: Meta 3/wk, YouTube 4/wk, CTV 5/wk.",
        "Reach is a planning estimate: impressions divided by per-flight cap.",
        "Persuasion-point lift uses Analyst Institute civic-engagement RCTs (2018-2024).",
    ]
    if target_universe:
        any_saturated = any(c.get("saturated") for c in channels)
        if any_saturated:
            notes.append(
                f"Saturation warning: at this budget some channels would deliver "
                f"more impressions than the {target_universe:,}-voter persuadable "
                f"universe can absorb at frequency caps. Consider rebalancing "
                f"toward doors and SMS, or expanding the universe."
            )
    if in_language:
        notes.append(
            f"In-language inventory ({language_intent}) priced 22.5 percent under English CPM "
            "in the same DMA (file 07: 15-30 percent range)."
        )
    if budget < 25_000:
        notes.append(
            "At this budget, doors do the persuasion work. Treat digital as awareness "
            "and reinforcement; do not expect measurable digital-only lift."
        )
    if budget >= 75_000:
        notes.append(
            "CTV is concentrated in the last 2 weeks of the flight; budget shown is "
            "tier total, not weekly pacing."
        )

    return {
        "budget":               round(budget, 2),
        "tier_label":           tier["label"],
        "language_intent":      language_intent,
        "in_language_pricing":  in_language,
        "district_label":       district_label,
        "target_universe":      target_universe,
        "flight_weeks":         flight_weeks,
        "digital_spend_total":  round(digital_spend, 2),
        "non_digital_spend_total": round(non_digital_spend, 2),
        "channels":             channels,
        "non_digital":          non_digital,
        "total_points_lift_low":  round(total_lift_low,  2),
        "total_points_lift_high": round(total_lift_high, 2),
        "notes":                notes,
        "source":               "Powerbuilder corpus file 07: paid-media digital benchmarks",
    }


# ---------------------------------------------------------------------------
# Narrative formatter
# ---------------------------------------------------------------------------


def _fmt_dollars(x: float) -> str:
    return f"${x:,.0f}"


def _fmt_int(x: int) -> str:
    return f"{x:,}"


def format_paid_media_section(estimate: dict) -> str:
    """Render a paid-media plan as a markdown section for the budget memo."""
    if not estimate:
        return ""

    lines: list[str] = []
    lines.append("### Paid Media Plan")
    lines.append("")
    district_bit = (
        f" for {estimate['district_label']}" if estimate.get("district_label") else ""
    )
    lines.append(
        f"Tier: **{estimate['tier_label']}**. Total program budget "
        f"**{_fmt_dollars(estimate['budget'])}**{district_bit}, "
        f"of which **{_fmt_dollars(estimate['digital_spend_total'])}** is paid digital "
        f"and **{_fmt_dollars(estimate['non_digital_spend_total'])}** is SMS and print."
    )
    if estimate.get("in_language_pricing"):
        lines.append(
            f"In-language pricing applied for `{estimate['language_intent']}`: "
            f"22.5 percent under English CPM in the same DMA."
        )
    lines.append("")

    # Digital channel table
    lines.append("**Digital channels**")
    lines.append("")
    lines.append("| Channel | Spend | Share | CPM (low - high) | Impressions (mid) | Est. Reach | Est. Lift (pp) |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in estimate["channels"]:
        cpm = f"${c['cpm_low']:.0f} - ${c['cpm_high']:.0f}"
        imp_mid = _fmt_int(c["impressions"]["mid"])
        reach   = _fmt_int(c["reach"]) if c["reach"] else "n/a"
        lift    = (
            f"{c['points_lift']['low']:.2f} - {c['points_lift']['high']:.2f}"
            if c.get("points_lift") else "n/a"
        )
        lines.append(
            f"| {c['label']} | {_fmt_dollars(c['spend'])} | {c['share_pct']:.0f}% | "
            f"{cpm} | {imp_mid} | {reach} | {lift} |"
        )
    lines.append("")

    # Non-digital line items
    if estimate["non_digital"]:
        lines.append("**Non-digital allocation (in same total)**")
        lines.append("")
        for n in estimate["non_digital"]:
            lines.append(
                f"- {n['label']}: {_fmt_dollars(n['spend'])} ({n['share_pct']:.0f}%)"
            )
        lines.append("")

    # Total lift summary
    if estimate["total_points_lift_low"] or estimate["total_points_lift_high"]:
        lines.append(
            f"**Estimated total persuasion lift in target universe:** "
            f"{estimate['total_points_lift_low']:.2f} to "
            f"{estimate['total_points_lift_high']:.2f} percentage points "
            f"(digital channels only; door knocks and direct mail are tracked "
            f"separately in the operational program above)."
        )
        lines.append("")

    # Notes
    if estimate["notes"]:
        lines.append("**Notes**")
        lines.append("")
        for n in estimate["notes"]:
            lines.append(f"- {n}")
        lines.append("")

    lines.append(
        "Source: Powerbuilder corpus file 07 (paid media digital benchmarks), "
        "distilled from Analyst Institute civic-engagement RCTs, "
        "AdImpact 2024 civic spend tracker, Pew Research platform reach, "
        "APIAVote and AAPI Data in-language inventory surveys."
    )

    return "\n".join(lines)
