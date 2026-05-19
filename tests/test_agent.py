import unittest
import os
import shutil
from src.servers.app_server.agent import FileAgent


class TestFileAgent(unittest.TestCase):
    def setUp(self):
        self.agent = FileAgent()
        self.test_dir = "test_dummy_data"
        self.agent.data_folder = self.test_dir
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_text_file(self):
        test_filename = "test_forecast.txt"
        test_content = "Wear a coat today!"

        self.agent.save_text_file(test_filename, test_content)
        file_path = os.path.join(self.test_dir, test_filename)

        self.assertTrue(os.path.exists(file_path))

        with open(file_path, 'r', encoding='utf-8') as f:
            saved_content = f.read()

        self.assertIn("DAILY RECOMMENDATION", saved_content)
        self.assertIn("Wear a coat today!", saved_content)

    def test_get_ftp_file_list(self):
        with open(os.path.join(self.test_dir, "file1.txt"), 'w') as f: f.write("test")
        with open(os.path.join(self.test_dir, "file2.csv"), 'w') as f: f.write("test")

        ftp_list = self.agent.get_ftp_file_list()

        self.assertIn("--- WEATHERWEAR FTP ARCHIVE ---", ftp_list)
        self.assertIn("- file1.txt", ftp_list)
        self.assertIn("- file2.csv", ftp_list)

    def test_get_ftp_file_content_missing(self):
        response = self.agent.get_ftp_file_content("ghost_file.txt")
        self.assertTrue(response.startswith("Error: The file"))

    def test_get_ftp_file_content_path_traversal_protection(self):
        safe_filename = "secret.txt"
        with open(os.path.join(self.test_dir, safe_filename), 'w') as f:
            f.write("Safe Content")

        malicious_request = "../../../secret.txt"

        response = self.agent.get_ftp_file_content(malicious_request)
        self.assertEqual(response, "Safe Content")


if __name__ == '__main__':
    unittest.main()