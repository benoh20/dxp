"""
Demo carousel tile configuration (Milestone G).

The empty-state landing page on /chat/ shows a row of clickable tiles that
pre-fill the prompt textarea. Until now those tiles were hardcoded in
templates/chat.html; this module pulls them out so anyone (including
non-engineers reviewing the demo deck) can edit prompts without touching
the template.

Schema (per tile):

    id        — short unique slug used for the click-tracking data attribute
                and for tests; lowercase, alphanumeric + dashes
    chip      — short kicker label (1 to 2 words). Examples: 'Full plan',
                'Win number', 'Voter file'.
    chip_kind — color variant. Must be one of CHIP_KINDS below; the template
                maps each to a `.demo-tile-chip--<kind>` modifier class so
                the tile chips stay color-coded.
    headline  — single-line headline rendered in bold. Avoid em dashes per
                house style; use commas, parentheses, or colons.
    preview   — supporting line under the headline. One sentence.
    prompt    — the full text dropped into the textarea on click. Multi-line
                strings are fine; the JS handler trims trailing whitespace.

To add a tile: append a dict at the bottom of DEMO_TILES.
To remove a tile: delete its dict.
To reorder: rearrange the list — display order matches list order.
To recolor: change chip_kind to one of CHIP_KINDS.

C3 note: keep the prompt phrasing nonpartisan-friendly. Issue framing and
'leans Democratic' style hedges are fine; explicit candidate or party
boost language is not.
"""
from __future__ import annotations

from typing import TypedDict


# Allowed chip color variants. Each maps to a .demo-tile-chip--<kind> CSS
# rule already shipped in chat.html. If you want a new color, add the rule
# in the stylesheet first, then add the kind here.
CHIP_KINDS: tuple[str, ...] = ("plan", "win", "opp", "lang", "vf", "social")


class DemoTile(TypedDict):
    """Static type for a single carousel tile."""
    id:        str
    chip:      str
    chip_kind: str
    headline:  str
    preview:   str
    prompt:    str


DEMO_TILES: list[DemoTile] = [
    {
        "id":        "gwinnett-gotv-latinx",
        "chip":      "Full plan",
        "chip_kind": "plan",
        "headline":  "Gwinnett GOTV, Latinx 18 to 35",
        "preview":   "Spanish door-knock script and a CSV target list.",
        "prompt": (
            "Build a Gwinnett County GOTV plan targeting Latinx voters "
            "age 18 to 35. Generate a Spanish door-knock script and give "
            "me a CSV of the target list."
        ),
    },
    {
        "id":        "win-number-ga07-midterm",
        "chip":      "Win number",
        "chip_kind": "win",
        "headline":  "Win number for GA-07, midterm",
        "preview":   "Quick lookup, shows CVAP and turnout math.",
        "prompt": (
            "What is the win number for Georgia's 7th Congressional "
            "District in a midterm cycle? Show me the math."
        ),
    },
    {
        "id":        "opp-research-ga06-gop",
        "chip":      "Opposition",
        "chip_kind": "opp",
        "headline":  "GOP opponent in GA-06",
        "preview":   "Vulnerabilities and contrast angles from research books.",
        "prompt": (
            "Pull opposition research on the Republican candidate in "
            "Georgia's 6th Congressional District. Give me the top "
            "vulnerabilities and three contrast messaging angles."
        ),
    },
    {
        "id":        "vietnamese-text-aapi",
        "chip":      "Multilingual",
        "chip_kind": "lang",
        "headline":  "Vietnamese text to AAPI voters",
        "preview":   "Tests language detection plus messaging agent.",
        "prompt": (
            "Draft a Vietnamese-language text message to AAPI voters in "
            "Gwinnett about early voting locations and hours."
        ),
    },
    {
        "id":        "social-pack-ga07-youth",
        "chip":      "Social pack",
        "chip_kind": "social",
        "headline":  "Social media pack for GA-07 youth turnout",
        "preview":   "Meta mobilization, YouTube persuasion, TikTok hook, grounded in research.",
        "prompt": (
            "Build a social media pack for Georgia's 7th Congressional "
            "District youth turnout (18 to 29). Generate the Meta post, "
            "YouTube script, and TikTok script alongside the standard "
            "canvassing and phone outputs. Lead with cost-of-living framing "
            "where it fits the research."
        ),
    },
    {
        "id":        "voterfile-segment-and-match",
        "chip":      "Voter file",
        "chip_kind": "vf",
        "headline":  "Segment my list and match scripts",
        "preview":   "Uses the attached synthetic voterfile in demo mode.",
        "prompt": (
            "Segment my voter file by age cohort and party, then match "
            "each segment to the right canvassing script and turnout tactic."
        ),
    },
]


def get_demo_tiles() -> list[DemoTile]:
    """
    Return the configured tile list, validated.

    Defensive on purpose: if a downstream edit drops a required field or
    picks an unknown chip_kind, we filter the offender out and log via
    print() rather than crashing the empty-state. The carousel just shows
    fewer tiles instead of the whole page erroring.
    """
    safe: list[DemoTile] = []
    required = ("id", "chip", "chip_kind", "headline", "preview", "prompt")
    seen_ids: set[str] = set()
    for tile in DEMO_TILES:
        if not all(tile.get(k) for k in required):
            print(f"[demo_tiles] dropping tile with missing fields: {tile.get('id', '?')}")
            continue
        if tile["chip_kind"] not in CHIP_KINDS:
            print(f"[demo_tiles] dropping tile {tile['id']!r}: unknown chip_kind {tile['chip_kind']!r}")
            continue
        if tile["id"] in seen_ids:
            print(f"[demo_tiles] dropping duplicate id {tile['id']!r}")
            continue
        seen_ids.add(tile["id"])
        safe.append(tile)
    return safe
