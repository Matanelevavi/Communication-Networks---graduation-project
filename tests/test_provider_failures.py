"""
When the weather provider cannot answer.

This is not hypothetical: on a shared host the provider's free tier limits
requests per address, and the deployed site was answered with HTTP 429 until
the code learned to cope. What is pinned here is how it copes: a specific
message, no hammering, and the last good forecast instead of an error.
"""
import json
import os
import shutil
import time
import unittest
from unittest.mock import MagicMock, patch

import requests

from src.config import STALE_FORECAST_MAX_AGE
from src.servers.app_server.advisor import LOCAL, Advice
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.external_service import (ProviderUnavailable, RateLimited,
                                                     ServiceError)
from src.servers.app_server.router import RequestRouter
from src.servers.app_server.weather_api import (BACKOFF_SECONDS, MAX_BACKOFF_SECONDS,
                                                Forecast, Place, WeatherService)

HOURS = [{"t": "2026-10-29T12:00", "temp": 25.0, "rain": 0, "code": 1}]
FORECAST = Forecast(Place("Ariel", 32.1, 35.1), 18, 30, 25, "No rain expected", hourly=HOURS)
OK_BODY = {"hourly": {"time": ["2026-10-29T12:00"], "temperature_2m": [20.0]}}


def reply(status=200, body=None, headers=None):
    mock = MagicMock(status_code=status, ok=status < 400, headers=headers or {})
    mock.json.return_value = body if body is not None else {}
    return mock


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@patch("src.servers.app_server.weather_api.requests.get")
class TestHowTheClientFails(unittest.TestCase):

    def setUp(self):
        self.clock = Clock()
        self.service = WeatherService(clock=self.clock)

    def test_a_429_is_a_rate_limit_with_its_own_message(self, get):
        get.return_value = reply(429, {"error": True, "reason": "Minutely API request limit exceeded"})

        with self.assertRaises(RateLimited) as caught:
            self.service.fetch_at("Ariel", 1, 2)

        self.assertIn("too many requests", str(caught.exception))
        self.assertIsInstance(caught.exception, ProviderUnavailable)

    def test_the_reason_the_provider_gives_reaches_the_log(self, get):
        """It says which limit was hit, which decides what to do about it."""
        get.return_value = reply(429, {"reason": "Daily API request limit exceeded"})

        with self.assertLogs("src.servers.app_server.weather_api", level="ERROR") as logs:
            with self.assertRaises(RateLimited):
                self.service.fetch_at("Ariel", 1, 2)

        self.assertIn("Daily API request limit exceeded", "\n".join(logs.output))

    def test_after_a_429_the_provider_is_left_alone(self, get):
        """Every request during a limit only extends it, and the address is shared."""
        get.return_value = reply(429)

        for _ in range(5):
            with self.assertRaises(RateLimited):
                self.service.fetch_at("Ariel", 1, 2)

        self.assertEqual(get.call_count, 1)

    def test_it_tries_again_once_the_wait_is_over(self, get):
        get.side_effect = [reply(429), reply(200, OK_BODY)]
        with self.assertRaises(RateLimited):
            self.service.fetch_at("Ariel", 1, 2)

        self.clock.now += BACKOFF_SECONDS + 1

        self.assertEqual(self.service.fetch_at("Ariel", 1, 2).min_temp, 20.0)
        self.assertEqual(get.call_count, 2)

    def test_it_waits_as_long_as_it_is_told_within_limits(self, get):
        for asked, expected in (("120", 120), ("1", 10), ("999999", MAX_BACKOFF_SECONDS), ("soon", BACKOFF_SECONDS)):
            service = WeatherService(clock=self.clock)
            get.reset_mock()
            get.return_value = reply(429, headers={"Retry-After": asked})
            with self.assertRaises(RateLimited):
                service.fetch_at("Ariel", 1, 2)

            self.clock.now += expected - 1
            with self.assertRaises(RateLimited):
                service.fetch_at("Ariel", 1, 2)
            self.assertEqual(get.call_count, 1, asked)          # still waiting
            self.clock.now += 2
            get.return_value = reply(200, OK_BODY)
            service.fetch_at("Ariel", 1, 2)
            self.assertEqual(get.call_count, 2, asked)          # and then it asks again

    def test_a_server_error_is_unavailable_but_not_a_rate_limit(self, get):
        get.return_value = reply(503)

        with self.assertRaises(ProviderUnavailable) as caught:
            self.service.fetch_at("Ariel", 1, 2)

        self.assertNotIsInstance(caught.exception, RateLimited)
        get.return_value = reply(200, OK_BODY)
        self.service.fetch_at("Ariel", 1, 2)            # a 503 does not start a wait

    def test_an_unreachable_provider_is_unavailable(self, get):
        get.side_effect = requests.ConnectionError("no route")

        with self.assertRaises(ProviderUnavailable):
            self.service.fetch_at("Ariel", 1, 2)

    def test_garbage_from_the_provider_is_unavailable(self, get):
        bad = reply(200)
        bad.json.side_effect = ValueError("not json")
        get.return_value = bad

        with self.assertRaises(ProviderUnavailable):
            self.service.fetch_at("Ariel", 1, 2)

    def test_an_unknown_city_is_not_a_provider_problem(self, get):
        """No earlier forecast can stand in for a place that does not exist."""
        get.return_value = reply(200, {"results": []})

        with self.assertRaises(ServiceError) as caught:
            self.service.fetch("Atlantis")

        self.assertNotIsInstance(caught.exception, ProviderUnavailable)

    def test_without_a_key_the_public_api_is_used(self, get):
        get.return_value = reply(200, OK_BODY)

        self.service.fetch_at("Ariel", 1, 2)

        self.assertIn("//api.open-meteo.com", get.call_args[0][0])
        self.assertNotIn("apikey", get.call_args[1]["params"])

    def test_with_a_key_the_paid_api_is_used_and_the_key_is_not_in_the_url(self, get):
        get.return_value = reply(200, OK_BODY)

        WeatherService(api_key="secret", clock=self.clock).fetch_at("Ariel", 1, 2)

        self.assertIn("//customer-api.open-meteo.com", get.call_args[0][0])
        self.assertEqual(get.call_args[1]["params"]["apikey"], "secret")
        self.assertNotIn("secret", get.call_args[0][0])


