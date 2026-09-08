import os
import shutil
import time
import unittest

from src.servers.app_server.agent import FileAgent
from src.servers.app_server.file_archive import BANNER, EMPTY
from src.servers.app_server.forecast_cache import HEADER


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

    def test_advice_stored_today_comes_back(self):
        self.agent.store_forecast("Ariel", "Sunny, wear light clothes")

        self.assertEqual(self.agent.cached_forecast("Ariel"),
                         "Sunny, wear light clothes")

    def test_the_stored_file_carries_a_header(self):
        self.agent.store_forecast("Ariel", "advice")

        with open(os.path.join(self.folder, "Ariel_forecast.txt"), encoding="utf-8") as f:
            self.assertTrue(f.read().startswith(HEADER))

    def test_an_unknown_city_is_a_miss(self):
        self.assertIsNone(self.agent.cached_forecast("Atlantis"))

    def test_yesterdays_file_is_stale(self):
        path = self.write("Ariel_forecast.txt", (HEADER + "old advice").encode())
        yesterday = time.time() - 24 * 3600
        os.utime(path, (yesterday, yesterday))

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

    def test_a_report_is_rendered_as_a_table(self):
        self.agent.store_report("Ariel", b"latitude,longitude\n32.1,35.1\n\n"
                                         b"time,temperature_2m,precipitation_probability\n"
                                         b"2026-09-01T00:00,19.9,0\n")

        table = self.agent.archived_file("Ariel_full_report.csv")

        self.assertIn("Date & Time", table)
        self.assertIn("2026-09-01  00:00", table)
        self.assertIn("19.9", table)
        self.assertNotIn("latitude", table)      # the metadata rows are dropped

    def test_the_table_is_not_limited_to_the_2020s(self):
        """The row filter used to test for a literal '202' prefix."""
        self.write("future.csv", b"time,temperature_2m,precipitation_probability\n"
                                 b"2031-01-01T00:00,5.0,10\n")

        self.assertIn("2031-01-01  00:00", self.agent.archived_file("future.csv"))


if __name__ == "__main__":
    unittest.main()
