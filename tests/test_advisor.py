import unittest
from unittest.mock import MagicMock

from src.servers.app_server.advisor import AI, LOCAL, Advice, ClothingAdvisor
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.local_advisor import LocalAdvisor
from src.servers.app_server.weather_api import Forecast, Place

PLACE = Place("Ariel", 32.1, 35.1)


def forecast(low=18.0, high=24.0, now=21.0, rain="No rain expected"):
    return Forecast(PLACE, min_temp=low, max_temp=high,
                    current_temp=now, rain_summary=rain)


ADULT = {"name": "Dana", "gender": "Female", "age_category": "Adult", "notes": ""}
BABY = {"name": "Noam", "gender": "Male", "age_category": "Baby", "notes": "daycare"}
CHILD = {"name": "Yossi", "gender": "Male", "age_category": "Child", "notes": ""}


class TestLocalAdvisor(unittest.TestCase):
    """The no-key path has to be a real recommendation, not a placeholder."""

    def setUp(self):
        self.advisor = LocalAdvisor()

    def test_it_names_the_place_and_the_real_temperatures(self):
        text = self.advisor.recommend(forecast(low=19.9, high=33.3), [])

        self.assertIn("Ariel", text)
        self.assertIn("19.9", text)
        self.assertIn("33.3", text)

    def test_cold_and_hot_give_different_advice(self):
        cold = self.advisor.recommend(forecast(low=1, high=4), [])
        hot = self.advisor.recommend(forecast(low=28, high=36), [])

        self.assertIn("coat", cold)
        self.assertNotIn("coat", hot)
        self.assertNotEqual(cold, hot)

    def test_bands_cover_the_whole_range(self):
        for temperature in (-10, 0, 8, 15, 21, 27, 35, 50):
            word, clothing = self.advisor.band(temperature)
            self.assertTrue(word and clothing, temperature)

    def test_rain_is_mentioned_with_the_hour(self):
        text = self.advisor.recommend(forecast(rain="07:00 (60%), 08:00 (70%)"), [])

        self.assertIn("07:00", text)
        self.assertIn("umbrella", text)

    def test_a_dry_day_says_nothing_about_rain(self):
        self.assertNotIn("umbrella", self.advisor.recommend(forecast(), []))

    def test_a_big_swing_asks_for_an_extra_layer(self):
        text = self.advisor.recommend(forecast(low=12, high=30), [])

        self.assertIn("evening", text)

    def test_a_steady_day_does_not(self):
        self.assertNotIn("evening", self.advisor.recommend(forecast(low=20, high=24), []))

    def test_a_baby_gets_its_own_sentence(self):
        text = self.advisor.recommend(forecast(), [BABY])

        self.assertIn("Noam", text)
        self.assertIn("one more layer", text)

    def test_notes_are_used(self):
        self.assertIn("daycare", self.advisor.recommend(forecast(), [BABY]))

    def test_a_child_is_advised_differently_from_a_baby(self):
        child = self.advisor.recommend(forecast(), [CHILD])
        baby = self.advisor.recommend(forecast(), [BABY])

        self.assertIn("Yossi", child)
        self.assertNotEqual(child, baby)

    def test_it_copes_with_no_profiles_at_all(self):
        for profiles in ([], None, ["not a dict"]):
            self.assertTrue(self.advisor.recommend(forecast(), profiles))


class TestClothingAdvisor(unittest.TestCase):
    """Prefers the AI, always returns something, says which one answered."""

    def test_the_ai_is_used_when_it_is_configured(self):
        ai = MagicMock(is_configured=True, **{"recommend.return_value": "Wear a hat"})
        advisor = ClothingAdvisor(ai=ai, local=MagicMock())

        advice = advisor.recommend(forecast(), [ADULT])

        self.assertEqual(advice, Advice("Wear a hat", AI))
        self.assertTrue(advice.is_ai)

    def test_without_a_key_it_goes_straight_to_the_local_rules(self):
        ai = MagicMock(is_configured=False)
        advisor = ClothingAdvisor(ai=ai, local=LocalAdvisor())

        advice = advisor.recommend(forecast(), [ADULT])

        self.assertEqual(advice.source, LOCAL)
        self.assertTrue(advice.text)
        ai.recommend.assert_not_called()

    def test_a_revoked_key_falls_back_instead_of_failing(self):
        """
        Exactly what happened in practice: Google revokes a key it finds in
        public code, and the app has to keep working.
        """
        ai = MagicMock(is_configured=True, **{
            "recommend.side_effect": ServiceError(
                "AI Error: Your API key was reported as leaked.")})
        advisor = ClothingAdvisor(ai=ai, local=LocalAdvisor())

        advice = advisor.recommend(forecast(), [ADULT])

        self.assertEqual(advice.source, LOCAL)
        self.assertIn("Ariel", advice.text)

    def test_an_outage_falls_back_too(self):
        ai = MagicMock(is_configured=True, **{
            "recommend.side_effect": ServiceError("Could not connect")})
        advisor = ClothingAdvisor(ai=ai, local=LocalAdvisor())

        self.assertEqual(advisor.recommend(forecast(), []).source, LOCAL)

    def test_a_recommendation_is_never_empty(self):
        for ai in (MagicMock(is_configured=False),
                   MagicMock(is_configured=True,
                             **{"recommend.side_effect": ServiceError("x")})):
            advice = ClothingAdvisor(ai=ai, local=LocalAdvisor()).recommend(
                forecast(), [ADULT, BABY])
            self.assertTrue(advice.text.strip())


if __name__ == "__main__":
    unittest.main()
