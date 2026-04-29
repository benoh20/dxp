"""
Milestone K: A/B scaffolding for messaging outputs.

Scope:
  - Two-variant generation (Variant A vs Variant B) for the social-leaning
    formats: text_script, digital_copy, meta_post, youtube_script,
    tiktok_script. Variants share the same research grounding and target
    audience but differ on a single deliberate axis (hook, CTA verb,
    framing) so a campaign can run a clean comparison.
  - Sample-size math grounded in the two-proportion z-test, expressed in
    language a campaign manager (not a statistician) can act on.

Effect-size grounding:
  Coppock, Hill & Vavreck. "The Small Effects of Political Advertising."
  APSR 2024 — best-fit MDE for political ad copy is roughly 1 to 3 percentage
  points on intent-to-vote / intent-to-share metrics. That informs both the
  default MDE we suggest in the UI and the warning copy we emit when the
  user asks for a smaller effect than the literature can typically detect.

This module is intentionally self-contained — no LangChain imports — so it
can be unit-tested without spinning up the agent graph.
"""
from __future__ import annotations

import math
from typing import Iterable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The five formats where A/B testing is operationally cheap (single-message
# delivery, easy click/open attribution). Door knocks and mail narratives are
# excluded because per-contact attribution is messy enough that you cannot
# cleanly resolve which variant moved the dial.
AB_ELIGIBLE_FORMATS: tuple[str, ...] = (
    "text_script",
    "digital_copy",
    "meta_post",
    "youtube_script",
    "tiktok_script",
)

# Default A/B knobs surfaced in the UI. Aligned with Coppock APSR 2024
# baseline: a 2 pp MDE on a 5% baseline click-through is a reasonable
# default for a campaign-scale test.
DEFAULT_BASELINE_RATE: float = 0.05   # 5% baseline conversion (click, RSVP, etc.)
DEFAULT_MDE: float           = 0.02   # 2 percentage points absolute lift
DEFAULT_ALPHA: float         = 0.05   # 95% confidence
DEFAULT_POWER: float         = 0.80   # 80% statistical power

# Two-variant test by default. Three+ arms is out of scope for K (more arms
# means a multiple-comparisons correction we don't surface yet).
NUM_VARIANTS: int = 2


# ---------------------------------------------------------------------------
# Defensive normalization
# ---------------------------------------------------------------------------

def _normalize_ab_test(value) -> bool:
    """
    Coerce an ab_test value (typically from request.POST or state) into a
    plain bool. Treats common truthy strings ("1", "true", "yes", "on")
    as True; everything else (including None and unknown strings) as False.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _coerce_rate(value, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """
    Defensive numeric coercion for a probability. Out-of-range or
    unparseable values fall back to ``default``.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not (lo < v < hi):
        return default
    return v


# ---------------------------------------------------------------------------
# Sample-size math
# ---------------------------------------------------------------------------

# Z-scores for the most common alpha/power pairs. Pre-computed so the math
# is deterministic without depending on scipy at runtime.
_Z_TABLE = {
    # alpha (two-sided): z_{1-alpha/2}
    0.10: 1.6449,
    0.05: 1.9600,
    0.01: 2.5758,
}
_Z_POWER_TABLE = {
    # power: z_{power}
    0.80: 0.8416,
    0.85: 1.0364,
    0.90: 1.2816,
    0.95: 1.6449,
}


def _z_alpha_two_sided(alpha: float) -> float:
    """Look up the two-sided z-score for the given alpha. Falls back to 0.05."""
    return _Z_TABLE.get(round(alpha, 2), _Z_TABLE[0.05])


def _z_power(power: float) -> float:
    """Look up the z-score for the given target power. Falls back to 0.80."""
    return _Z_POWER_TABLE.get(round(power, 2), _Z_POWER_TABLE[0.80])


def compute_sample_size(
    baseline_rate: float = DEFAULT_BASELINE_RATE,
    mde: float = DEFAULT_MDE,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> int:
    """
    Per-variant sample size for a two-proportion z-test, two-sided.

    Formula:
        n_per_arm = ((z_{1-alpha/2} * sqrt(2*p_bar*(1-p_bar))
                      + z_power * sqrt(p1*(1-p1) + p2*(1-p2)))**2)
                    / mde**2

    where p1 = baseline_rate, p2 = baseline_rate + mde, p_bar = (p1+p2)/2.

    Args:
        baseline_rate: control-arm conversion rate, 0 < p < 1
        mde:           minimum detectable effect, absolute pp difference
        alpha:         two-sided significance level
        power:         target statistical power

    Returns:
        Smallest integer sample size per variant, rounded up. The total
        messages-to-send is `n_per_arm * NUM_VARIANTS`. Always at least 1
        per arm so callers don't have to special-case zero.
    """
    p1 = _coerce_rate(baseline_rate, DEFAULT_BASELINE_RATE)
    delta = float(mde) if mde is not None else DEFAULT_MDE
    if delta <= 0:
        delta = DEFAULT_MDE
    p2 = min(0.999, p1 + delta)
    p_bar = (p1 + p2) / 2.0

    z_a = _z_alpha_two_sided(alpha)
    z_b = _z_power(power)

    pooled = math.sqrt(2.0 * p_bar * (1.0 - p_bar))
    unpooled = math.sqrt(p1 * (1.0 - p1) + p2 * (1.0 - p2))
    numerator = (z_a * pooled + z_b * unpooled) ** 2
    n_per_arm = numerator / (delta ** 2)
    return max(1, math.ceil(n_per_arm))


def compute_total_messages(per_variant: int, num_variants: int = NUM_VARIANTS) -> int:
    """Total messages to send across both arms."""
    return max(1, int(per_variant)) * max(1, int(num_variants))


# ---------------------------------------------------------------------------
# Prompt + output formatting
# ---------------------------------------------------------------------------

# Prompt fragment injected into messaging_node when ab_test=True. Tells the
# LLM to produce two distinct variants per eligible format, separated by
# explicit subsection markers we then parse out.
AB_PROMPT_INSTRUCTION: str = (
    "A/B TEST MODE: For each of the eligible formats below — "
    "text_script, digital_copy, meta_post, youtube_script, tiktok_script — "
    "produce TWO distinct variants (Variant A and Variant B) within the "
    "section. Variants must share the same research grounding and target "
    "audience but differ deliberately on a single axis: hook, CTA verb, "
    "or framing (not all three at once). Use the subsection markers below "
    "exactly as printed:\n"
    "    >>> VARIANT A <<<\n"
    "    ... copy for variant A ...\n"
    "    >>> VARIANT B <<<\n"
    "    ... copy for variant B ...\n"
    "After both variants, in italics, name the single axis you varied "
    "(e.g., \"*Variant axis: CTA verb (Pledge vs RSVP).*\"). For the "
    "non-eligible formats (canvassing_script, phone_script, mail_narrative) "
    "produce a single version as usual.\n"
)


def is_ab_eligible(format_key: str) -> bool:
    """Is this format eligible for A/B variant generation?"""
    return format_key in AB_ELIGIBLE_FORMATS


def split_variants(content: str) -> dict[str, str]:
    """
    Parse a single section body into {"A": ..., "B": ..., "axis": ...}.

    Tolerant of:
      - missing variant markers (returns the whole content under "A")
      - missing axis annotation (returns axis="")
      - extra whitespace, mixed case in the markers
    """
    if not content:
        return {"A": "", "B": "", "axis": ""}

    # Normalize markers to a canonical token so case/whitespace doesn't bite us.
    text = content
    a_marker = ">>> VARIANT A <<<"
    b_marker = ">>> VARIANT B <<<"

    if a_marker not in text and b_marker not in text:
        # No variant markers — caller was probably non-eligible or the LLM
        # ignored the instruction. Return the content as variant A only.
        return {"A": text.strip(), "B": "", "axis": ""}

    a_idx = text.find(a_marker)
    b_idx = text.find(b_marker)

    # Tolerate B-before-A by swapping.
    if a_idx < 0:
        a_idx, b_idx = b_idx, a_idx
        a_marker, b_marker = b_marker, a_marker

    if b_idx < 0:
        # Only Variant A present — no B yet.
        a_body = text[a_idx + len(a_marker):].strip()
        return {"A": a_body, "B": "", "axis": _extract_axis(a_body)}

    a_body = text[a_idx + len(a_marker): b_idx].strip()
    b_and_after = text[b_idx + len(b_marker):].strip()
    axis_line = _extract_axis(b_and_after)
    # Strip the axis annotation off the end of B's body so it isn't double-printed.
    b_body = _strip_axis_annotation(b_and_after).strip()
    return {"A": a_body, "B": b_body, "axis": axis_line}


def _extract_axis(text: str) -> str:
    """
    Pull out the italic axis annotation if present. We accept both
    ``*Variant axis: ...*`` and ``_Variant axis: ..._`` markdown forms.
    """
    if not text:
        return ""
    needles = ("*Variant axis:", "_Variant axis:")
    for needle in needles:
        idx = text.find(needle)
        if idx >= 0:
            tail = text[idx:]
            # Stop at the first newline or end of string.
            line_end = tail.find("\n")
            line = tail if line_end < 0 else tail[:line_end]
            return line.strip()
    return ""


def _strip_axis_annotation(text: str) -> str:
    """Remove the `*Variant axis: ...*` line so it isn't echoed inside variant B."""
    axis = _extract_axis(text)
    if not axis:
        return text
    return text.replace(axis, "").rstrip()


def format_ab_math_block(
    baseline_rate: float = DEFAULT_BASELINE_RATE,
    mde: float = DEFAULT_MDE,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> str:
    """
    Build the campaign-friendly Markdown block that goes at the top of an
    A/B-mode messaging output. Gives the user the per-variant + total
    message volume they need to hit the requested MDE.

    Plain language only — no LaTeX, no statistical jargon beyond what a
    campaign manager already says ("baseline", "lift", "confidence").
    """
    p1 = _coerce_rate(baseline_rate, DEFAULT_BASELINE_RATE)
    delta = mde if mde and mde > 0 else DEFAULT_MDE
    n_per = compute_sample_size(p1, delta, alpha, power)
    n_total = compute_total_messages(n_per)

    baseline_pct = p1 * 100.0
    mde_pp       = delta * 100.0
    alpha_pct    = (1.0 - alpha) * 100.0
    power_pct    = power * 100.0

    lines = [
        "**A/B sample-size math (per format):**",
        f"  - Baseline conversion: {baseline_pct:.1f}%  (e.g., click-through, RSVP, or reply rate)",
        f"  - Minimum detectable lift: {mde_pp:.1f} percentage points",
        f"  - Confidence: {alpha_pct:.0f}%   |   Power: {power_pct:.0f}%",
        f"  - **{n_per:,} messages per variant**, {n_total:,} total across A and B",
        "",
        "*Grounded in Coppock, Hill, and Vavreck (APSR 2024): political ad effects "
        "are typically 1 to 3 percentage points, so any MDE smaller than 1 pp "
        "will need an order of magnitude more sample.*",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "AB_ELIGIBLE_FORMATS",
    "AB_PROMPT_INSTRUCTION",
    "DEFAULT_BASELINE_RATE",
    "DEFAULT_MDE",
    "DEFAULT_ALPHA",
    "DEFAULT_POWER",
    "NUM_VARIANTS",
    "_normalize_ab_test",
    "is_ab_eligible",
    "compute_sample_size",
    "compute_total_messages",
    "split_variants",
    "format_ab_math_block",
]
