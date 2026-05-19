import unittest
from unittest.mock import patch, MagicMock
from src.servers.app_server.logic import WeatherLogic

class TestWeatherLogic(unittest.TestCase):

    @patch('src.servers.app_server.logic.requests.get')
    def test_download_weather_csv_report_success(self, mock_get):
        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"time,temperature_2m\n2026-03-04T12:00,20.5"
        mock_get.return_value = mock_response

        logic = WeatherLogic()
        result = logic.download_weather_csv_report("TestCity", 32.0, 34.0)

        self.assertEqual(result, b"time,temperature_2m\n2026-03-04T12:00,20.5")
        mock_get.assert_called_once()

    @patch('src.servers.app_server.logic.requests.get')
    def test_download_weather_csv_report_fail(self, mock_get):
        # Mock 404 HTTP error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        logic = WeatherLogic()
        result = logic.download_weather_csv_report("TestCity", 32.0, 34.0)

        # Logic should handle the 404 gracefully and return None
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()