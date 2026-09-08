import json
import os
import shutil
import time
import unittest

from src.servers.app_server.agent import FileAgent
from src.servers.app_server.file_archive import BANNER, EMPTY

CARD = {
    "kind": "forecast", "city": "Ariel", "min_temp": 19.9, "max_temp": 33.3,
    "current_temp": 22.6, "rain": "No rain expected",
    "advice": "Ariel is hot today, go with light clothes.", "source": "local",
}


class AgentTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.abspath("test_dummy_data")
        shutil.rmtree(self.folder, ignore_errors=True)
        self.agent = FileAgent(data_folder=self.folder)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def write(self, name, data=b"test"):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as f:
            f.write(data)
        return path


class TestCache(AgentTestCase):

    def test_a_card_stored_today_comes_back_whole(self):
        self.agent.store_forecast("Ariel", CARD)

        self.assertEqual(self.agent.cached_forecast("Ariel"), CARD)

    def test_it_is_stored_as_readable_json(self):
        self.agent.store_forecast("Ariel", CARD)

        with open(os.path.join(self.folder, "Ariel_forecast.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), CARD)

    def test_an_unknown_city_is_a_miss(self):
        self.assertIsNone(self.agent.cached_forecast("Atlantis"))

    def test_yesterdays_file_is_stale(self):
        self.agent.store_forecast("Ariel", CARD)
        path = os.path.join(self.folder, "Ariel_forecast.json")
        yesterday = time.time() - 24 * 3600
        os.utime(path, (yesterday, yesterday))

        self.assertIsNone(self.agent.cached_forecast("Ariel"))

    def test_a_corrupted_entry_is_discarded_rather_than_served(self):
        self.write("Ariel_forecast.json", b"{not json")

        self.assertIsNone(self.agent.cached_forecast("Ariel"))


class TestArchive(AgentTestCase):

    def test_the_listing_names_every_file(self):
        self.write("file1.txt")
        self.write("file2.csv")

        listing = self.agent.archive_listing()

        self.assertIn(BANNER, listing)
        self.assertIn("- file1.txt", listing)
        self.assertIn("- file2.csv", listing)

    def test_an_empty_archive_says_so(self):
        self.assertEqual(self.agent.archive_listing(), EMPTY)

    def test_a_missing_file_is_reported(self):
        self.assertTrue(self.agent.archived_file("ghost.txt").startswith("Error: The file"))

    def test_a_traversal_attempt_cannot_escape(self):
        self.write("secret.txt", b"Safe Content")

        self.assertEqual(self.agent.archived_file("../../../secret.txt"), "Safe Content")

    def test_a_binary_file_comes_back_as_bytes(self):
        """Reading in text mode used to raise UnicodeDecodeError."""
        self.write("photo.bin", b"\x89PNG\r\n\x1a\n\xff\xfe")

        self.assertEqual(self.agent.archived_file("photo.bin"),
                         b"\x89PNG\r\n\x1a\n\xff\xfe")

    def test_a_stored_forecast_is_rendered_as_a_report(self):
        """The cache holds data; a person reading the archive wants prose."""
        self.agent.store_forecast("Ariel", CARD)

        report = self.agent.archived_file("Ariel_forecast.json")

        self.assertIn("Forecast for Ariel", report)
        self.assertIn("19.9", report)
        self.assertIn("What to wear", report)
        self.assertIn("light clothes", report)
        self.assertIn("local advisor", report)
        self.assertNotIn("min_temp", report)      # not the raw JSON

    def test_an_ai_written_forecast_says_so(self):
        self.agent.store_forecast("Ariel", {**CARD, "source": "ai"})

        self.assertIn("AI advisor", self.agent.archived_file("Ariel_forecast.json"))

    def test_unreadable_json_is_returned_as_it_is(self):
        self.write("broken.json", b"{not json")

        self.assertEqual(self.agent.archived_file("broken.json"), "{not json")

    def test_a_report_is_rendered_as_a_table(self):
        self.agent.store_report("Ariel", b"latitude,longitude\n32.1,35.1\n\n"
                                         b"time,temperature_2m,precipitation_probability\n"
                                         b"2026-09-01T00:00,19.9,0\n")

        table = self.agent.archived_file("Ariel_full_report.csv")

        self.assertIn("Date & Time", table)
        self.assertIn("2026-09-01  00:00", table)
        self.assertNotIn("latitude", table)      # the metadata rows are dropped

    def test_the_table_is_not_limited_to_the_2020s(self):
        """The row filter used to test for a literal '202' prefix."""
        self.write("future.csv", b"time,temperature_2m,precipitation_probability\n"
                                 b"2031-01-01T00:00,5.0,10\n")

        self.assertIn("2031-01-01  00:00", self.agent.archived_file("future.csv"))


if __name__ == "__main__":
    unittest.main()
