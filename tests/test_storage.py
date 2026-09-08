import os
import shutil
import unittest

from src.servers.app_server.storage import FileStore


class FileStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = os.path.abspath("test_dummy_data")
        shutil.rmtree(self.folder, ignore_errors=True)
        self.store = FileStore(self.folder)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def write(self, name, data=b"test"):
        with open(os.path.join(self.folder, name), "wb") as f:
            f.write(data)


class TestContainment(FileStoreTestCase):

    def test_a_plain_name_resolves_inside_the_folder(self):
        path = self.store.resolve("report.csv")

        self.assertEqual(os.path.dirname(path), os.path.realpath(self.folder))

    def test_a_traversal_attempt_is_stripped(self):
        """`../../../etc/passwd` becomes `passwd`, inside the archive."""
        path = self.store.resolve("../../../etc/passwd")

        self.assertEqual(os.path.basename(path), "passwd")
        self.assertEqual(os.path.dirname(path), os.path.realpath(self.folder))

    def test_an_empty_name_resolves_to_nothing(self):
        self.assertIsNone(self.store.resolve(""))
        self.assertIsNone(self.store.resolve("../"))


class TestReadingAndWriting(FileStoreTestCase):

    def test_text_round_trip(self):
        self.assertTrue(self.store.write_text("a.txt", "hello"))

        self.assertEqual(self.store.read_bytes("a.txt"), b"hello")

    def test_binary_round_trip(self):
        self.assertTrue(self.store.write_bytes("a.bin", b"\x00\xff"))

        self.assertEqual(self.store.read_bytes("a.bin"), b"\x00\xff")

    def test_reading_a_missing_file_returns_nothing(self):
        self.assertIsNone(self.store.read_bytes("ghost.txt"))

    def test_the_modification_time_of_a_missing_file_is_nothing(self):
        self.assertIsNone(self.store.modified_at("ghost.txt"))


class TestListing(FileStoreTestCase):

    def test_files_are_listed_with_their_size_in_order(self):
        self.write("b.txt", b"12345")
        self.write("a.txt", b"1")

        self.assertEqual(self.store.list_files(), [("a.txt", 1), ("b.txt", 5)])

    def test_directories_are_skipped(self):
        """getsize on a directory used to report it as a downloadable file."""
        self.write("a.txt")
        os.makedirs(os.path.join(self.folder, "a_folder"), exist_ok=True)

        self.assertEqual([name for name, _ in self.store.list_files()], ["a.txt"])

    def test_dotfiles_are_skipped(self):
        self.write("a.txt")
        self.write(".gitkeep", b"")

        self.assertEqual([name for name, _ in self.store.list_files()], ["a.txt"])

    def test_an_empty_folder_lists_nothing(self):
        self.assertEqual(self.store.list_files(), [])


if __name__ == "__main__":
    unittest.main()
