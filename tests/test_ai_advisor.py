import unittest
from unittest.mock import patch

import requests

from src.servers.app_server.ai_advisor import GEMINI_URL, MOCK_ADVICE, AiAdvisor
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.weather_api import Forecast, Place

FORECAST = Forecast(Place("Ariel", 32.1, 35.1), min_temp=18, max_temp=30,
                    current_temp=25, rain_summary="No rain expected")

ANSWER = {"candidates": [{"content": {"parts": [{"text": "Wear a hat"}]}}]}


def advisor():
    return AiAdvisor(api_key="test-key", use_mock=False)


class TestPrompt(unittest.TestCase):

    def test_it_names_the_place_the_range_and_the_family(self):
        prompt = AiAdvisor.build_prompt(FORECAST, [{"name": "Dana"}])

        self.assertIn("Ariel", prompt)
        self.assertIn("18C to 30C", prompt)
        self.assertIn("Dana", prompt)


class TestMockMode(unittest.TestCase):

    @patch("src.servers.app_server.ai_advisor.requests.post")
    def test_no_call_is_made(self, post):
        answer = AiAdvisor(api_key="", use_mock=True).recommend(FORECAST, [])

        self.assertEqual(answer, MOCK_ADVICE)
        post.assert_not_called()


@patch("src.servers.app_server.ai_advisor.requests.post")
class TestLiveMode(unittest.TestCase):

    def test_a_successful_recommendation(self, post):
        post.return_value.json.return_value = ANSWER

        self.assertEqual(advisor().recommend(FORECAST, []), "Wear a hat")

    def test_the_key_travels_in_a_header_not_in_the_url(self, post):
        """Keeps it out of proxy logs and out of a packet capture of the URL."""
        post.return_value.json.return_value = ANSWER

        advisor().recommend(FORECAST, [])

        self.assertEqual(post.call_args[0][0], GEMINI_URL)
        self.assertNotIn("key=", post.call_args[0][0])
        self.assertEqual(post.call_args[1]["headers"]["x-goog-api-key"], "test-key")

    def test_hebrew_profiles_never_reach_the_network(self, post):
        with self.assertRaises(ServiceError):
            advisor().recommend(FORECAST, [{"name": "דני"}])

        post.assert_not_called()

    def test_a_quota_error_is_raised_not_returned(self, post):
        """Raising is what keeps a transient failure out of the daily cache."""
        post.return_value.json.return_value = {"error": {"message": "quota exceeded"}}

        with self.assertRaises(ServiceError) as caught:
            advisor().recommend(FORECAST, [])

        self.assertIn("quota exceeded", str(caught.exception))

    def test_an_unreachable_service(self, post):
        post.side_effect = requests.RequestException("timeout")

        with self.assertRaises(ServiceError) as caught:
            advisor().recommend(FORECAST, [])

        self.assertIn("Could not connect", str(caught.exception))

    def test_an_answer_in_an_unexpected_shape(self, post):
        post.return_value.json.return_value = {"candidates": [{"nonsense": True}]}

        with self.assertRaises(ServiceError):
            advisor().recommend(FORECAST, [])


if __name__ == "__main__":
    unittest.main()
