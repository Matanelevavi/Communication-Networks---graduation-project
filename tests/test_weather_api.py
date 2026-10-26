import unittest
from unittest.mock import MagicMock, patch

import requests

from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.weather_api import Forecast, Place, WeatherService

GEOCODED = {"results": [{"latitude": 32.0, "longitude": 34.7, "name": "Tel Aviv"}]}
HOURLY = {
    "hourly": {"temperature_2m": [20, 25], "precipitation_probability": [0, 40],
               "time": ["2026-09-01T00:00", "2026-09-01T01:00"]},
    "current_weather": {"temperature": 22},
}


def response(payload, status=200):
    mock = MagicMock()
    mock.json.return_value = payload
    mock.status_code = status
    mock.ok = status < 400
    return mock


@patch("src.servers.app_server.weather_api.requests.get")
class TestLanguage(unittest.TestCase):
    """The users are in Israel, and Hebrew used to be refused outright."""

    def test_a_hebrew_city_is_looked_up_in_hebrew(self, get):
        get.side_effect = [response({"results": [{"latitude": 32.1, "longitude": 35.1,
                                                  "name": "אריאל"}]}),
                           response(HOURLY)]

        forecast = WeatherService().fetch("אריאל")

        self.assertEqual(forecast.place.name, "אריאל")
        self.assertEqual(get.call_args_list[0][1]["params"]["language"], "he")

    def test_a_hebrew_town_open_meteo_does_not_know_falls_back_to_english(self, get):
        """'אריאל' finds nothing at Open-Meteo; 'Ariel' does."""
        get.side_effect = [response({}),
                           response({"results": [{"latitude": 32.1, "longitude": 35.2,
                                                  "name": "Ariel"}]}),
                           response(HOURLY)]

        forecast = WeatherService().fetch("אריאל")

        self.assertEqual(get.call_args_list[1][1]["params"]["name"], "Ariel")
        self.assertEqual(forecast.place.name, "אריאל")      # shown as typed
        self.assertEqual(forecast.place.latitude, 32.1)

    def test_an_unknown_hebrew_name_is_still_not_found(self, get):
        get.return_value = response({})

        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("עיר שלא קיימת")

        self.assertIn("not found", str(caught.exception))
        self.assertEqual(get.call_count, 1)             # nothing to fall back to

    def test_an_english_city_is_looked_up_in_english(self, get):
        get.side_effect = [response(GEOCODED), response(HOURLY)]

        WeatherService().fetch("Tel Aviv")

        self.assertEqual(get.call_args_list[0][1]["params"]["language"], "en")


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

        self.assertIn("No forecast is available", str(caught.exception))

    def test_an_unreachable_service(self, get):
        get.side_effect = requests.RequestException("no route to host")

        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("Ariel")

        self.assertIn("Could not reach", str(caught.exception))

    def test_an_http_error_is_not_mistaken_for_an_unknown_city(self, get):
        """Open-Meteo answers a bad request with JSON, so the status must be read."""
        get.return_value = response({"error": True, "reason": "bad"}, status=500)

        with self.assertRaises(ServiceError) as caught:
            WeatherService().fetch("Ariel")

        self.assertIn("unavailable", str(caught.exception))
        self.assertNotIn("not found", str(caught.exception))

    def test_the_hours_start_now_in_the_citys_time_zone(self, get):
        """A calendar day used to report rain that had already fallen."""
        get.side_effect = [response(GEOCODED), response(HOURLY)]

        WeatherService().fetch("Tel Aviv")

        params = get.call_args_list[1][1]["params"]
        self.assertEqual(params["forecast_hours"], 24)
        self.assertEqual(params["timezone"], "auto")


class TestForecastData(unittest.TestCase):

    def test_a_forecast_survives_a_round_trip_through_the_cache(self):
        forecast = Forecast(Place("Ariel", 32.1, 35.1), 18, 30, 25, "No rain expected")

        self.assertEqual(Forecast.from_dict(forecast.to_dict()), forecast)

    def test_an_incomplete_entry_raises(self):
        with self.assertRaises(KeyError):
            Forecast.from_dict({"city": "Ariel"})


@patch("src.servers.app_server.weather_api.requests.get")
class TestCsvReport(unittest.TestCase):

    def test_a_successful_download(self, get):
        get.return_value.status_code = 200
        get.return_value.content = b"time,temperature_2m\n2026-03-04T12:00,20.5"

        report = WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0))

        self.assertEqual(report, b"time,temperature_2m\n2026-03-04T12:00,20.5")

    def test_the_report_uses_the_same_hours_as_the_forecast(self, get):
        """It used to be in GMT while the summary on screen was in local time."""
        get.return_value.status_code = 200

        WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0))

        params = get.call_args[1]["params"]
        self.assertEqual(params["timezone"], "auto")
        self.assertEqual(params["forecast_hours"], 24)

    def test_a_rejected_download_returns_nothing(self, get):
        get.return_value.status_code = 404

        self.assertIsNone(WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0)))

    def test_a_network_error_returns_nothing(self, get):
        get.side_effect = requests.RequestException("boom")

        self.assertIsNone(WeatherService().download_csv_report(Place("Ariel", 32.0, 34.0)))


if __name__ == "__main__":
    unittest.main()
