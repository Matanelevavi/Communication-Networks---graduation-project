"""
The parsing helpers behind the interface.

The windows themselves need a display, but the logic they depend on is plain
data handling and is tested here.
"""
import unittest

from src.client.gui.parsing import is_rtl, parse_listing, parse_profiles, readable


class TestDirection(unittest.TestCase):

    def test_hebrew_reads_right_to_left(self):
        self.assertTrue(is_rtl("אריאל"))
        self.assertTrue(is_rtl("ב-Ariel חם היום"))

    def test_english_and_non_text_do_not(self):
        for value in ("Ariel", "", None, b"\xd7\x90"):
            self.assertFalse(is_rtl(value))


class TestProfileParsing(unittest.TestCase):

    def test_one_profile_per_line(self):
        profiles = parse_profiles("Dana, Adult, runner\nAvi, Baby, ")

        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0], {"name": "Dana", "age_category": "Adult",
                                       "notes": "runner"})

    def test_notes_are_optional(self):
        self.assertEqual(parse_profiles("Dana, Adult")[0]["notes"], "")

    def test_a_name_alone_is_enough(self):
        """A line with fewer than three fields used to vanish without a word."""
        self.assertEqual(parse_profiles("Dana"),
                         [{"name": "Dana", "age_category": "", "notes": ""}])

    def test_a_note_may_contain_a_comma(self):
        self.assertEqual(parse_profiles("Noam, Baby, daycare, then grandma")[0]["notes"],
                         "daycare, then grandma")

    def test_blank_lines_are_skipped(self):
        self.assertEqual(parse_profiles("\n\n   \n , Adult"), [])

    def test_hebrew_is_kept_as_typed(self):
        self.assertEqual(parse_profiles("נועם, תינוק")[0],
                         {"name": "נועם", "age_category": "תינוק", "notes": ""})

    def test_surrounding_spaces_are_trimmed(self):
        self.assertEqual(parse_profiles("  Dana ,  Adult ")[0]["name"], "Dana")


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
