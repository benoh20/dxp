import pandas as pd
from ..utils.data_fetcher import DataFetcher

class PrecinctsAgent:
    """
    The Spatial Architect: Maps Census demographics onto Voting Precincts
    using dasymetric reaggregation (weighting).
    """

    @staticmethod
    def get_top_precincts(state_fips, district_id, target_metric="total_vap", top_n=10):
        # 1. Fetch Block Group data for the district
        # We pull at the 'precinct' level toggle we built in DataFetcher
        raw_bg_data = DataFetcher.get_census_data(state_fips, [target_metric], geo_level="precinct")
        
        # 2. Load the Crosswalk (Relationship File)
        # These files map Block Group GEOIDs to Precinct IDs with a 'weight'
        try:
            crosswalk = pd.read_csv(f"data/crosswalks/{state_fips}_bg_to_precinct.csv")
        except FileNotFoundError:
            return {"error": "Crosswalk file missing. Run ingestor for this state first."}

        # 3. Apply Dasymetric Weights
        # We merge Census data with the Crosswalk and multiply: 
        # (Block Group Population) * (Weight) = (Precinct Contribution)
        bg_df = pd.DataFrame(raw_bg_data)
        merged = bg_df.merge(crosswalk, left_on='GEOID', right_on='bg_geoid')
        
        merged['weighted_val'] = merged[target_metric].astype(float) * merged['weight']
        
        # 4. Reaggregate (Sum by Precinct)
        precinct_totals = merged.groupby('precinct_id')['weighted_val'].sum().reset_index()
        
        # Sort and return top targets
        top_targets = precinct_totals.sort_values(by='weighted_val', ascending=False).head(top_n)
        return top_targets.to_dict(orient='records')