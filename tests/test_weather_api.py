import unittest
from unittest.mock import MagicMock, patch

import requests

from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.weather_api import Place, WeatherService

GEOCODED = {"results": [{"latitude": 32.0, "longitude": 34.7, "name": "Tel Aviv"}]}
HOURLY = {
    "hourly": {"temperature_2m": [20, 25], "precipitation_probability": [0, 40],
               "time": ["2026-09-01T00:00", "2026-09-01T01:00"]},
    "current_weather": {"temperature": 22},
}


def response(payload):
    mock = MagicMock()
    mock.json.return_value = payload
    return mock


class TestInputValidation(unittest.TestCase):

    def test_english_is_accepted(self):
        self.assertTrue(WeatherService.is_english_only("Tel Aviv"))
        self.assertTrue(WeatherService.is_english_only("Ariel 40"))

    @patch("src.servers.app_server.weather_api.requests.get")
    def test_hebrew_never_reaches_the_network(self, get):
        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("אריאל")

        self.assertIn("Input Error", str(caught.exception))
        get.assert_not_called()


@patch("src.servers.app_server.weather_api.requests.get")
class TestFetch(unittest.TestCase):

    def test_a_full_forecast(self, get):
        get.side_effect = [response(GEOCODED), response(HOURLY)]

        forecast = WeatherService().fetch("Tel Aviv")

        self.assertEqual(forecast.place.name, "Tel Aviv")
        self.assertEqual((forecast.min_temp, forecast.max_temp), (20, 25))
        self.assertEqual(forecast.current_temp, 22)

    def test_the_city_is_passed_as_a_parameter_not_glued_into_the_url(self, get):
        """A name with a space has to be encoded by the HTTP layer."""
        get.side_effect = [response(GEOCODED), response(HOURLY)]

        WeatherService().fetch("Tel Aviv")

        self.assertEqual(get.call_args_list[0][1]["params"]["name"], "Tel Aviv")

    def test_wet_hours_are_summarised(self, get):
        get.side_effect = [response(GEOCODED), response(HOURLY)]

        forecast = WeatherService().fetch("Tel Aviv")

        self.assertIn("01:00", forecast.rain_summary)
        self.assertIn("40%", forecast.rain_summary)

    def test_a_dry_day_says_so(self, get):
        dry = {**HOURLY, "hourly": {**HOURLY["hourly"], "precipitation_probability": [0, 0]}}
        get.side_effect = [response(GEOCODED), response(dry)]

        self.assertEqual(WeatherService().fetch("Tel Aviv").rain_summary,
                         "No rain expected")

    def test_an_unknown_city(self, get):
        get.return_value = response({"results": []})

        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("Atlantis")

        self.assertIn("was not found", str(caught.exception))

    def test_an_empty_forecast(self, get):
        get.side_effect = [response(GEOCODED), response({"hourly": {}})]

        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("Tel Aviv")

        self.assertIn("Data Error", str(caught.exception))

    def test_an_unreachable_service(self, get):
        get.side_effect = requests.RequestException("no route to host")

        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("Ariel")

        self.assertIn("Connection Error", str(caught.exception))


@patch("src.servers.app_server.weather_api.requests.get")
class TestCsvReport(unittest.TestCase):

    def test_a_successful_download(self, get):
        get.return_value.status_code = 200
        get.return_value.content = b"time,temperature_2m\n2026-03-04T12:00,20.5"

        report = WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0))

        self.assertEqual(report, b"time,temperature_2m\n2026-03-04T12:00,20.5")

    def test_a_rejected_download_returns_nothing(self, get):
        get.return_value.status_code = 404

        self.assertIsNone(WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0)))

    def test_a_network_error_returns_nothing(self, get):
        get.side_effect = requests.RequestException("boom")

        self.assertIsNone(WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0)))


if __name__ == "__main__":
    unittest.main()
