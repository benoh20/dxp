# powerbuilder/chat/tests/test_utilities.py
"""
Live integration tests for the three core utility modules:
  - chat/utils/district_standardizer.py
  - chat/utils/census_vars.py
  - chat/utils/data_fetcher.py

Tests hit real APIs — no mocking. Requires CENSUS_API_KEY and FEC_API_KEY
to be present in the .env file at the project root.

Test district: Virginia's 7th Congressional District
  State FIPS  : 51
  GEOID       : 5107 (state_fips "51" + district "07")
  FEC office  : H (House)
  2022 cycle  : Abigail Spanberger (D) held the seat

Run from the project root:
  python -m chat.tests.test_utilities
  — or —
  python chat/tests/test_utilities.py
"""

from dotenv import load_dotenv
load_dotenv()  # must be before any import that reads env vars

import os
import re
import sys

# ── Path setup ───────────────────────────────────────────────────────────────
# Supports running as a module (python -m) or directly (python path/to/file.py)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from chat.utils.district_standardizer import GeographyStandardizer
from chat.utils.census_vars import (
    VOTER_DEMOGRAPHICS,
    CENSUS_DEMOGRAPHICS,
    SOCIOECONOMIC_VARS,
    SOCIAL_SERVICES_VARS,
)
from chat.utils.data_fetcher import DataFetcher

# ── Test helpers ─────────────────────────────────────────────────────────────

_GREEN  = "\033[32m"
_RED    = "\033[31m"
_YELLOW = "\033[33m"
_RESET  = "\033[0m"

_results: list = []   # (test_name, passed: bool)


def check(name: str, actual, expected, *, note: str = "") -> bool:
    """
    Compare actual vs expected, print a PASS/FAIL line, and record the result.
    Pass note="" for additional context shown on PASS lines too.
    """
    passed = actual == expected
    tag    = f"{_GREEN}PASS{_RESET}" if passed else f"{_RED}FAIL{_RESET}"
    _results.append((name, passed))

    print(f"  [{tag}] {name}")
    if not passed:
        print(f"         expected : {expected!r}")
        print(f"         actual   : {actual!r}")
    elif note:
        print(f"         {_YELLOW}{note}{_RESET}")
    return passed


def check_true(name: str, value: bool, *, note: str = "") -> bool:
    """Convenience wrapper: pass when value is truthy."""
    return check(name, bool(value), True, note=note)


def section(title: str):
    print(f"\n{'-' * 64}")
    print(f"  {title}")
    print("-" * 64)


def skip(name: str, reason: str):
    print(f"  [{_YELLOW}SKIP{_RESET}] {name}")
    print(f"         {reason}")
    _results.append((name, None))   # None = skipped


# ── 1. district_standardizer.py ──────────────────────────────────────────────

section("1 · district_standardizer.py — Input Format Tests")

# ---------------------------------------------------------------------------
# Minimal input parser that simulates what an LLM extraction step produces.
# In production the LLM handles free-form input; here we test that the
# standardizer itself produces the right GEOID once state+number are isolated.
# ---------------------------------------------------------------------------
def _parse_district_input(text: str) -> tuple:
    """
    Extract (state_token, district_num) from common user-facing formats.
    Test-only helper — not part of the production standardizer.

    Handled patterns
    ----------------
    "VA-07"          →  ("VA", 7)
    "Virginia-7"     →  ("Virginia", 7)
    "VA District 7"  →  ("VA", 7)
    "Virginia 7"     →  ("Virginia", 7)
    """
    text = text.strip()
    # "XX-NN" or "State Name-N"
    m = re.match(r"^([A-Za-z ]+?)\s*-\s*0*(\d+)$", text)
    if m:
        return m.group(1).strip(), int(m.group(2))
    # "State [District] N"
    m = re.match(r"^([A-Za-z ]+?)\s+(?:[Dd]istrict\s+)?0*(\d+)$", text)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return text, 0


