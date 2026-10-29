"""
The richer forecast: how it is read from Open-Meteo, what to bring, and what the
advice says about wind, sun and how it feels.
"""
import unittest
from unittest.mock import MagicMock, patch

from src.servers.app_server.advisor import LOCAL, ClothingAdvisor
from src.servers.app_server.ai_advisor import AiAdvisor
from src.servers.app_server.gear import gear_for
from src.servers.app_server.local_advisor import LocalAdvisor
from src.servers.app_server.weather_api import (FORECAST_DAYS, Forecast, Place,
                                                WeatherService)

PLACE = Place("Ariel", 32.1, 35.2)


def payload(**overrides):
    """A response shaped like the real one, for 24 hours and 7 days."""
    hours = [f"2026-10-29T{h:02d}:00" for h in range(24)]
    days = [f"2026-10-{29 + d:02d}" for d in range(7)]
    body = {
        "timezone": "Asia/Jerusalem",
        "current": {"time": "2026-10-29T06:30", "temperature_2m": 17.6,
                    "apparent_temperature": 16.7, "relative_humidity_2m": 61,
                    "weather_code": 1, "wind_speed_10m": 6.4, "is_day": 1},
        "hourly": {"time": hours,
                   "temperature_2m": [15 + h / 3 for h in range(24)],
                   "precipitation_probability": [0] * 20 + [40, 50, 10, 0],
                   "weather_code": [1] * 24},
        "daily": {"time": days, "weather_code": [3] * 7,
                  "temperature_2m_max": [23.3 + d for d in range(7)],
                  "temperature_2m_min": [13.7] * 7,
                  "precipitation_probability_max": [0] * 7,
                  "uv_index_max": [5.05] * 7, "wind_speed_10m_max": [29.6] * 7,
                  "sunrise": [f"{d}T05:53" for d in days],
                  "sunset": [f"{d}T16:52" for d in days]},
    }
    body.update(overrides)
    return body


def response(body, status=200):
    mock = MagicMock(status_code=status, ok=status < 400)
    mock.json.return_value = body
    return mock


def forecast(**overrides):
    base = dict(place=PLACE, min_temp=18.0, max_temp=24.0, current_temp=21.0,
                rain_summary="No rain expected")
    base.update(overrides)
    return Forecast(**base)


