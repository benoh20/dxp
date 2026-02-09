# powerbuilder/chat/utils/data_fetcher.py
import os
import requests
from .census_vars import VOTER_DEMOGRAPHICS # Your human-readable map

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
    def get_census_data(state_fips, variables=["total_pop"], geo_level="county:*"):
        """
        Dynamic Fetcher: Uses human-readable keys or direct Census codes.
        """
        # Map human-readable names to codes using your census_vars.py map
        census_codes = [VOTER_DEMOGRAPHICS.get(v, v) for v in variables]
        get_vars = "NAME," + ",".join(census_codes)
        
        url = f"https://api.census.gov/data/2022/acs/acs5"
        params = {
            "get": get_vars,
            "for": geo_level,
            "in": f"state:{state_fips}",
            "key": os.getenv("CENSUS_API_KEY")
        }
        # ... (rest of your request logic)

# ADD IN OPPO RESEARCH API FROM 21ST CENTURY BRIDGE
# ADD IN ELECTION RESULTS API KEY
# ADD IN FEC / CAMPAIGN FINANCE API KEY?

