"""
The fallback provider, and the failover from Open-Meteo to it.

The reading is tested against a trimmed copy of a real MET Norway response, so
what is checked is what the service actually sends, not what was assumed it did.
"""
import copy
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from src.servers.app_server.external_service import (ProviderUnavailable, RateLimited,
                                                     ServiceError)
from src.servers.app_server.met_norway import (MetNorway, uv_under_cloud, weather_code)
from src.servers.app_server.weather_api import FORECAST_DAYS, Forecast, Place
from src.servers.app_server.weather_failover import FailoverWeather

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "met_locationforecast.json")
with open(FIXTURE, encoding="utf-8") as f:
    REAL = json.load(f)

ARIEL = Place("Ariel", 32.11, 35.18, "Asia/Jerusalem")


def payload():
    return copy.deepcopy(REAL)


def reply(status=200, body=None):
    mock = MagicMock(status_code=status, ok=status < 400)
    mock.json.return_value = body if body is not None else payload()
    return mock


class TestReadingARealResponse(unittest.TestCase):

    def setUp(self):
        self.forecast = MetNorway().parse(payload(), ARIEL)

    def test_it_is_a_forecast_and_says_whose(self):
        self.assertIsInstance(self.forecast, Forecast)
        self.assertEqual(self.forecast.provider, "MET Norway")

    def test_the_hours_are_the_places_own_not_utc(self):
        """The first entry is 08:00Z, which in Jerusalem in November is 10:00."""
        self.assertEqual(REAL["properties"]["timeseries"][0]["time"], "2026-11-17T08:00:00Z")
        self.assertEqual(self.forecast.hourly[0]["t"], "2026-11-17T10:00")

    def test_a_different_zone_gives_different_hours(self):
        tokyo = MetNorway().parse(payload(), Place("Tokyo", 35.7, 139.7, "Asia/Tokyo"))

        self.assertEqual(tokyo.hourly[0]["t"], "2026-11-17T17:00")

    def test_no_zone_falls_back_to_longitude_and_not_to_utc(self):
        """Showing UTC as though it were local time would be wrong by hours."""
        guess = MetNorway().parse(payload(), Place("Ariel", 32.11, 35.18))     # 35 degrees: +2 h

        self.assertEqual(guess.hourly[0]["t"], "2026-11-17T10:00")

    def test_an_unknown_zone_is_survived(self):
        odd = MetNorway().parse(payload(), Place("Ariel", 32.11, 35.18, "Mars/Olympus"))

        self.assertEqual(odd.hourly[0]["t"], "2026-11-17T10:00")

    def test_twenty_four_hours_and_a_week(self):
        self.assertEqual(len(self.forecast.hourly), 24)
        self.assertEqual(len(self.forecast.daily), FORECAST_DAYS)
        self.assertEqual([d["date"] for d in self.forecast.daily][:2], ["2026-11-17", "2026-11-18"])

    def test_the_numbers_are_in_the_pages_units(self):
        first = REAL["properties"]["timeseries"][0]["data"]["instant"]["details"]

        self.assertEqual(self.forecast.current_temp, first["air_temperature"])
        self.assertEqual(self.forecast.wind_kmh, round(first["wind_speed"] * 3.6, 1))     # m/s to km/h
        self.assertEqual(self.forecast.humidity, round(first["relative_humidity"]))
        self.assertEqual(self.forecast.min_temp, min(h["temp"] for h in self.forecast.hourly))

    def test_there_is_no_chance_of_rain_and_none_is_invented(self):
        """MET gives an amount. Reporting it as a percentage would be a lie."""
        self.assertTrue(all(h["rain"] is None for h in self.forecast.hourly))
        self.assertTrue(all(d["rain"] is None for d in self.forecast.daily))
        self.assertTrue(all("mm" in h for h in self.forecast.hourly))

    def test_a_wet_hour_is_listed_with_its_amount(self):
        data = payload()
        data["properties"]["timeseries"][3]["data"]["next_1_hours"]["details"]["precipitation_amount"] = 1.4

        wet = MetNorway().parse(data, ARIEL)

        self.assertIn("(1.4 mm)", wet.rain_summary)
        self.assertEqual(wet.rain_summary.split(" ")[0], wet.hourly[3]["t"][11:16])
        self.assertEqual(self.forecast.rain_summary, "No rain expected")

    def test_a_drizzle_below_the_threshold_is_not_rain(self):
        data = payload()
        data["properties"]["timeseries"][3]["data"]["next_1_hours"]["details"]["precipitation_amount"] = 0.1

        self.assertEqual(MetNorway().parse(data, ARIEL).rain_summary, "No rain expected")

    def test_sunrise_and_sunset_are_absent_not_made_up(self):
        self.assertIsNone(self.forecast.sunrise)
        self.assertIsNone(self.forecast.sunset)

    def test_a_days_uv_comes_from_daylight_not_from_a_night_reading(self):
        for day in self.forecast.daily:
            self.assertTrue(day["uv"] is None or day["uv"] > 0, day)

    def test_the_sky_is_a_code_the_page_can_draw(self):
        self.assertEqual(self.forecast.weather_code, 2)             # partlycloudy_day
        self.assertIs(self.forecast.is_day, True)
        self.assertTrue(all(d["code"] is None or isinstance(d["code"], int) for d in self.forecast.daily))

    def test_it_survives_the_cache_and_keeps_its_credit(self):
        again = Forecast.from_dict(self.forecast.to_dict())

        self.assertEqual(again.provider, "MET Norway")
        self.assertEqual(again.hourly, self.forecast.hourly)

    def test_the_archive_report_can_be_written_from_it(self):
        csv = self.forecast.to_csv().decode().splitlines()

        self.assertEqual(csv[0], "time,temperature_2m,precipitation_probability")
        self.assertEqual(len(csv), 25)


