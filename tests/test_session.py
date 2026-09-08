import json
import unittest
from unittest.mock import MagicMock, patch

from src.client import session

CARD = {"kind": "forecast", "city": "Ariel", "min_temp": 19.9, "max_temp": 33.3,
        "current_temp": 22.6, "rain": "No rain expected",
        "advice": "Go with light clothes.", "source": "local", "cached": False}


def run_now(_message, work):
    """Stand-in for the progress window: run the work and hand back the result."""
    return work()


class TestRequestBuilding(unittest.TestCase):

    def test_a_forecast_carries_the_city_and_the_family(self):
        payload = json.loads(session.build_request("FORECAST", "Ariel", [{"name": "A"}]))

        self.assertEqual(payload, {"action": "FORECAST", "city": "Ariel",
                                   "profiles": [{"name": "A"}]})

    def test_an_archive_listing_carries_nothing_else(self):
        payload = json.loads(session.build_request("FTP_LIST", "Ariel", []))

        self.assertEqual(payload, {"action": "FTP_LIST"})


class TestAnswerRecognition(unittest.TestCase):
    """A forecast is a card; anything else is a message."""

    def test_a_card_is_recognised(self):
        self.assertEqual(session.as_forecast(json.dumps(CARD)), CARD)

    def test_plain_text_is_not_a_card(self):
        self.assertIsNone(session.as_forecast("--- WEATHERWEAR FTP ARCHIVE ---"))

    def test_other_json_is_not_a_card(self):
        self.assertIsNone(session.as_forecast('{"kind": "something else"}'))
        self.assertIsNone(session.as_forecast('[1, 2, 3]'))

    def test_bytes_are_not_a_card(self):
        self.assertIsNone(session.as_forecast(b"\x89PNG"))


@patch("src.client.session.with_progress", run_now)
class TestSessionLoop(unittest.TestCase):

    @patch("src.client.session.show_error")
    @patch("src.client.session.show_forecast")
    @patch("src.client.session.ask_request")
    def test_it_stops_when_the_user_closes_the_window(self, ask, forecast, error):
        ask.return_value = (None, None, None, None)

        session.run(MagicMock())

        forecast.assert_not_called()
        error.assert_not_called()

    @patch("src.client.session.show_forecast")
    @patch("src.client.session.ask_request")
    def test_a_forecast_is_laid_out_as_a_card(self, ask, forecast):
        ask.side_effect = [("FORECAST", "Ariel", [], "TCP"), (None, None, None, None)]
        client = MagicMock(**{"request.return_value": json.dumps(CARD)})

        session.run(client)

        forecast.assert_called_once_with(CARD)

    @patch("src.client.session.show_error")
    @patch("src.client.session.ask_request")
    def test_a_silent_server_is_reported_to_the_user(self, ask, error):
        ask.side_effect = [("FORECAST", "Ariel", [], "RUDP"), (None, None, None, None)]
        client = MagicMock(**{"request.return_value": None})

        session.run(client)

        error.assert_called_once()

    @patch("src.client.session.show_error")
    @patch("src.client.session.ask_request")
    def test_a_server_error_uses_the_error_screen(self, ask, error):
        ask.side_effect = [("FORECAST", "", [], "RUDP"), (None, None, None, None)]
        client = MagicMock(**{"request.return_value":
                              "Error: FORECAST requires a city name."})

        session.run(client)

        error.assert_called_once()

    @patch("src.client.session.show_text")
    @patch("src.client.session.choose_archived_file")
    @patch("src.client.session.ask_request")
    def test_choosing_a_file_fetches_and_shows_it(self, ask, pick, text):
        ask.side_effect = [("FTP_LIST", "", [], "RUDP"), (None, None, None, None)]
        pick.return_value = "Ariel_forecast.json"
        client = MagicMock(**{"request.side_effect": ["- listing", "file body"]})

        session.run(client)

        second = json.loads(client.request.call_args_list[1][0][0])
        self.assertEqual(second,
                         {"action": "FTP_GET", "filename": "Ariel_forecast.json"})
        self.assertEqual(text.call_args[0][:2], ("Ariel_forecast.json", "file body"))

    @patch("src.client.session.show_text")
    @patch("src.client.session.choose_archived_file")
    @patch("src.client.session.ask_request")
    def test_closing_the_archive_without_choosing_fetches_nothing(self, ask, pick, text):
        ask.side_effect = [("FTP_LIST", "", [], "RUDP"), (None, None, None, None)]
        pick.return_value = None
        client = MagicMock(**{"request.return_value": "- listing"})

        session.run(client)

        self.assertEqual(client.request.call_count, 1)
        text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
