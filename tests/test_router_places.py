"""
Forecasts for a chosen or shared place, the suggestion list, and the rule that a
position somebody shared never reaches the public archive.
"""
import json
import os
import shutil
import unittest
from unittest.mock import MagicMock

from src.servers.app_server.advisor import LOCAL, Advice
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.forecast_cache import PRIVATE_PREFIX
from src.servers.app_server.router import SEARCH_CACHE_SIZE, RequestRouter
from src.servers.app_server.weather_api import Forecast, Place

FORECAST = Forecast(Place("Ariel", 32.11, 35.18), 18, 30, 25, "No rain expected",
                    feels_like=24, wind_kmh=12, weather_code=1, uv_max=7,
                    hourly=[{"t": "2026-10-29T00:00", "temp": 20, "rain": 0, "code": 1}],
                    daily=[{"date": "2026-10-29", "code": 1, "max": 30, "min": 18, "rain": 0,
                            "uv": 7, "wind": 20, "sunrise": "05:53", "sunset": "16:52"}])


class PlacesTestCase(unittest.TestCase):
    def setUp(self):
        self.weather = MagicMock()
        self.weather.fetch.return_value = FORECAST
        self.weather.fetch_at.return_value = FORECAST
        self.weather.download_csv_report.return_value = b"csv"
        self.advisor = MagicMock()
        self.advisor.recommend.return_value = Advice("Wear a hat", LOCAL)
        self.agent = MagicMock()
        self.agent.cached_forecast.return_value = None
        self.router = RequestRouter(self.weather, self.advisor, self.agent)

    def ask(self, **request):
        return self.router.handle({"action": "FORECAST", **request})

    def card(self, **request):
        return json.loads(self.ask(**request))


class TestChosenPlaces(PlacesTestCase):

    def test_a_chosen_place_is_fetched_by_its_coordinates_not_looked_up_by_name(self):
        """'Ariel' is five towns: the name alone cannot say which one was meant."""
        self.card(city="Ariel", lat=32.1065, lon=35.18449)

        self.weather.fetch_at.assert_called_once_with("Ariel", 32.11, 35.18)
        self.weather.fetch.assert_not_called()

    def test_coordinates_are_rounded_to_about_a_kilometre(self):
        self.card(city="X", lat=32.123456, lon=35.987654)

        self.assertEqual(self.weather.fetch_at.call_args[0][1:], (32.12, 35.99))

    def test_a_chosen_place_is_cached_under_its_name_and_its_coordinates(self):
        self.card(city="Ariel", lat=32.1065, lon=35.18449)

        key = self.agent.store_forecast.call_args[0][0]
        self.assertEqual(key, "Ariel 32.11 35.18")
        self.agent.store_report.assert_called_once()

    def test_two_towns_with_one_name_do_not_share_a_cache_entry(self):
        self.card(city="Ariel", lat=32.1065, lon=35.18449)
        self.card(city="Ariel", lat=45.95678, lon=-122.57093)

        keys = [c[0][0] for c in self.agent.store_forecast.call_args_list]
        self.assertEqual(len(set(keys)), 2)

    def test_a_cache_hit_is_shown_under_this_visitors_own_label(self):
        self.agent.cached_forecast.return_value = FORECAST.to_dict()

        card = self.card(city="אריאל", lat=32.11, lon=35.18)

        self.assertEqual(card["city"], "אריאל")
        self.assertTrue(card["cached"])
        self.weather.fetch_at.assert_not_called()

    def test_an_entry_written_before_the_schema_changed_is_refetched(self):
        self.agent.cached_forecast.return_value = {"city": "Ariel", "latitude": 1, "longitude": 2,
                                                   "min_temp": 1, "max_temp": 2, "rain": "x"}

        self.assertFalse(self.card(city="Ariel")["cached"])
        self.weather.fetch.assert_called_once()


class TestSharedPositions(PlacesTestCase):
    """A position the browser shared is somebody's location: not archive content."""

    def test_it_is_stored_under_a_private_hashed_name(self):
        self.card(lat=32.123, lon=35.456)

        key = self.agent.store_forecast.call_args[0][0]
        self.assertTrue(key.startswith(PRIVATE_PREFIX))
        self.assertNotIn("32", key)
        self.assertNotIn("35", key)

    def test_the_same_position_finds_its_own_entry_again(self):
        self.card(lat=32.123, lon=35.456)
        self.card(lat=32.121, lon=35.458)               # rounds to the same kilometre

        keys = [c[0][0] for c in self.agent.store_forecast.call_args_list]
        self.assertEqual(keys[0], keys[1])

    def test_no_report_is_archived_for_it(self):
        self.card(lat=32.123, lon=35.456)

        self.agent.store_report.assert_not_called()
        self.weather.download_csv_report.assert_not_called()

    def test_the_card_has_no_name_for_the_page_to_fill_in(self):
        self.weather.fetch_at.return_value = Forecast(Place("", 32.12, 35.46), 18, 30, 25,
                                                      "No rain expected")

        self.assertEqual(self.card(lat=32.123, lon=35.456)["city"], "")

    def test_a_request_with_neither_a_name_nor_a_position_is_refused(self):
        self.assertTrue(self.ask().startswith("Error:"))


