# powerbuilder/chat/utils/election_ingestor.py
import pandas as pd
import requests
import os

class ElectionDataUtility:
    # We now point to the massive House and Senate master files
    MEDSL_URLS = {
        "house": "https://raw.githubusercontent.com/MEDSL/constituency-returns/master/data/house_results_1976_2024.csv",
        "senate": "https://raw.githubusercontent.com/MEDSL/constituency-returns/master/data/senate_results_1976_2024.csv"
    }

    @staticmethod
    def sync_national_database(years=range(2014, 2026, 2)) -> bool:
        """
        Synchronizes historical data for all 50 states for a decade of cycles.
        """
        data_dir = "data/election_results"
        os.makedirs(data_dir, exist_ok=True)
        
        print(f"🚀 Starting National Sync for cycles: {list(years)}")
        
        try:
            # 1. Fetch Master Datasets
            house_df = pd.read_csv(ElectionDataUtility.MEDSL_URLS["house"])
            senate_df = pd.read_csv(ElectionDataUtility.MEDSL_URLS["senate"])
            
            # 2. Filter for our specific decade
            house_df = house_df[house_df['year'].isin(years)]
            senate_df = senate_df[senate_df['year'].isin(years)]

            # 3. Save by State FIPS to keep runtime files small
            # (FIPS list includes 01-56, excluding non-state territories as needed)
            all_fips = house_df['state_fips'].unique()
            
            for fips in all_fips:
                fips_str = str(int(fips)).zfill(2)
                state_path = f"{data_dir}/{fips_str}_master.csv"
                
                # Combine house and senate for this state
                state_house = house_df[house_df['state_fips'] == fips]
                state_senate = senate_df[senate_df['state_fips'] == fips]
                
                master_state_df = pd.concat([state_house, state_senate])
                master_state_df.to_csv(state_path, index=False)
                print(f"✅ Synced {fips_str}")

            return True
        except Exception as e:
            print(f"❌ Sync failed: {e}")
            return False