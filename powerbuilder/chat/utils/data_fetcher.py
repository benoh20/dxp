# powerbuilder/chat/utils/data_fetcher.py
import os
import requests
from .census_vars import (
    VOTER_DEMOGRAPHICS,
    RACE_TABLES,
    SEX_AGE_OFFSETS,
    ANCESTRY_MAP
 ) # Your human-readable map

class DataFetcher:
    
    @staticmethod
    def search_census_variables(keyword, year=2022, dataset="acs/acs5"):
        """
        Discovery Tool: Searches the Census metadata for variables matching a keyword.
        """
        url = f"https://api.census.gov/data/{year}/{dataset}/variables.json"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                variables = response.json().get("variables", {})
                # Filter variables where keyword appears in the label or concept
                matches = {
                    k: v['label'] for k, v in variables.items() 
                    if keyword.lower() in v.get('label', '').lower() 
                    or keyword.lower() in v.get('concept', '').lower()
                }
                return matches
            return {"error": f"Failed to reach discovery tool: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def get_census_data(state_fips, variables=["total_pop"], geo_level="county"):
        """
        Dynamic Fetcher with Geography Toggle.
        Supports: 'statewide', 'county', 'congressional', 'state_senate', 'state_house', 'precinct'
        """
        # 1. GEOGRAPHY TOGGLE: Friendly names to Census API predicates
        GEO_MAP = {
            "statewide": {"for": "state:*", "in": ""},
            "county": {"for": "county:*", "in": f"state:{state_fips}"},
            "congressional": {"for": "congressional district:*", "in": f"state:{state_fips}"},
            "state_senate": {"for": "state legislative district (upper chamber):*", "in": f"state:{state_fips}"},
            "state_house": {"for": "state legislative district (lower chamber):*", "in": f"state:{state_fips}"},
            "precinct": {"for": "block group:*", "in": f"state:{state_fips}"}
        }

        geo_config = GEO_MAP.get(geo_level, GEO_MAP["county"])

        # 2. TRANSLATION: Human keys -> Census codes
        census_codes = [VOTER_DEMOGRAPHICS.get(v, v) for v in variables]
        get_vars = "NAME," + ",".join(census_codes)
        
        url = f"https://api.census.gov/data/2022/acs/acs5"
        params = {
            "get": get_vars,
            "for": geo_config["for"],
            "key": os.getenv("CENSUS_API_KEY")
        }
        
        if geo_config["in"]:
            params["in"] = geo_config["in"]

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            headers = data[0]
            return [dict(zip(headers, row)) for row in data[1:]]
        except Exception as e:
            return [{"error": f"Census API failure: {str(e)}"}]
    
    @staticmethod
    def get_computed_census_data(state_fips, race, gender, age_min, age_max, geo_level="precinct"):
        """
        Dynamically constructs and sums Census variables for specific intersections.
        """
        table_prefix = RACE_TABLES.get(race, "B01001") # Default to total pop
        
        # Logic to determine which row offsets to pull based on age_min/age_max
        required_offsets = DataFetcher._resolve_age_offsets(gender, age_min, age_max)
        
        # Construct codes: e.g., "B01001I_012E", "B01001I_013E"
        census_codes = [f"{table_prefix}_{offset}E" for offset in required_offsets]
        
        # Fetch raw data for all codes
        raw_results = DataFetcher.get_census_data(state_fips, variables=census_codes, geo_level=geo_level)
        
        # SUMMING LOGIC: Create a new key 'target_population' by adding the codes
        for row in raw_results:
            row['target_population'] = sum(float(row.get(code, 0)) for code in census_codes)
            
        return raw_results
    
    @staticmethod
    def _resolve_age_offsets(gender, age_min, age_max):
        """
        Helper to find all row offsets that fit within an age range.
        Ex: 30 to 50 would return ['012', '013', '014'] for Male.
        """
        # Mapping ranges to their descriptive keys in SEX_AGE_OFFSETS
        range_map = [
            (0, 4, "under_5"), (5, 9, "5_9"), (10, 14, "10_14"), 
            (15, 17, "15_17"), (18, 19, "18_19"), (20, 20, "20"), 
            (21, 21, "21"), (22, 24, "22_24"), (25, 29, "25_29"), 
            (30, 34, "30_34"), (35, 44, "35_44"), (45, 54, "45_54"), 
            (55, 64, "55_64"), (65, 74, "65_74"), (75, 84, "75_84"), (85, 200, "85_plus")
        ]
        
        selected_offsets = []
        for low, high, key in range_map:
            # If the bracket overlaps with the user's range, we grab the offset
            if not (high < age_min or low > age_max):
                offset = SEX_AGE_OFFSETS[gender].get(key)
                if offset:
                    selected_offsets.append(offset)
        return selected_offsets

    @staticmethod
    def get_custom_crosstab(state_fips, race="total", gender="female", age_min=18, age_max=99, geo_level="precinct"):
        """
        The Master Query Node: Builds any Race x Gender x Age combination.
        """
        table = RACE_TABLES.get(race, "B01001")
        offsets = DataFetcher._resolve_age_offsets(gender, age_min, age_max)
        
        # Build the codes: e.g., "B01001B_022E"
        codes = [f"{table}_{o}E" for o in offsets]
        
        # Fetch raw data
        raw_data = DataFetcher.get_census_data(state_fips, variables=codes, geo_level=geo_level)
        
        # Sum the results for the LLM
        for row in raw_data:
            row['target_pop'] = sum(float(row.get(c, 0)) for c in codes if row.get(c))
            
        return raw_data

    ############## FEC / CAMPAIGN FINANCE DATA INGESTION -- FEDERAL ONLY ##############
    @staticmethod
    def get_district_finances(state, district_number, office_type, cycle=2024):
        """
        Fetches spending and receipts for a specific race.
        Office types: 'H' (House), 'S' (Senate), 'P' (Presidential)
        """
        api_key = os.getenv("FEC_API_KEY")
        base_url = "https://api.open.fec.gov/v1/candidates/totals/"
        
        params = {
            "api_key": api_key,
            "cycle": cycle,
            "state": state,
            "district": district_number,
            "office": office_type,
            "sort": "-receipts"
        }
        
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            raw_data = response.json().get("results", [])
            # NORMALIZATION: Simplify for the LLM
            normalized = []
            for candidate in raw_data:
                normalized.append({
                    "name": candidate.get("name"),
                    "party": candidate.get("party_full"),
                    "total_receipts": f"${candidate.get('receipts', 0):,.2f}",
                    "total_disbursements": f"${candidate.get('disbursements', 0):,.2f}",
                    "cash_on_hand": f"${candidate.get('cash_on_hand_end_period', 0):,.2f}"
                })
            return normalized
        return {"error": "FEC API unreachable"}



# ADD IN OPPO RESEARCH API FROM 21ST CENTURY BRIDGE
# ADD IN ELECTION RESULTS API KEY