class TestTheMappings(unittest.TestCase):

    def test_symbols_become_codes(self):
        for symbol, code in (("clearsky_day", 0), ("clearsky_night", 0), ("fair_day", 1),
                             ("partlycloudy_night", 2), ("cloudy", 3), ("fog", 45),
                             ("lightrain", 61), ("heavyrain", 65), ("rainshowers_day", 81),
                             ("sleet", 67), ("snow", 73), ("heavysnowshowers_night", 86)):
            self.assertEqual(weather_code(symbol), code, symbol)

    def test_every_kind_of_thunder_is_a_thunderstorm(self):
        for symbol in ("thunderstorm", "lightrainandthunder_day", "heavysnowandthunder_night",
                       "rainshowersandthunder_polartwilight"):
            self.assertEqual(weather_code(symbol), 95, symbol)

    def test_an_unknown_symbol_is_unknown_not_an_error(self):
        self.assertIsNone(weather_code("brandnewweather_day"))
        self.assertIsNone(weather_code(None))
        self.assertIsNone(weather_code(""))

    def test_cloud_takes_the_sun_out_of_the_uv_index(self):
        """A clear sky value on an overcast day would tell people to wear sunscreen for nothing."""
        self.assertEqual(uv_under_cloud(8.0, 0), 8.0)
        self.assertAlmostEqual(uv_under_cloud(8.0, 100), 2.0, places=5)
        self.assertLess(uv_under_cloud(8.0, 80), uv_under_cloud(8.0, 40))
        self.assertEqual(uv_under_cloud(8.0, None), 8.0)
        self.assertIsNone(uv_under_cloud(None, 50))
        self.assertEqual(uv_under_cloud(8.0, 250), uv_under_cloud(8.0, 100))     # clamped


@patch("src.servers.app_server.met_norway.requests.get")
class TestTheRequest(unittest.TestCase):

    def test_it_identifies_itself_and_keeps_to_four_decimals(self, get):
        """Both are conditions of using the service."""
        get.return_value = reply()

        MetNorway().forecast_for(Place("Ariel", 32.123456789, 35.987654321, "Asia/Jerusalem"))

        headers, params = get.call_args[1]["headers"], get.call_args[1]["params"]
        self.assertIn("WeatherWear", headers["User-Agent"])
        self.assertIn("github.com", headers["User-Agent"])
        self.assertEqual((params["lat"], params["lon"]), ("32.1235", "35.9877"))

    def test_throttling_is_a_rate_limit_and_starts_a_wait(self, get):
        clock = [100.0]
        service = MetNorway(clock=lambda: clock[0])
        get.return_value = reply(429)

        with self.assertRaises(RateLimited):
            service.forecast_for(ARIEL)
        with self.assertRaises(RateLimited):
            service.forecast_for(ARIEL)

        self.assertEqual(get.call_count, 1)                 # the second never left the machine

    def test_a_403_is_treated_as_a_telling_off(self, get):
        get.return_value = reply(403)

        with self.assertRaises(RateLimited):
            MetNorway().forecast_for(ARIEL)

    def test_a_server_error_and_a_dead_network_are_unavailable(self, get):
        get.return_value = reply(503)
        with self.assertRaises(ProviderUnavailable):
            MetNorway().forecast_for(ARIEL)

        get.side_effect = requests.ConnectionError("no route")
        with self.assertRaises(ProviderUnavailable):
            MetNorway().forecast_for(ARIEL)

    def test_an_answer_that_is_not_what_it_should_be_is_unavailable_not_a_crash(self, get):
        for body in ({}, {"properties": {}}, {"properties": {"timeseries": []}},
                     {"properties": {"timeseries": [{"time": "x"}]}}, {"properties": {"timeseries": "no"}}):
            get.return_value = reply(200, body)
            with self.assertRaises(ProviderUnavailable):
                MetNorway().forecast_for(ARIEL)