EXPECTED_FIPS  = "51"
EXPECTED_GEOID = "5107"

# 1a. Common free-text formats → should all resolve to GEOID 5107
for user_input in [
    "VA District 7",
    "Virginia 7",
    "VA-07",
    "virginia-7",
    "Virginia District 7",
]:
    state_tok, dist_num = _parse_district_input(user_input)
    geoid = GeographyStandardizer.convert_to_geoid(state_tok, dist_num, "congressional")
    check(f'"{user_input}" -> GEOID', geoid, EXPECTED_GEOID)

# 1b. Direct STATE_FIPS lookup
check('STATE_FIPS.get("va")      == "51"', GeographyStandardizer.STATE_FIPS.get("va"),       EXPECTED_FIPS)
check('STATE_FIPS.get("virginia")== "51"', GeographyStandardizer.STATE_FIPS.get("virginia"), EXPECTED_FIPS)
check(
    'STATE_FIPS.get("VA") == None (keys are lowercase; callers must .lower())',
    GeographyStandardizer.STATE_FIPS.get("VA"),
    None,
    note="Expected — production agents call .lower() before lookup",
)

# 1c. Unknown state returns error dict, not a string
bad = GeographyStandardizer.convert_to_geoid("Neverland", 7, "congressional")
check_true('convert_to_geoid("Neverland", 7) returns error dict', isinstance(bad, dict))

# 1d. State-senate and state-house GEOID formats
check(
    'convert_to_geoid("Virginia", 7, "state_senate") == "51S007"',
    GeographyStandardizer.convert_to_geoid("Virginia", 7, "state_senate"),
    "51S007",
)
check(
    'convert_to_geoid("Virginia", 7, "state_house") == "51H007"',
    GeographyStandardizer.convert_to_geoid("Virginia", 7, "state_house"),
    "51H007",
)

# ── 2. census_vars.py ────────────────────────────────────────────────────────

section("2 · census_vars.py — Variable Code Mapping Tests")

# Known correct Census API codes — verify the mapping is intact and complete.
KNOWN_VARS = {
    # CENSUS_DEMOGRAPHICS
    "total_population": "B01003_001E",
    "total_cvap":       "B29001_001E",
    "median_age":       "B01002_001E",
    "white":            "B03002_003E",
    "black":            "B03002_004E",
    "hispanic":         "B03002_012E",
    # SOCIOECONOMIC_VARS
    "homeowners":       "B25003_002E",
    "renters":          "B25003_003E",
    "median_income":    "B19013_001E",
    "poverty_total":    "B17001_002E",
    "unemployed":       "S2301_C04_001E",
    "bach_degree":      "B15003_022E",
    # SOCIAL_SERVICES_VARS
    "food_stamps_snap": "B22001_002E",
}

for friendly_name, expected_code in KNOWN_VARS.items():
    actual_code = VOTER_DEMOGRAPHICS.get(friendly_name)
    check(f'VOTER_DEMOGRAPHICS["{friendly_name}"]', actual_code, expected_code)

# Sanity-check: VOTER_DEMOGRAPHICS is the union of the three sub-dicts
all_keys = (
    set(CENSUS_DEMOGRAPHICS)
    | set(SOCIOECONOMIC_VARS)
    | set(SOCIAL_SERVICES_VARS)
)
check_true(
    "VOTER_DEMOGRAPHICS contains all keys from the three sub-dicts",
    set(VOTER_DEMOGRAPHICS) >= all_keys,
    note=f"{len(VOTER_DEMOGRAPHICS)} total keys in VOTER_DEMOGRAPHICS",
)

# ── 3. data_fetcher.py — Census API ──────────────────────────────────────────

section("3a · data_fetcher.py — Census API (VA Congressional Districts)")

if not os.environ.get("CENSUS_API_KEY"):
    skip("Census API live call", "CENSUS_API_KEY not set in environment")