class RouterCase(unittest.TestCase):
    def setUp(self):
        self.weather = MagicMock()
        self.advisor = MagicMock()
        self.advisor.recommend.return_value = Advice("Wear a hat", LOCAL)
        self.folder = os.path.abspath("test_dummy_stale")
        shutil.rmtree(self.folder, ignore_errors=True)
        self.agent = FileAgent(data_folder=self.folder)
        self.router = RequestRouter(self.weather, self.advisor, self.agent)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def age(self, name, seconds):
        path = os.path.join(self.folder, name)
        then = time.time() - seconds
        os.utime(path, (then, then))

    def ask(self, **request):
        return json.loads(self.router.handle({"action": "FORECAST", "city": "Ariel", **request}))


class TestStaleIfError(RouterCase):

    def store_old(self, seconds):
        self.agent.store_forecast("Ariel", FORECAST.to_dict())
        self.age("ariel_forecast.json", seconds)

    def test_a_busy_provider_costs_a_banner_not_the_answer(self):
        self.store_old(2 * 3600)
        self.weather.fetch.side_effect = RateLimited("busy")

        card = self.ask()

        self.assertEqual(card["city"], "Ariel")
        self.assertEqual(card["max_temp"], 30)
        self.assertTrue(card["cached"])
        self.assertEqual(card["stale_minutes"], 120)

    def test_the_advice_is_still_written_for_this_family(self):
        self.store_old(3600)
        self.weather.fetch.side_effect = ProviderUnavailable("down")

        self.ask(profiles=[{"name": "Noam", "age_category": "baby"}])

        self.assertEqual(self.advisor.recommend.call_args[0][1][0]["name"], "Noam")

    def test_a_fresh_entry_is_used_without_asking_the_provider(self):
        self.store_old(60)

        card = self.ask()

        self.assertNotIn("stale_minutes", card)
        self.weather.fetch.assert_not_called()

    def test_a_forecast_too_old_to_be_useful_is_an_error_again(self):
        self.store_old(STALE_FORECAST_MAX_AGE + 600)
        self.weather.fetch.side_effect = RateLimited("busy")

        answer = self.router.handle({"action": "FORECAST", "city": "Ariel"})

        self.assertTrue(answer.startswith("Error:"))
        self.assertIn("too many requests", answer.replace("busy", "too many requests"))

    def test_with_nothing_stored_the_error_is_what_the_visitor_sees(self):
        self.weather.fetch.side_effect = RateLimited("The weather provider is busy.")

        answer = self.router.handle({"action": "FORECAST", "city": "Ariel"})

        self.assertEqual(answer, "Error: The weather provider is busy.")

    def test_an_unknown_city_gets_no_stale_stand_in(self):
        self.store_old(3600)
        self.weather.fetch.side_effect = ServiceError("'Ariel' was not found.")

        answer = self.router.handle({"action": "FORECAST", "city": "Ariel"})

        self.assertEqual(answer, "Error: 'Ariel' was not found.")

    def test_a_chosen_place_falls_back_to_its_own_entry(self):
        """Keyed by name and coordinates, so another Ariel's forecast is never offered."""
        self.agent.store_forecast("Ariel 32.11 35.18", FORECAST.to_dict())
        self.age("ariel_32_11_35_18_forecast.json", 3600)
        self.weather.fetch_at.side_effect = RateLimited("busy")

        card = self.ask(city="Ariel", lat=32.1065, lon=35.18449)
        self.assertEqual(card["stale_minutes"], 60)

        other = self.router.handle({"action": "FORECAST", "city": "Ariel",
                                    "lat": 45.95678, "lon": -122.57093})      # Ariel, Washington
        self.assertTrue(other.startswith("Error:"))

    def test_a_shared_position_falls_back_too_and_stays_private(self):
        self.weather.fetch_at.return_value = Forecast(Place("", 32.12, 35.46), 18, 30, 25,
                                                      "No rain expected", hourly=HOURS)
        self.ask(city="", lat=32.123, lon=35.456)                    # stores it, privately
        (name,) = [f for f in os.listdir(self.folder) if f.startswith("private_")]
        self.age(name, 3 * 3600)
        self.weather.fetch_at.side_effect = RateLimited("busy")

        card = self.ask(city="", lat=32.123, lon=35.456)

        self.assertEqual(card["stale_minutes"], 180)
        self.assertNotIn("private", self.agent.archive_listing())

    def test_a_provider_that_works_again_replaces_the_stale_entry(self):
        self.store_old(5 * 3600)
        newer = Forecast(Place("Ariel", 32.1, 35.1), 10, 12, 11, "No rain expected", hourly=HOURS)
        self.weather.fetch.return_value = newer

        card = self.ask()

        self.assertEqual(card["max_temp"], 12)
        self.assertNotIn("stale_minutes", card)
        self.assertEqual(self.ask()["max_temp"], 12)                 # and it is what is cached now


class TestTheCacheAge(RouterCase):

    def test_age_and_the_wider_limit(self):
        self.agent.store_forecast("Ariel", FORECAST.to_dict())
        self.age("ariel_forecast.json", 2 * 3600)

        self.assertIsNone(self.agent.cached_forecast("Ariel"))                       # normally too old
        self.assertEqual(self.agent.cached_forecast("Ariel", max_age=6 * 3600)["city"], "Ariel")
        self.assertIsNone(self.agent.cached_forecast("Ariel", max_age=3600))
        self.assertAlmostEqual(self.agent.forecast_age("Ariel"), 2 * 3600, delta=5)

    def test_a_place_never_stored_has_no_age(self):
        self.assertIsNone(self.agent.forecast_age("Nowhere"))


if __name__ == "__main__":
    unittest.main()
