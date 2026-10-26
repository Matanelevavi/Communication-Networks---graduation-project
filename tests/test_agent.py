import json
import os
import shutil
import time
import unittest

from src.config import FORECAST_CACHE_TTL
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.file_archive import BANNER, EMPTY
from src.servers.app_server.forecast_cache import city_key

FORECAST = {
    "city": "Ariel", "latitude": 32.1, "longitude": 35.1,
    "min_temp": 19.9, "max_temp": 33.3, "current_temp": 22.6,
    "rain": "No rain expected",
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

    def age(self, name, seconds):
        path = os.path.join(self.folder, name)
        then = time.time() - seconds
        os.utime(path, (then, then))


class TestCityKey(unittest.TestCase):

    def test_case_and_spacing_share_one_entry(self):
        """'ariel' and 'Ariel' used to be cached, and fetched, separately."""
        self.assertEqual(city_key("Ariel"), city_key("  ariel "))
        self.assertEqual(city_key("Tel Aviv"), city_key("TEL   aviv"))

    def test_a_name_can_never_form_a_path(self):
        for name in ("../../etc/passwd", "a/b\\c", "..", "C:\\x"):
            key = city_key(name)
            self.assertNotIn("/", key)
            self.assertNotIn("\\", key)
            self.assertNotIn("..", key)

    def test_hebrew_is_kept(self):
        self.assertEqual(city_key("תל אביב"), "תל_אביב")


class TestCache(AgentTestCase):

    def test_a_recent_forecast_comes_back_whole(self):
        self.agent.store_forecast("Ariel", FORECAST)

        self.assertEqual(self.agent.cached_forecast("Ariel"), FORECAST)

    def test_another_spelling_of_the_same_city_hits(self):
        self.agent.store_forecast("Ariel", FORECAST)

        self.assertEqual(self.agent.cached_forecast(" ARIEL "), FORECAST)

    def test_it_is_stored_as_readable_json(self):
        self.agent.store_forecast("Ariel", FORECAST)

        with open(os.path.join(self.folder, "ariel_forecast.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), FORECAST)

    def test_an_unknown_city_is_a_miss(self):
        self.assertIsNone(self.agent.cached_forecast("Atlantis"))

    def test_a_forecast_older_than_the_ttl_is_stale(self):
        """A whole day used to count, so "right now" stayed frozen at the morning."""
        self.agent.store_forecast("Ariel", FORECAST)
        self.age("ariel_forecast.json", FORECAST_CACHE_TTL + 60)

        self.assertIsNone(self.agent.cached_forecast("Ariel"))

    def test_a_forecast_inside_the_ttl_is_fresh(self):
        self.agent.store_forecast("Ariel", FORECAST)
        self.age("ariel_forecast.json", FORECAST_CACHE_TTL / 2)

        self.assertEqual(self.agent.cached_forecast("Ariel"), FORECAST)

    def test_a_corrupted_entry_is_discarded_rather_than_served(self):
        self.write("ariel_forecast.json", b"{not json")

        self.assertIsNone(self.agent.cached_forecast("Ariel"))

    def test_json_that_is_not_an_object_is_discarded(self):
        self.write("ariel_forecast.json", b"[1, 2, 3]")

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

    def test_names_the_platform_cannot_place_are_refused_not_raised(self):
        """Fuzzing found that '::::' raised ValueError out of os.path.commonpath."""
        for name in ("::::", "C:\\Windows\\win.ini", "a\x00b", "..", ".", "..\\..\\x",
                     "file.txt:stream"):
            path = self.agent.store.resolve(name)
            if path is not None:
                self.assertTrue(path.startswith(os.path.realpath(self.folder)), name)

    def test_a_backslash_is_a_separator_on_every_platform(self):
        self.write("secret.txt", b"Safe Content")

        self.assertEqual(self.agent.archived_file("..\\..\\secret.txt"), "Safe Content")

    def test_a_binary_file_comes_back_as_bytes(self):
        """Reading in text mode used to raise UnicodeDecodeError."""
        self.write("photo.bin", b"\x89PNG\r\n\x1a\n\xff\xfe")

        self.assertEqual(self.agent.archived_file("photo.bin"),
                         b"\x89PNG\r\n\x1a\n\xff\xfe")

    def test_a_stored_forecast_is_rendered_as_a_report(self):
        """The cache holds data; a person reading the archive wants labels."""
        self.agent.store_forecast("Ariel", FORECAST)

        report = self.agent.archived_file("ariel_forecast.json")

        self.assertIn("Forecast for Ariel", report)
        self.assertIn("19.9", report)
        self.assertIn("No rain expected", report)
        self.assertNotIn("min_temp", report)      # not the raw JSON

    def test_unreadable_json_is_returned_as_it_is(self):
        self.write("broken.json", b"{not json")

        self.assertEqual(self.agent.archived_file("broken.json"), "{not json")

    def test_a_report_is_rendered_as_a_table(self):
        self.agent.store_report("Ariel", b"latitude,longitude\n32.1,35.1\n\n"
                                         b"time,temperature_2m,precipitation_probability\n"
                                         b"2026-09-01T00:00,19.9,0\n")

        table = self.agent.archived_file("ariel_full_report.csv")

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
