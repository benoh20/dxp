# tests/test_edge_cases.py
import unittest
from unittest.mock import patch, Mock
from chat.utils.data_fetcher import DataFetcher

class TestEdgeCases(unittest.TestCase):
    @patch('requests.get')
    def test_empty_census_response(self, mock_get):
        """Stress test: What if the Census returns no data for a district?"""
        mock_response = Mock()
        # Simulating the Census 'No Data' response: just the header, no rows
        mock_response.json.return_value = [["NAME", "B01003_001E"]] 
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = DataFetcher.get_census_data("51", variables=["total_pop"], geo_level="congressional")
        
        # We expect an empty list, not a crash
        self.assertEqual(result, [])
        print("✅ Empty API Response Handling: PASSED")