class TestBadCoordinates(PlacesTestCase):

    def test_nothing_reaches_the_weather_service_when_the_position_is_wrong(self):
        for bad in ({"lat": "north", "lon": 1}, {"lat": 91, "lon": 0}, {"lat": 0, "lon": 181},
                    {"lat": float("nan"), "lon": 0}, {"lat": float("inf"), "lon": 0},
                    {"lat": 5}, {"lon": 5}, {"lat": None, "lon": None}, {"lat": [], "lon": {}}):
            answer = self.ask(city="Ariel", **bad)

            self.assertTrue(answer.startswith("Error:"), bad)
            self.assertIn("coordinates", answer, bad)
        self.weather.fetch_at.assert_not_called()
        self.weather.fetch.assert_not_called()


class TestTheCard(PlacesTestCase):

    def test_it_carries_everything_the_page_draws(self):
        card = self.card(city="Ariel", profiles=[{"name": "Noam", "age_category": "baby"}])

        for key in ("feels_like", "humidity", "wind_kmh", "weather_code", "is_day", "uv_max",
                    "sunrise", "sunset", "hourly", "daily", "gear"):
            self.assertIn(key, card)
        self.assertEqual(card["hourly"][0]["temp"], 20)
        self.assertEqual(card["daily"][0]["uv"], 7)
        self.assertIn("spare_clothes", card["gear"])
        self.assertIn("sunscreen", card["gear"])

    def test_the_language_hint_is_passed_on_and_a_bad_one_is_dropped(self):
        self.card(city="Ariel", lang="he")
        self.assertEqual(self.advisor.recommend.call_args[1], {"language": "he"})

        self.card(city="Ariel", lang="klingon")
        self.assertEqual(self.advisor.recommend.call_args[1], {})

        self.card(city="Ariel")
        self.assertEqual(self.advisor.recommend.call_args[1], {})


class TestSearch(PlacesTestCase):

    PLACES = [{"name": "Ariel", "admin1": "Judea", "country": "Israel",
               "latitude": 32.1, "longitude": 35.2}]

    def search(self, query):
        return json.loads(self.router.handle({"action": "SEARCH", "query": query}))

    def test_matches_come_back_as_places(self):
        self.weather.search.return_value = self.PLACES

        answer = self.search("Ariel")

        self.assertEqual(answer, {"kind": "places", "places": self.PLACES})

    def test_a_query_too_short_to_mean_anything_is_not_sent_upstream(self):
        for query in ("", "a", " a ", None):
            self.assertEqual(self.search(query)["places"], [])
        self.weather.search.assert_not_called()

    def test_the_same_query_is_answered_from_memory(self):
        self.weather.search.return_value = self.PLACES

        self.search("Ariel")
        self.search("  ariel ")

        self.weather.search.assert_called_once()

    def test_the_query_is_bounded(self):
        self.weather.search.return_value = []

        self.search("x" * 500)

        self.assertEqual(len(self.weather.search.call_args[0][0]), 60)

    def test_the_memory_has_a_ceiling(self):
        self.weather.search.return_value = []

        for i in range(SEARCH_CACHE_SIZE + 50):
            self.search(f"city number {i}")

        self.assertLessEqual(len(self.router._searches), SEARCH_CACHE_SIZE)

    def test_a_failure_is_an_error_and_is_not_remembered(self):
        self.weather.search.side_effect = ServiceError("Could not reach the weather service.")

        first = self.router.handle({"action": "SEARCH", "query": "Ariel"})
        self.weather.search.side_effect = None
        self.weather.search.return_value = self.PLACES

        self.assertTrue(first.startswith("Error:"))
        self.assertEqual(self.search("Ariel")["places"], self.PLACES)


class TestArchivePrivacy(unittest.TestCase):

    def setUp(self):
        self.folder = os.path.abspath("test_dummy_private")
        shutil.rmtree(self.folder, ignore_errors=True)
        self.agent = FileAgent(data_folder=self.folder)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_shared_position_is_cached_but_neither_listed_nor_served(self):
        self.agent.store_forecast(f"{PRIVATE_PREFIX}abc123", FORECAST.to_dict())
        self.agent.store_forecast("Ariel 32.11 35.18", FORECAST.to_dict())

        listing = self.agent.archive_listing()

        self.assertNotIn("private", listing)
        self.assertIn("ariel_32_11_35_18_forecast.json", listing)
        self.assertEqual(self.agent.cached_forecast(f"{PRIVATE_PREFIX}abc123")["city"], "Ariel")
        self.assertTrue(self.agent.archived_file(
            f"{PRIVATE_PREFIX}abc123_forecast.json").startswith("Error:"))

    def test_an_archive_holding_only_private_files_looks_empty(self):
        self.agent.store_forecast(f"{PRIVATE_PREFIX}abc123", FORECAST.to_dict())

        self.assertIn("empty", self.agent.archive_listing())


if __name__ == "__main__":
    unittest.main()
