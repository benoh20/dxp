# powerbuilder/chat/agents/win_number.py
import pandas as pd
from ..utils.data_fetcher import DataFetcher

class WinNumberAgent:
    @staticmethod
    def calculate_win_math(state_fips, district_type, district_id, target_year=2026):
        # 1. Get Census Scale (Universe)
        census_data = DataFetcher.get_census_data(state_fips, ["total_vap"], district_type)
        # Simple lookup for the specific district's population
        district_pop_row = next((d for d in census_data if district_id in d.get('NAME', '')), census_data[0])
        total_vap = int(district_pop_row.get('total_vap', 0))

        # 2. Load Historical Data (Decade of results)
        path = f"data/election_results/{state_fips}_master.csv"
        try:
            df = pd.read_csv(path)
            # Filter for the specific district
            history = df[df['district'] == district_id]
        except FileNotFoundError:
            return {"error": "Historical data not synced. Run election_ingestor first."}

        # 3. SMART AVERAGE: Match the 'climate' of the target year
        # 2026 is a Midterm. We want to weight 2018 and 2022 more heavily.
        if target_year % 4 == 0:
            relevant_years = [2016, 2020, 2024] # Presidential Climate
        elif target_year % 2 != 0:
            relevant_years = [2015, 2017, 2019, 2021, 2023] # Odd-Year Climate
        else:
            relevant_years = [2014, 2018, 2022] # Midterm Climate

        # Calculate average turnout % based on past similar climates
        # (Assuming CSV has a 'turnout_pct' or we calculate from 'totalvotes')
        subset = history[history['year'].isin(relevant_years)]
        avg_turnout_pct = subset['turnout_pct'].mean() if not subset.empty else 0.50

        # 4. FINAL MATH
        projected_turnout = total_vap * avg_turnout_pct
        win_number = int(projected_turnout * 0.52) # 52% safety margin

        return {
            "win_number": win_number,
            "projected_turnout": int(projected_turnout),
            "voter_universe": total_vap,
            "historical_context": f"Averaged cycles: {relevant_years}"
        }