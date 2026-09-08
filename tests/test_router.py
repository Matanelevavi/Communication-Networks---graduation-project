import unittest
from unittest.mock import MagicMock

from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.router import RequestRouter
from src.servers.app_server.weather_api import Forecast, Place

PLACE = Place("Ariel", 32.1, 35.1)
FORECAST = Forecast(PLACE, min_temp=18, max_temp=30,
                    current_temp=25, rain_summary="No rain expected")


class RouterTestCase(unittest.TestCase):
    def setUp(self):
        self.weather = MagicMock()
        self.advisor = MagicMock()
        self.agent = MagicMock()
        self.router = RequestRouter(self.weather, self.advisor, self.agent)


class TestRouting(RouterTestCase):

    def test_an_archive_listing(self):
        self.agent.archive_listing.return_value = "LISTING"

        self.assertEqual(self.router.handle({"action": "FTP_LIST"}), "LISTING")

    def test_an_archived_file(self):
        self.agent.archived_file.return_value = "BODY"

        self.assertEqual(self.router.handle({"action": "FTP_GET", "filename": "a.txt"}), "BODY")
        self.agent.archived_file.assert_called_once_with("a.txt")

    def test_an_unknown_action_touches_nothing(self):
        answer = self.router.handle({"action": "HACK_SERVER"})

        self.assertEqual(answer, "Error: Unknown action requested.")
        self.weather.fetch.assert_not_called()
        self.agent.archive_listing.assert_not_called()

    def test_a_download_without_a_filename(self):
        answer = self.router.handle({"action": "FTP_GET"})

        self.assertTrue(answer.startswith("Error:"))
        self.agent.archived_file.assert_not_called()

    def test_forecast_is_the_default_action(self):
        self.agent.cached_forecast.return_value = "cached"

        self.assertEqual(self.router.handle({"city": "Ariel"}), "cached")


class TestForecast(RouterTestCase):

    def test_a_cache_hit_never_reaches_the_external_services(self):
        self.agent.cached_forecast.return_value = "Cached advice"

        answer = self.router.handle({"action": "FORECAST", "city": "Ariel"})

        self.assertEqual(answer, "Cached advice")
        self.weather.fetch.assert_not_called()
        self.advisor.recommend.assert_not_called()

    def test_a_fresh_forecast_is_stored_with_its_report(self):
        self.agent.cached_forecast.return_value = None
        self.weather.fetch.return_value = FORECAST
        self.advisor.recommend.return_value = "Wear a hat"
        self.weather.download_csv_report.return_value = b"csv"

        answer = self.router.handle({"action": "FORECAST", "city": "Ariel", "profiles": []})

        self.assertEqual(answer, "Wear a hat")
        self.agent.store_forecast.assert_called_once_with("Ariel", "Wear a hat")
        self.agent.store_report.assert_called_once_with("Ariel", b"csv")

    def test_a_missing_city_is_reported(self):
        """This used to raise AttributeError inside the worker thread."""
        answer = self.router.handle({"action": "FORECAST"})

        self.assertTrue(answer.startswith("Error:"))
        self.weather.fetch.assert_not_called()

    def test_a_city_name_with_spaces_is_normalised(self):
        self.agent.cached_forecast.return_value = "cached"

        self.router.handle({"action": "FORECAST", "city": "  Tel Aviv  "})

        self.agent.cached_forecast.assert_called_once_with("Tel_Aviv")


class TestFailuresAreNeverCached(RouterTestCase):

    def setUp(self):
        super().setUp()
        self.agent.cached_forecast.return_value = None

    def test_an_ai_failure_is_shown_but_not_stored(self):
        """
        Storing it would serve that error for the rest of the day, because the
        cache is keyed by city and file date.
        """
        self.weather.fetch.return_value = FORECAST
        self.advisor.recommend.side_effect = ServiceError("AI Error: quota exceeded")

        answer = self.router.handle({"action": "FORECAST", "city": "Ariel"})

        self.assertEqual(answer, "AI Error: quota exceeded")
        self.agent.store_forecast.assert_not_called()
        self.agent.store_report.assert_not_called()

    def test_a_weather_failure_stops_before_the_ai_call(self):
        self.weather.fetch.side_effect = ServiceError("City Error: not found")

        answer = self.router.handle({"action": "FORECAST", "city": "Nowhere"})

        self.assertEqual(answer, "City Error: not found")
        self.advisor.recommend.assert_not_called()
        self.agent.store_forecast.assert_not_called()

    def test_a_missing_report_still_stores_the_advice(self):
        self.weather.fetch.return_value = FORECAST
        self.advisor.recommend.return_value = "Wear a hat"
        self.weather.download_csv_report.return_value = None

        self.router.handle({"action": "FORECAST", "city": "Ariel"})

        self.agent.store_forecast.assert_called_once()
        self.agent.store_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