@patch("src.servers.app_server.weather_api.requests.get")
class TestReadingTheResponse(unittest.TestCase):

    def fetch(self, get, body=None, **kw):
        get.return_value = response(body or payload())
        return WeatherService().fetch_at("Ariel", 32.1, 35.2, **kw)

    def test_how_it_feels_the_wind_and_the_sky_are_read(self, get):
        result = self.fetch(get)

        self.assertEqual(result.feels_like, 16.7)
        self.assertEqual(result.humidity, 61)
        self.assertEqual(result.wind_kmh, 6.4)
        self.assertEqual(result.weather_code, 1)
        self.assertIs(result.is_day, True)

    def test_night_is_not_day(self, get):
        body = payload()
        body["current"]["is_day"] = 0

        self.assertIs(self.fetch(get, body).is_day, False)

    def test_todays_sun_comes_from_the_first_day(self, get):
        result = self.fetch(get)

        self.assertEqual(result.uv_max, 5.05)
        self.assertEqual(result.sunrise, "2026-10-29T05:53")
        self.assertEqual(result.sunset, "2026-10-29T16:52")

    def test_there_is_an_hour_series_and_a_week(self, get):
        result = self.fetch(get)

        self.assertEqual(len(result.hourly), 24)
        self.assertEqual(result.hourly[0], {"t": "2026-10-29T00:00", "temp": 15.0, "rain": 0, "code": 1})
        self.assertEqual(len(result.daily), FORECAST_DAYS)
        self.assertEqual(result.daily[1]["max"], 24.3)
        self.assertEqual(set(result.daily[0]),
                         {"date", "code", "max", "min", "rain", "uv", "wind", "sunrise", "sunset"})

    def test_the_request_asks_for_everything_in_one_call_in_kmh(self, get):
        self.fetch(get)

        params = get.call_args[1]["params"]
        self.assertEqual(params["forecast_days"], FORECAST_DAYS)
        self.assertEqual(params["wind_speed_unit"], "kmh")
        self.assertIn("apparent_temperature", params["current"])
        self.assertIn("uv_index_max", params["daily"])
        self.assertIn("weather_code", params["hourly"])
        self.assertEqual(params["timezone"], "auto")

    def test_a_response_missing_the_extras_is_still_a_forecast(self, get):
        """Only the temperatures are essential; everything else is a bonus."""
        body = {"hourly": {"time": ["2026-10-29T00:00"], "temperature_2m": [20.0]}}

        result = self.fetch(get, body)

        self.assertEqual((result.min_temp, result.max_temp), (20.0, 20.0))
        self.assertIsNone(result.feels_like)
        self.assertIsNone(result.uv_max)
        self.assertEqual(result.daily, [])
        self.assertEqual(len(result.hourly), 1)

    def test_series_of_different_lengths_cannot_raise(self, get):
        body = payload()
        body["hourly"]["weather_code"] = [1, 2]
        body["daily"]["uv_index_max"] = []

        result = self.fetch(get, body)

        self.assertEqual([h["code"] for h in result.hourly[:3]], [1, 2, None])
        self.assertIsNone(result.daily[0]["uv"])

    def test_the_older_current_weather_block_still_works(self, get):
        body = payload()
        del body["current"]
        body["current_weather"] = {"temperature": 19.5}

        self.assertEqual(self.fetch(get, body).current_temp, 19.5)

    def test_it_survives_the_cache(self, get):
        result = self.fetch(get)

        self.assertEqual(Forecast.from_dict(result.to_dict()), result)

    def test_an_entry_from_before_the_schema_changed_is_refused(self, get):
        old = {"city": "Ariel", "latitude": 1, "longitude": 2, "min_temp": 1, "max_temp": 2,
               "current_temp": 1, "rain": "No rain expected"}

        with self.assertRaises(KeyError):
            Forecast.from_dict(old)

    def test_the_peak_wind_is_the_stronger_of_now_and_today(self, get):
        self.assertEqual(forecast(wind_kmh=10).peak_wind_kmh, 10)
        self.assertEqual(forecast(wind_kmh=10, daily=[{"wind": 35}]).peak_wind_kmh, 35)
        self.assertEqual(forecast().peak_wind_kmh, 0)


@patch("src.servers.app_server.weather_api.requests.get")
class TestPlaceSearch(unittest.TestCase):

    RESULTS = {"results": [
        {"name": "Ariel", "admin1": "Judea and Samaria Area", "country": "Israel",
         "latitude": 32.1065, "longitude": 35.18449, "population": 20540},
        {"name": "Lake Ariel", "admin1": "Pennsylvania", "country": "United States",
         "latitude": 41.45, "longitude": -75.38},
        {"name": "No Coordinates", "country": "Nowhere"},
    ]}

    def test_several_matches_come_back_as_choices(self, get):
        get.return_value = response(self.RESULTS)

        places = WeatherService().search("Ariel")

        self.assertEqual([p["name"] for p in places], ["Ariel", "Lake Ariel"])
        self.assertEqual(places[0], {"name": "Ariel", "admin1": "Judea and Samaria Area",
                                     "country": "Israel", "latitude": 32.1065, "longitude": 35.18449})

    def test_it_asks_for_five(self, get):
        get.return_value = response(self.RESULTS)

        WeatherService().search("Ariel")

        self.assertEqual(get.call_args[1]["params"]["count"], 5)
        self.assertEqual(get.call_args[1]["params"]["language"], "en")

    def test_a_hebrew_query_is_searched_in_hebrew(self, get):
        get.return_value = response(self.RESULTS)

        WeatherService().search("תל")

        self.assertEqual(get.call_args[1]["params"]["language"], "he")

    def test_a_hebrew_town_the_service_does_not_know_falls_back_to_the_english_name(self, get):
        get.side_effect = [response({}), response(self.RESULTS)]

        places = WeatherService().search("אריאל")

        self.assertEqual(get.call_args_list[1][1]["params"]["name"], "Ariel")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["name"], "אריאל")           # shown as typed

    def test_nothing_found_is_an_empty_list_not_an_error(self, get):
        get.return_value = response({})

        self.assertEqual(WeatherService().search("zzzzzz"), [])

    def test_coordinates_skip_the_geocoder_entirely(self, get):
        get.return_value = response(payload())

        result = WeatherService().fetch_at("Ariel", 32.1, 35.2)

        self.assertEqual(get.call_count, 1)
        self.assertEqual(result.place, Place("Ariel", 32.1, 35.2))