else:
    print("  Fetching Census CVAP data for Virginia congressional districts…")
    census_results = DataFetcher.get_census_data("51", ["total_cvap"], "congressional")

    check_true("Census API returned a non-empty list", isinstance(census_results, list) and len(census_results) > 0)

    # Surface any API-level error
    if census_results and "error" in census_results[0]:
        check("No error in Census response", census_results[0]["error"], None)
    else:
        check_true("First result is a dict with keys", isinstance(census_results[0], dict) and len(census_results[0]) > 1)

        # Find VA-07 specifically
        CVAP_CODE = "B29001_001E"
        va07 = next(
            (r for r in census_results if r.get("congressional district") == "07"),
            None,
        )
        check_true('VA-07 row found in results (congressional district == "07")', va07 is not None)

        if va07:
            cvap_raw = va07.get(CVAP_CODE)
            check_true(
                f"VA-07 CVAP code ({CVAP_CODE}) is present and non-zero",
                cvap_raw is not None and float(cvap_raw) > 0,
                note=f"VA-07 CVAP: {cvap_raw}",
            )

            # Sanity-check: VA-07 CVAP should be in a plausible range for a
            # mid-sized congressional district (~400K–800K citizens 18+)
            cvap_val = float(cvap_raw)
            check_true(
                "VA-07 CVAP is in a plausible range (400,000 – 800,000)",
                400_000 <= cvap_val <= 800_000,
                note=f"Actual: {cvap_val:,.0f}",
            )

# ── 4. data_fetcher.py — FEC API ─────────────────────────────────────────────

section("3b · data_fetcher.py — FEC API (VA-07, House, cycle 2022)")

if not os.environ.get("FEC_API_KEY"):
    skip("FEC API live call", "FEC_API_KEY not set in environment")
else:
    print("  Fetching FEC disbursement data for VA-07, cycle 2022…")
    fec_results = DataFetcher.get_district_finances("VA", "07", "H", 2022)

    # DataFetcher returns a list on success, a dict {"error": ...} on failure
    check_true("FEC API returned a list (not an error dict)", isinstance(fec_results, list))

    if isinstance(fec_results, list):
        check_true("FEC API returned at least one candidate", len(fec_results) >= 1,
                   note=f"Candidates found: {[r.get('name') for r in fec_results]}")

        if fec_results:
            first = fec_results[0]
            # Verify the normalised schema from DataFetcher.get_district_finances()
            for field in ("name", "party", "total_receipts", "total_disbursements", "cash_on_hand"):
                check_true(f'First result has "{field}" field', field in first)

            # Total disbursements should be a dollar-formatted string, not zero
            disbursements = first.get("total_disbursements", "$0")
            check_true(
                "total_disbursements is a non-zero dollar amount",
                disbursements != "$0.00" and disbursements.startswith("$"),
                note=f"Top candidate: {first.get('name')} — {disbursements}",
            )
    elif isinstance(fec_results, dict) and "error" in fec_results:
        check("No error in FEC response", fec_results["error"], None)


# ── Summary ───────────────────────────────────────────────────────────────────

section("Summary")

passed  = sum(1 for _, ok in _results if ok is True)
failed  = sum(1 for _, ok in _results if ok is False)
skipped = sum(1 for _, ok in _results if ok is None)
total   = len(_results)

print(f"\n  Total : {total}")
print(f"  {_GREEN}Passed{_RESET}: {passed}")
if failed:
    print(f"  {_RED}Failed{_RESET}: {failed}")
if skipped:
    print(f"  {_YELLOW}Skipped{_RESET}: {skipped}")
print()

if failed:
    print(f"  {_RED}FAILED TESTS:{_RESET}")
    for name, ok in _results:
        if ok is False:
            print(f"    ✗ {name}")
    sys.exit(1)
else:
    print(f"  {_GREEN}All checks passed.{_RESET}" if not skipped
          else f"  {_GREEN}All non-skipped checks passed.{_RESET}")
    sys.exit(0)
