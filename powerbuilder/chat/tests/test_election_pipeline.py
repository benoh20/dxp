# powerbuilder/chat/tests/test_election_pipeline.py
"""
Live integration tests for the election data pipeline:
  1. election_ingestor.py  -- sync Virginia (FIPS 51), verify output CSV
  2. win_number.py         -- calculate win math for VA-07 congressional, 2026

Tests hit real APIs (Census CVAP). Requires CENSUS_API_KEY in .env.
MEDSL election data is fetched from public GitHub -- no key required.

NOTE ON MEDSL COVERAGE:
  House data  : 1976-2018 only (constituency-returns repo)
  Senate data : 1976-2018 + 2024 supplemental
  2022 House  : not available in any national aggregate -- per-state zip only (TODO)
  Impact      : 2026 midterm climate years [2014, 2018, 2022] will only have
                2014 and 2018 House turnout data; avg_turnout_pct reflects two cycles.

Run from the project root:
  python -m chat.tests.test_election_pipeline
  -- or --
  python chat/tests/test_election_pipeline.py
"""

from dotenv import load_dotenv
load_dotenv()  # must be before any import that reads env vars

import os
import sys
import math

# -- Path setup ---------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pandas as pd
from chat.utils.election_ingestor import ElectionDataUtility
from chat.agents.win_number import WinNumberAgent

# -- Test helpers -------------------------------------------------------------

_GREEN  = "\033[32m"
_RED    = "\033[31m"
_YELLOW = "\033[33m"
_RESET  = "\033[0m"

_results: list = []


def check(name: str, actual, expected, *, note: str = "") -> bool:
    passed = actual == expected
    tag = f"{_GREEN}PASS{_RESET}" if passed else f"{_RED}FAIL{_RESET}"
    _results.append((name, passed))
    print(f"  [{tag}] {name}")
    if not passed:
        print(f"         expected : {expected!r}")
        print(f"         actual   : {actual!r}")
    elif note:
        print(f"         {_YELLOW}{note}{_RESET}")
    return passed


def check_true(name: str, value: bool, *, note: str = "") -> bool:
    return check(name, bool(value), True, note=note)


def section(title: str):
    print(f"\n{'-' * 64}")
    print(f"  {title}")
    print("-" * 64)


def skip(name: str, reason: str):
    print(f"  [{_YELLOW}SKIP{_RESET}] {name}")
    print(f"         {reason}")
    _results.append((name, None))


def info(label: str, value):
    """Print an informational line (not a pass/fail check)."""
    print(f"  [INFO] {label}: {value}")


# -- Constants ----------------------------------------------------------------

STATE_FIPS   = "51"
DISTRICT_ID  = "5107"   # VA-07 congressional GEOID
TARGET_YEAR  = 2026
CSV_PATH     = f"data/election_results/{STATE_FIPS}_master.csv"

REQUIRED_COLUMNS = [
    "year", "state_fips", "district",
    "totalvotes", "office_type", "cvap", "turnout_pct",
]

# Climate years for a midterm (2026 % 4 != 0, 2026 % 2 == 0)
MIDTERM_CLIMATE_YEARS = [2014, 2018, 2022]


# =============================================================================
# 1. election_ingestor.py -- Sync Virginia
# =============================================================================

section("1 - election_ingestor.py -- Sync Virginia (FIPS 51)")

has_census_key = bool(os.environ.get("CENSUS_API_KEY"))

if not has_census_key:
    skip(
        "sync_national_database (VA)",
        "CENSUS_API_KEY not set -- sync requires Census CVAP join. "
        "Will use existing CSV if present.",
    )
    master_df = pd.read_csv(CSV_PATH) if os.path.exists(CSV_PATH) else None

else:
    print("  Syncing Virginia election data (MEDSL public CSVs + Census CVAP join)...")
    print("  House coverage: 1976-2018 only; 2020/2022/2024 House data not available.")
    print()

    success = ElectionDataUtility.sync_national_database(
        years=range(2014, 2026, 2),   # [2014, 2016, 2018, 2020, 2022, 2024]
        state_fips=STATE_FIPS,
    )
    check_true("sync_national_database() returned True", success)
    master_df = pd.read_csv(CSV_PATH) if os.path.exists(CSV_PATH) else None


# -- Verify CSV exists --------------------------------------------------------

check_true(f"CSV exists at {CSV_PATH}", os.path.exists(CSV_PATH))