class TestGear(unittest.TestCase):

    def test_a_mild_dry_day_needs_nothing_special(self):
        self.assertEqual(gear_for(forecast(min_temp=19, max_temp=23)), [])

    def test_rain_means_an_umbrella(self):
        self.assertIn("umbrella", gear_for(forecast(rain_summary="07:00 (60%)")))

    def test_the_cold_asks_for_a_coat_and_gloves(self):
        gear = gear_for(forecast(min_temp=0, max_temp=6))

        self.assertIn("warm_coat", gear)
        self.assertIn("gloves", gear)
        self.assertNotIn("jacket", gear)

    def test_a_cool_day_asks_for_a_jacket(self):
        self.assertEqual(gear_for(forecast(min_temp=12, max_temp=16)), ["jacket"])

    def test_a_warm_day_that_turns_cold_in_the_evening_asks_for_a_layer(self):
        self.assertIn("jacket", gear_for(forecast(min_temp=10, max_temp=26)))

    def test_wind_asks_for_a_windbreaker_from_either_source(self):
        self.assertIn("windbreaker", gear_for(forecast(wind_kmh=40)))
        self.assertIn("windbreaker", gear_for(forecast(daily=[{"wind": 45}])))
        self.assertNotIn("windbreaker", gear_for(forecast(wind_kmh=15)))

    def test_strong_sun_asks_for_protection(self):
        gear = gear_for(forecast(uv_max=8))

        self.assertEqual({"hat", "sunscreen", "sunglasses"} - set(gear), set())

    def test_a_hot_day_asks_for_water_and_a_hat(self):
        gear = gear_for(forecast(min_temp=24, max_temp=34))

        self.assertIn("water", gear)
        self.assertIn("hat", gear)

    def test_a_small_child_means_a_spare_set(self):
        self.assertIn("spare_clothes", gear_for(forecast(), [{"name": "Noam", "age_category": "baby"}]))
        self.assertIn("spare_clothes", gear_for(forecast(), [{"name": "נועם", "age_category": "ילד"}]))
        self.assertNotIn("spare_clothes", gear_for(forecast(), [{"name": "Dana", "age_category": "adult"}]))

    def test_no_item_appears_twice_and_the_input_is_not_trusted(self):
        gear = gear_for(forecast(min_temp=25, max_temp=36, uv_max=9, wind_kmh=50),
                        ["not a dict", None, {"age_category": 5}])

        self.assertEqual(len(gear), len(set(gear)))


