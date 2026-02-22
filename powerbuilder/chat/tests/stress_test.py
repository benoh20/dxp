# tests/stress_test.py
from chat.utils.data_fetcher import DataFetcher
from chat.utils.election_ingestor import ElectionDataUtility
from chat.agents.win_number import WinNumberAgent

def run_stress_test():
    print("🧪 Starting Component Stress Test...")

    # 1. Test Ingestor
    print("- Testing Election Ingestor (VA)...")
    success = ElectionDataUtility.sync_historical_data("51")
    assert success, "❌ Ingestor failed to sync VA data."

    # 2. Test Win Number Logic
    print("- Testing Win Number Math...")
    results = WinNumberAgent.calculate_win_math("51", "congressional", "District 07")
    assert "win_number" in results, "❌ Win Number calculation failed."
    print(f"   [Success] Projected Win Number: {results['win_number']}")

    # 3. Test Census Fetcher
    print("- Testing Dynamic Census Fetch (Black Women VAP)...")
    census_test = DataFetcher.get_custom_crosstab("51", race="black", gender="female", age_min=18, age_max=45)
    assert len(census_test) > 0, "❌ Census Fetcher returned no data."
    
    print("✅ All components passed stress test!")

if __name__ == "__main__":
    run_stress_test()