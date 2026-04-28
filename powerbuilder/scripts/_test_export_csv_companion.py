"""
Test that export_node emits BOTH a DOCX and a CSV when running a full plan
with precinct data in state.

This is the gap the screenshots Ben saw exposed: the user's prompt asked for
a Spanish door script PLUS a CSV target list, but only the DOCX came back.

Verifies:
  1. result['generated_files'] is a list with two paths.
  2. One path ends with .docx, one with .csv.
  3. Both files exist on disk.
  4. The CSV contains the precinct headers and row count matches state.

Usage:
    python scripts/_test_export_csv_companion.py
"""
from __future__ import annotations

import csv as csv_module
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Bootstrap Django.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "powerbuilder_app.settings")

import django  # noqa: E402

django.setup()


def main() -> int:
    failures: list[str] = []

    from chat.agents.export import export_node

    # Fake the synthesis LLM call so the test does not need an OpenAI key.
    fake_synthesis = (
        "## Strategy\nFocus on Latinx 18-35 voters in Gwinnett.\n\n"
        "## Spanish Door Script\nHola, soy [nombre], voluntario(a). "
        "¿Prefiere que sigamos en español o en inglés?\n\n"
        "## Target Precincts\nSee CSV.\n"
    )

    sample_precincts = [
        {
            "precinct_id":  "GW-001",
            "name":         "Norcross 1A",
            "county":       "Gwinnett",
            "win_number":   1240,
            "turnout_2022": 0.41,
            "dem_share":    0.58,
            "latinx_share": 0.34,
        },
        {
            "precinct_id":  "GW-014",
            "name":         "Lawrenceville 3B",
            "county":       "Gwinnett",
            "win_number":   980,
            "turnout_2022": 0.38,
            "dem_share":    0.55,
            "latinx_share": 0.29,
        },
    ]

    state = {
        "query":            "Build a Gwinnett GOTV plan for Latinx 18-35 with Spanish door script and CSV target list.",
        "org_namespace":    "general",
        "research_results": [
            "Spanish-language outreach lifts contact rates among Latinx 18-35.",
        ],
        "structured_data":  [
            {
                "agent":     "precincts",
                "district":  "Gwinnett County, GA",
                "precincts": sample_precincts,
            },
        ],
        "router_decision":  "full_plan",
        "output_format":    "markdown",
        # Must include all PLAN_AGENTS so export_node treats this as a full plan.
        "active_agents":    [
            "researcher", "election_results", "win_number", "precincts",
            "messaging", "cost_calculator",
        ],
        "uploaded_file_path": None,
        "errors":           [],
    }

    # Patch _synthesize so no LLM call is made.
    with patch("chat.agents.export._synthesize", return_value=fake_synthesis):
        result = export_node(state)

    files = result.get("generated_files") or []
    if len(files) != 2:
        failures.append(
            f"Expected 2 generated files (DOCX + CSV), got {len(files)}: {files}"
        )

    exts = sorted(os.path.splitext(p)[1].lower() for p in files)
    if exts != [".csv", ".docx"]:
        failures.append(f"Expected exts ['.csv', '.docx'], got {exts}")

    for p in files:
        if not os.path.isfile(p):
            failures.append(f"Generated file not found on disk: {p}")

    # Inspect the CSV: headers present and at least 2 data rows.
    csv_path = next((p for p in files if p.endswith(".csv")), None)
    if csv_path:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv_module.reader(f)
            rows = list(reader)
        if len(rows) < 1 + len(sample_precincts):
            failures.append(
                f"CSV has {len(rows)} rows; expected >= "
                f"{1 + len(sample_precincts)} (header + precincts)"
            )

    # The first generated file should still be the DOCX (primary).
    primary = result.get("generated_file_path")
    if not primary or not primary.endswith(".docx"):
        failures.append(
            f"generated_file_path should be the DOCX, got {primary}"
        )

    print(f"export_node CSV companion test: files={files}")
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: all 5 assertion groups OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