if master_df is not None:

    # -- Required columns -----------------------------------------------------
    section("1a - CSV column validation")
    for col in REQUIRED_COLUMNS:
        check_true(f'Column "{col}" present in master CSV', col in master_df.columns)

    info("Total rows in CSV", len(master_df))
    info("Columns", list(master_df.columns))
    info("Years present", sorted(master_df["year"].unique().tolist()))
    info("Office types", master_df["office_type"].unique().tolist())

    # -- VA-07 row validation -------------------------------------------------
    section("1b - VA-07 district rows (district == '5107')")

    va07 = master_df[master_df["district"] == DISTRICT_ID].copy()
    check_true(f'Rows found for district "{DISTRICT_ID}"', len(va07) > 0,
               note=f"{len(va07)} rows")

    if len(va07) > 0:
        va07_years = sorted(va07["year"].tolist())
        info("VA-07 years present", va07_years)

        # Print full VA-07 table for manual audit
        display_cols = [c for c in ["year", "district", "totalvotes", "cvap", "turnout_pct"] if c in va07.columns]
        print()
        print("  VA-07 historical rows (all cycles present):")
        print(va07[display_cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        print()

        # turnout_pct checks
        has_any_turnout = va07["turnout_pct"].notna().any()
        check_true("At least one VA-07 row has turnout_pct", has_any_turnout)

        valid_rows = va07.dropna(subset=["turnout_pct"])
        if len(valid_rows) > 0:
            all_in_range = ((valid_rows["turnout_pct"] > 0) & (valid_rows["turnout_pct"] <= 1.0)).all()
            check_true(
                "All non-null turnout_pct values are in (0.0, 1.0]",
                all_in_range,
                note=f"values: {valid_rows['turnout_pct'].round(4).tolist()}",
            )

        # Climate-year availability note
        available_climate = [y for y in MIDTERM_CLIMATE_YEARS if y in va07_years]
        missing_climate   = [y for y in MIDTERM_CLIMATE_YEARS if y not in va07_years]
        info(
            "2026 midterm climate years [2014, 2018, 2022] available in CSV",
            available_climate,
        )
        if missing_climate:
            info(
                "Missing climate years (MEDSL coverage gap -- expected for House)",
                missing_climate,
            )

        check_true(
            "At least one midterm climate year present for VA-07",
            len(available_climate) >= 1,
            note=f"win_number will average over: {available_climate}",
        )


# =============================================================================
# 2. win_number.py -- VA-07 Congressional, 2026
# =============================================================================

section("2 - win_number.py -- VA-07 Congressional, target year 2026")

if not has_census_key:
    skip(
        "WinNumberAgent.calculate_win_math",
        "CENSUS_API_KEY not set -- Census CVAP call required.",
    )

elif not os.path.exists(CSV_PATH):
    skip(
        "WinNumberAgent.calculate_win_math",
        f"No master CSV at {CSV_PATH} -- run sync first.",
    )

else:
    print("  Running WinNumberAgent.calculate_win_math()...")
    print(f"  state_fips={STATE_FIPS!r}  district_type='congressional'")
    print(f"  district_id={DISTRICT_ID!r}  target_year={TARGET_YEAR}  victory_margin=0.52")
    print(f"  2026 climate: midterm -> relevant years {MIDTERM_CLIMATE_YEARS}")
    print(f"  NOTE: only years present in CSV will contribute to avg_turnout_pct")
    print()

    result = WinNumberAgent.calculate_win_math(
        state_fips    = STATE_FIPS,
        district_type = "congressional",
        district_id   = DISTRICT_ID,
        target_year   = TARGET_YEAR,
        victory_margin= 0.52,
    )

    # Print full dict for manual audit
    print("  Full result dict:")
    for k, v in result.items():
        print(f"    {k}: {v}")
    print()

    # -- Error check ----------------------------------------------------------
    check_true(
        "No 'error' key in result",
        "error" not in result,
        note=result.get("error", ""),
    )

    if "error" not in result:
        win_number        = result.get("win_number")
        projected_turnout = result.get("projected_turnout")
        voter_universe    = result.get("voter_universe_cvap")
        avg_turnout_pct   = result.get("avg_turnout_pct")
        victory_margin    = result.get("victory_margin")
        historical_ctx    = result.get("historical_context", "")

        # -- Field presence ---------------------------------------------------
        section("2a - Field presence and types")

        check_true("win_number is present", win_number is not None)
        check_true("projected_turnout is present", projected_turnout is not None)
        check_true("voter_universe_cvap is present", voter_universe is not None)
        check_true("avg_turnout_pct is present", avg_turnout_pct is not None)
        check_true("historical_context is present", bool(historical_ctx))

        # -- No NaN in any numeric field --------------------------------------
        for field, val in result.items():
            if isinstance(val, float):
                check_true(f'"{field}" is not NaN', not math.isnan(val))

        # -- Logical sanity checks --------------------------------------------
        section("2b - Logical sanity checks")

        if all(v is not None for v in [win_number, projected_turnout, voter_universe]):

            check_true(
                "win_number is a positive integer",
                isinstance(win_number, int) and win_number > 0,
                note=f"win_number = {win_number:,}",
            )

            check_true(
                "projected_turnout is a positive integer",
                isinstance(projected_turnout, int) and projected_turnout > 0,
                note=f"projected_turnout = {projected_turnout:,}",
            )

            check_true(
                "projected_turnout < voter_universe_cvap",
                projected_turnout < voter_universe,
                note=f"{projected_turnout:,} < {voter_universe:,}",
            )

            check_true(
                "win_number < projected_turnout",
                win_number < projected_turnout,
                note=f"{win_number:,} < {projected_turnout:,}",
            )

            # Turnout rate sanity: congressional midterm typically 35-65%
            check_true(
                "avg_turnout_pct in plausible midterm range (0.25 to 0.75)",
                0.25 <= avg_turnout_pct <= 0.75,
                note=f"avg_turnout_pct = {avg_turnout_pct:.4f} ({avg_turnout_pct:.1%})",
            )

            # CVAP sanity: VA-07 should be near the 542,664 we saw in test_utilities
            check_true(
                "voter_universe_cvap in plausible range (400,000 - 800,000)",
                400_000 <= voter_universe <= 800_000,
                note=f"voter_universe_cvap = {voter_universe:,}",
            )

            # Math verification: win_number ~= projected_turnout * victory_margin
            # Allow ±1 vote: calculate_win_math multiplies the pre-truncation float by
            # victory_margin, so int(float_turnout * margin) can differ by 1 from
            # int(int_turnout * margin) depending on the fractional part.
            expected_wn = int(projected_turnout * victory_margin)
            check_true(
                f"win_number within 1 vote of int(projected_turnout * victory_margin)  [{expected_wn:,}]",
                abs(win_number - expected_wn) <= 1,
                note=f"win_number={win_number:,}, expected~={expected_wn:,}",
            )

        # -- Full intermediate audit ------------------------------------------
        section("2c - Intermediate values (manual audit)")

        if all(v is not None for v in [win_number, projected_turnout, voter_universe, avg_turnout_pct]):
            print()
            info("voter_universe_cvap ", f"{voter_universe:>10,}  (2022 ACS5 CVAP for VA-07)")
            info("avg_turnout_pct     ", f"{avg_turnout_pct:>10.4f}  ({avg_turnout_pct:.1%})  [{historical_ctx}]")
            info("projected_turnout   ", f"{projected_turnout:>10,}  (cvap x avg_turnout_pct)")
            info("victory_margin      ", f"{victory_margin:>10}  ({victory_margin:.0%} of projected vote)")
            info("win_number          ", f"{win_number:>10,}  (projected_turnout x victory_margin)")
            print()

            # Show what midterm years actually contributed
            if master_df is not None and "turnout_pct" in master_df.columns:
                va07_climate = master_df[
                    (master_df["district"] == DISTRICT_ID) &
                    (master_df["year"].isin(MIDTERM_CLIMATE_YEARS))
                ][["year", "totalvotes", "cvap", "turnout_pct"]]
                if not va07_climate.empty:
                    print("  Midterm climate rows that fed avg_turnout_pct:")
                    print(va07_climate.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
                    print()
                else:
                    print("  No midterm climate rows found in master CSV for VA-07.")
                    print()


# =============================================================================
# Summary
# =============================================================================

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
            print(f"    x {name}")
    sys.exit(1)
else:
    print(
        f"  {_GREEN}All checks passed.{_RESET}" if not skipped
        else f"  {_GREEN}All non-skipped checks passed.{_RESET}"
    )
    sys.exit(0)
