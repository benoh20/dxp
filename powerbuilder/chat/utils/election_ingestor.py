# powerbuilder/chat/utils/election_ingestor.py
import pandas as pd
import os
from .data_fetcher import DataFetcher
from .census_vars import VOTER_DEMOGRAPHICS

CVAP_KEY = VOTER_DEMOGRAPHICS.get("total_cvap", "B29001_001E")

class ElectionDataUtility:
    MEDSL_URLS = {
        # constituency-returns: House + Senate 1976-2018 (files at repo root, not in data/)
        "house":       "https://raw.githubusercontent.com/MEDSL/constituency-returns/master/1976-2018-house.csv",
        "senate":      "https://raw.githubusercontent.com/MEDSL/constituency-returns/master/1976-2018-senate.csv",
        # 2024-elections-official: pre-aggregated national Senate state-level file
        # No House equivalent at root; no 2022 equivalent (only per-state zip files) — TODO
        "senate_2024": "https://raw.githubusercontent.com/MEDSL/2024-elections-official/main/2024-senate-state.csv",
    }

    @staticmethod
    def _fetch_cvap_lookup(fips_str, office_type):
        """
        Returns a dict mapping district identifier → CVAP float.
          House:  {district_int: cvap}   e.g. {7: 450000.0}
          Senate: {"statewide": cvap}
        """
        if office_type == "senate":
            # geo_level="statewide" returns all states; filter for ours by "state" key
            rows = DataFetcher.get_census_data(fips_str, ["total_cvap"], geo_level="statewide")
            state_row = next(
                (r for r in rows if "error" not in r and r.get("state") == fips_str),
                None
            )
            if state_row:
                return {"statewide": float(state_row.get(CVAP_KEY, 0))}
            return {}

        else:  # house — congressional district level
            rows = DataFetcher.get_census_data(fips_str, ["total_cvap"], geo_level="congressional")
            lookup = {}
            for row in rows:
                if "error" in row:
                    continue
                # Census returns zero-padded district string e.g. "07"; convert to int for matching
                dist_num = int(row.get("congressional district", 0))
                lookup[dist_num] = float(row.get(CVAP_KEY, 0))
            return lookup

    @staticmethod
    def _standardize_district(district_val, fips_str, office_type):
        """
        Converts MEDSL district values to the GEOID format used by district_standardizer.py.
          House:  int 7  → "5107"  (state_fips + zero-padded 2-digit district number)
          Senate: any    → "statewide"
        """
        if office_type == "senate":
            return "statewide"
        try:
            dist_num = int(district_val)
            return f"{fips_str}{dist_num:02d}"
        except (ValueError, TypeError):
            return str(district_val)

    @staticmethod
    def _load_senate_2024(years):
        """
        Loads 2024 Senate results from MEDSL 2024-elections-official.
        The 2024 repo uses uppercase "GEN" for stage and has no district column.
        Returns a deduplicated DataFrame with columns: year, state_fips, district,
        totalvotes, office_type — or an empty DataFrame if 2024 is not in years.
        """
        if 2024 not in years:
            return pd.DataFrame()
        try:
            df = pd.read_csv(ElectionDataUtility.MEDSL_URLS["senate_2024"], low_memory=False)
            df = df[df["stage"].str.upper() == "GEN"]
            df = df[df["year"] == 2024]
            df["district"] = "statewide"
            df["state_fips"] = df["state_fips"].astype(int)
            df = (
                df.groupby(["year", "state_fips", "district"], as_index=False)["totalvotes"]
                .first()
            )
            df["office_type"] = "senate"
            print(f"  Loaded {len(df)} 2024 Senate races from supplemental source.")
            return df
        except Exception as e:
            print(f"  Warning: Could not load 2024 Senate supplemental data: {e}")
            return pd.DataFrame()

    @staticmethod
    def sync_national_database(years=range(2014, 2026, 2), state_fips=None) -> bool:
        """
        Synchronizes historical election data and writes per-state master CSVs.

        Sources:
          - MEDSL constituency-returns (1976-2018): House + Senate
          - MEDSL 2024-elections-official: Senate state-level only
          - 2022: per-state zip files only, no national aggregate — TODO

        Pipeline:
          1. Fetch and filter MEDSL source CSVs to general elections + target years.
          2. Supplement Senate with 2024 data if 2024 is in scope.
          3. Deduplicate to one row per race (source files have one row per candidate).
          4. Standardize district to GEOID format matching district_standardizer.py:
               House  → "{state_fips}{district:02d}"  e.g. "5107"
               Senate → "statewide"
          5. Join Census CVAP and compute turnout_pct.
          6. Write data/election_results/{fips}_master.csv.

        Pass state_fips (e.g. "51") to sync a single state instead of all 50.
        """
        data_dir = "data/election_results"
        os.makedirs(data_dir, exist_ok=True)

        print(f"Starting national sync for cycles: {list(years)}")

        try:
            # 1. Fetch MEDSL constituency-returns (1976-2018)
            # latin-1 encoding required: MEDSL CSVs contain non-UTF-8 bytes (e.g. accented candidate names)
            house_df = pd.read_csv(ElectionDataUtility.MEDSL_URLS["house"], low_memory=False, encoding="latin-1")
            senate_df = pd.read_csv(ElectionDataUtility.MEDSL_URLS["senate"], low_memory=False, encoding="latin-1")

            # 2. General elections only (exclude primaries, runoffs)
            house_df = house_df[house_df["stage"] == "gen"]
            senate_df = senate_df[senate_df["stage"] == "gen"]

            # 3. Filter for target years
            house_df = house_df[house_df["year"].isin(years)]
            senate_df = senate_df[senate_df["year"].isin(years)]

            # 4. Deduplicate to one row per race (source has one row per candidate;
            #    totalvotes is constant across all candidates in a race so we take first)
            house_races = (
                house_df
                .groupby(["year", "state_fips", "district"], as_index=False)["totalvotes"]
                .first()
            )
            house_races["office_type"] = "house"

            senate_races = (
                senate_df
                .groupby(["year", "state_fips", "district"], as_index=False)["totalvotes"]
                .first()
            )
            senate_races["office_type"] = "senate"

            # 5. Supplement Senate with 2024 data if in scope
            senate_2024 = ElectionDataUtility._load_senate_2024(years)
            if not senate_2024.empty:
                senate_races = pd.concat([senate_races, senate_2024], ignore_index=True)
                senate_races = (
                    senate_races
                    .groupby(["year", "state_fips", "district"], as_index=False)["totalvotes"]
                    .first()
                )
                senate_races["office_type"] = "senate"

            # 6. Optionally filter to a single state
            if state_fips is not None:
                fips_int = int(state_fips)
                house_races = house_races[house_races["state_fips"] == fips_int]
                senate_races = senate_races[senate_races["state_fips"] == fips_int]
                all_fips = [fips_int]
            else:
                all_fips = house_races["state_fips"].unique()

            # 7. Per-state: standardize district, join CVAP, compute turnout_pct, save
            for fips in all_fips:
                fips_str = str(int(fips)).zfill(2)
                state_path = f"{data_dir}/{fips_str}_master.csv"

                state_house = house_races[house_races["state_fips"] == fips].copy()
                state_senate = senate_races[senate_races["state_fips"] == fips].copy()

                # Fetch CVAP lookups from Census (2022 ACS5)
                house_cvap = ElectionDataUtility._fetch_cvap_lookup(fips_str, "house")
                senate_cvap = ElectionDataUtility._fetch_cvap_lookup(fips_str, "senate")

                # Standardize district column to GEOID format
                state_house["district"] = state_house["district"].apply(
                    lambda d: ElectionDataUtility._standardize_district(d, fips_str, "house")
                )
                state_senate["district"] = "statewide"

                # Join CVAP: extract the numeric district suffix from GEOID for house lookup
                state_house["cvap"] = state_house["district"].apply(
                    lambda geoid: house_cvap.get(int(geoid[len(fips_str):]), 0)
                )
                state_senate["cvap"] = senate_cvap.get("statewide", 0)

                # Compute turnout_pct (None if CVAP is zero or missing)
                for df_part in [state_house, state_senate]:
                    df_part["turnout_pct"] = df_part.apply(
                        lambda r: round(r["totalvotes"] / r["cvap"], 4) if r["cvap"] > 0 else None,
                        axis=1
                    )

                master_df = pd.concat([state_house, state_senate], ignore_index=True)
                master_df.to_csv(state_path, index=False)
                print(f"  Synced {fips_str} ({len(master_df)} races)")

            return True

        except Exception as e:
            print(f"Sync failed: {e}")
            return False
