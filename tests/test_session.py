import json
import unittest
from unittest.mock import MagicMock, patch

from src.client import session


class TestRequestBuilding(unittest.TestCase):

    def test_a_forecast_carries_the_city_and_the_family(self):
        payload = json.loads(session.build_request("FORECAST", "Ariel", [{"name": "A"}]))

        self.assertEqual(payload, {"action": "FORECAST", "city": "Ariel",
                                   "profiles": [{"name": "A"}]})

    def test_an_archive_listing_carries_nothing_else(self):
        payload = json.loads(session.build_request("FTP_LIST", "Ariel", []))

        self.assertEqual(payload, {"action": "FTP_LIST"})


class TestSessionLoop(unittest.TestCase):

    @patch("src.client.session.show_result_gui")
    @patch("src.client.session.get_user_data_gui")
    def test_it_stops_when_the_user_closes_the_window(self, ask, show):
        ask.return_value = (None, None, None, None)

        session.run(MagicMock())

        show.assert_not_called()

    @patch("src.client.session.show_result_gui")
    @patch("src.client.session.get_user_data_gui")
    def test_an_answer_is_displayed(self, ask, show):
        ask.side_effect = [("FORECAST", "Ariel", [], "TCP"), (None, None, None, None)]
        client = MagicMock(**{"request.return_value": "Wear a hat"})

        session.run(client)

        show.assert_called_once_with("FORECAST", "Ariel", "Wear a hat")

    @patch("src.client.session.show_result_gui")
    @patch("src.client.session.get_user_data_gui")
    def test_a_silent_server_is_reported_to_the_user(self, ask, show):
        ask.side_effect = [("FORECAST", "Ariel", [], "RUDP"), (None, None, None, None)]
        client = MagicMock(**{"request.return_value": None})

        session.run(client)

        self.assertEqual(show.call_args[0][0], "ERROR")

    @patch("src.client.session.show_result_gui")
    @patch("src.client.session.show_ftp_list_gui")
    @patch("src.client.session.get_user_data_gui")
    def test_choosing_a_file_fetches_it(self, ask, pick, show):
        ask.side_effect = [("FTP_LIST", "", [], "RUDP"), (None, None, None, None)]
        pick.return_value = "Ariel_forecast.txt"
        client = MagicMock(**{"request.side_effect": ["- listing", "file body"]})

        session.run(client)

        second = json.loads(client.request.call_args_list[1][0][0])
        self.assertEqual(second, {"action": "FTP_GET", "filename": "Ariel_forecast.txt"})
        show.assert_called_once_with("FTP_GET", "Ariel_forecast.txt", "file body")

    @patch("src.client.session.show_result_gui")
    @patch("src.client.session.show_ftp_list_gui")
    @patch("src.client.session.get_user_data_gui")
    def test_closing_the_archive_without_choosing_fetches_nothing(self, ask, pick, show):
        ask.side_effect = [("FTP_LIST", "", [], "RUDP"), (None, None, None, None)]
        pick.return_value = None
        client = MagicMock(**{"request.return_value": "- listing"})

        session.run(client)

        self.assertEqual(client.request.call_count, 1)
        show.assert_not_called()


if __name__ == "__main__":
    unittest.main()
