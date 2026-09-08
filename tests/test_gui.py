"""
The parsing helpers behind the interface.

The windows themselves need a display, but the logic they depend on is plain
data handling and is tested here.
"""
import unittest

from src.client.gui.parsing import parse_listing, parse_profiles, readable


class TestProfileParsing(unittest.TestCase):

    def test_one_profile_per_line(self):
        profiles = parse_profiles("Dana, Female, Adult, runner\nAvi, Male, Baby, ")

        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0], {"name": "Dana", "gender": "Female",
                                       "age_category": "Adult", "notes": "runner"})

    def test_notes_are_optional(self):
        self.assertEqual(parse_profiles("Dana, Female, Adult")[0]["notes"], "")

    def test_incomplete_lines_are_skipped(self):
        self.assertEqual(parse_profiles("Dana, Female\n\n   \n"), [])

    def test_surrounding_spaces_are_trimmed(self):
        self.assertEqual(parse_profiles("  Dana ,  Female , Adult ")[0]["name"], "Dana")


class TestListingParsing(unittest.TestCase):

    LISTING = ("--- WEATHERWEAR FTP ARCHIVE ---\n"
               "- Ariel_forecast.txt (Size: 0.7 KB)\n"
               "- Tel Aviv report.csv (Size: 4.1 KB)\n")

    def test_names_and_sizes_are_read_out_of_the_rows(self):
        self.assertEqual([name for name, _size in parse_listing(self.LISTING)],
                         ["Ariel_forecast.txt", "Tel Aviv report.csv"])

    def test_the_size_is_kept_for_display(self):
        self.assertEqual(parse_listing(self.LISTING)[0][1], "0.7 KB")

    def test_a_name_containing_a_space_stays_whole(self):
        """Splitting on whitespace used to cut such a name in half."""
        self.assertIn("Tel Aviv report.csv",
                      [name for name, _size in parse_listing(self.LISTING)])

    def test_the_banner_is_not_a_file(self):
        self.assertNotIn("--- WEATHERWEAR FTP ARCHIVE ---",
                         [name for name, _size in parse_listing(self.LISTING)])

    def test_an_empty_archive_yields_no_names(self):
        self.assertEqual(parse_listing("FTP Directory is empty"), [])


class TestDisplayableContent(unittest.TestCase):

    def test_text_is_shown_as_it_is(self):
        self.assertEqual(readable("Wear a hat"), "Wear a hat")

    def test_bytes_are_described_instead(self):
        """A text widget cannot display raw bytes."""
        described = readable(b"\x89PNG\r\n")

        self.assertIn("Binary file", described)
        self.assertIn("6 bytes", described)


if __name__ == "__main__":
    unittest.main()