class TestAdviceUsesTheNewData(unittest.TestCase):

    def setUp(self):
        self.advisor = LocalAdvisor()

    def test_wind_is_mentioned_when_it_matters(self):
        self.assertIn("windy", self.advisor.recommend(forecast(wind_kmh=42), []))
        self.assertNotIn("windy", self.advisor.recommend(forecast(wind_kmh=12), []))

    def test_strong_sun_is_mentioned(self):
        text = self.advisor.recommend(forecast(uv_max=9), [])

        self.assertIn("UV", text)
        self.assertIn("9", text)

    def test_feels_like_is_said_only_when_it_differs_enough(self):
        self.assertIn("feels like 14", self.advisor.recommend(
            forecast(current_temp=20, feels_like=14), []))
        self.assertNotIn("feels like", self.advisor.recommend(
            forecast(current_temp=20, feels_like=19), []))

    def test_the_same_in_hebrew(self):
        text = self.advisor.recommend(forecast(wind_kmh=42, uv_max=9), [], language="he")

        self.assertIn("רוח", text)
        self.assertIn("UV", text)
        self.assertNotIn("windy", text)

    def test_the_language_the_page_states_beats_guessing(self):
        """A Hebrew reader who types 'Haifa' in English used to get English advice."""
        text = self.advisor.recommend(forecast(place=Place("Haifa", 1, 1)),
                                      [{"name": "Dana"}], language="he")

        self.assertIn("ב-Haifa", text)

    def test_a_hebrew_name_takes_the_prefix_without_a_hyphen(self):
        text = self.advisor.recommend(forecast(place=Place("אריאל", 1, 1)), [], language="he")

        self.assertTrue(text.startswith("באריאל"))

    def test_an_english_page_with_a_hebrew_city_gets_english(self):
        text = self.advisor.recommend(forecast(place=Place("חיפה", 1, 1)), [], language="en")

        self.assertIn("is ", text)
        self.assertNotIn("היום", text)

    def test_an_unknown_language_falls_back_to_guessing(self):
        self.assertIn("Ariel", self.advisor.recommend(forecast(), [], language="klingon"))

    def test_a_shared_position_has_no_name_to_put_in_a_sentence(self):
        english = self.advisor.recommend(forecast(place=Place("", 1, 1)), [], language="en")
        hebrew = self.advisor.recommend(forecast(place=Place("", 1, 1)), [], language="he")

        self.assertTrue(english.startswith("It is "))
        self.assertNotIn(" is  ", english)
        self.assertTrue(hebrew.startswith("חמים") or hebrew.startswith("נעים") or "היום" in hebrew)
        self.assertFalse(hebrew.startswith("ב "))


class TestLanguageHintPlumbing(unittest.TestCase):

    def test_the_hint_reaches_the_advisor_only_when_there_is_one(self):
        local, ai = MagicMock(), MagicMock(is_configured=False)
        local.recommend.return_value = "text"
        advisor = ClothingAdvisor(ai=ai, local=local)

        advisor.recommend(forecast(), [])
        advisor.recommend(forecast(), [], language="he")

        self.assertEqual(local.recommend.call_args_list[0][1], {})
        self.assertEqual(local.recommend.call_args_list[1][1], {"language": "he"})

    def test_the_ai_prompt_follows_the_hint_and_carries_the_new_numbers(self):
        prompt = AiAdvisor.build_prompt(forecast(feels_like=15, wind_kmh=33, uv_max=7),
                                        [{"name": "Dana"}], language="he")

        self.assertIn("in Hebrew", prompt)
        self.assertIn('"feels_like_c": 15', prompt)
        self.assertIn('"wind_kmh": 33', prompt)
        self.assertIn('"uv_index_max": 7', prompt)

    def test_a_nameless_place_is_sent_as_null_not_as_an_empty_string(self):
        prompt = AiAdvisor.build_prompt(forecast(place=Place("", 1, 1)), [])

        self.assertIn('"place": null', prompt)

    def test_a_source_is_still_reported(self):
        advisor = ClothingAdvisor(ai=MagicMock(is_configured=False), local=LocalAdvisor())

        self.assertEqual(advisor.recommend(forecast(), [], language="he").source, LOCAL)


if __name__ == "__main__":
    unittest.main()