class TestFailover(unittest.TestCase):

    def setUp(self):
        self.primary, self.fallback = MagicMock(), MagicMock()
        self.good = Forecast(ARIEL, 10, 20, 15, "No rain expected")
        self.other = Forecast(ARIEL, 11, 21, 16, "No rain expected", provider="MET Norway")
        self.weather = FailoverWeather(self.primary, self.fallback)

    def test_the_first_provider_is_used_when_it_answers(self):
        self.primary.forecast_for.return_value = self.good

        self.assertIs(self.weather.fetch_at("Ariel", 32.1, 35.2, "Asia/Jerusalem"), self.good)
        self.fallback.forecast_for.assert_not_called()

    def test_a_throttled_first_provider_hands_over_to_the_second(self):
        self.primary.forecast_for.side_effect = RateLimited("Daily API request limit exceeded")
        self.fallback.forecast_for.return_value = self.other

        result = self.weather.fetch_at("Ariel", 32.1, 35.2, "Asia/Jerusalem")

        self.assertIs(result, self.other)
        self.assertEqual(result.provider, "MET Norway")

    def test_the_same_place_is_asked_of_both_including_its_zone(self):
        self.primary.forecast_for.side_effect = ProviderUnavailable("down")
        self.fallback.forecast_for.return_value = self.other

        self.weather.fetch_at("Ariel", 32.1, 35.2, "Asia/Jerusalem")

        self.assertEqual(self.fallback.forecast_for.call_args[0][0],
                         Place("Ariel", 32.1, 35.2, "Asia/Jerusalem"))

    def test_when_both_fail_the_first_ones_explanation_is_what_is_shown(self):
        self.primary.forecast_for.side_effect = RateLimited("The provider is receiving too many requests.")
        self.fallback.forecast_for.side_effect = ProviderUnavailable("the second is down too")

        with self.assertRaises(RateLimited) as caught:
            self.weather.fetch_at("Ariel", 32.1, 35.2)

        self.assertIn("too many requests", str(caught.exception))

    def test_an_unreadable_second_answer_is_not_a_crash_either(self):
        self.primary.forecast_for.side_effect = ProviderUnavailable("down")
        self.fallback.forecast_for.side_effect = ServiceError("odd")

        with self.assertRaises(ProviderUnavailable):
            self.weather.fetch_at("Ariel", 32.1, 35.2)

    def test_an_unknown_city_is_not_an_outage_and_asks_nobody_else(self):
        self.primary.locate.side_effect = ServiceError("'Atlantis' was not found.")

        with self.assertRaises(ServiceError) as caught:
            self.weather.fetch("Atlantis")

        self.assertNotIsInstance(caught.exception, ProviderUnavailable)
        self.fallback.forecast_for.assert_not_called()

    def test_a_typed_name_is_found_once_and_the_place_is_reused(self):
        self.primary.locate.return_value = ARIEL
        self.primary.forecast_for.side_effect = RateLimited("busy")
        self.fallback.forecast_for.return_value = self.other

        self.weather.fetch("Ariel")

        self.primary.locate.assert_called_once_with("Ariel")
        self.assertEqual(self.fallback.forecast_for.call_args[0][0], ARIEL)

    def test_searching_stays_with_the_first_providers_geocoder(self):
        self.primary.search.return_value = [{"name": "Ariel"}]

        self.assertEqual(self.weather.search("Ariel"), [{"name": "Ariel"}])
        self.fallback.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
