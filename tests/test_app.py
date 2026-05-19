import unittest
import json
from unittest.mock import MagicMock, patch
from src.servers.app_server.app import AppServer

class TestAppServer(unittest.TestCase):
    def setUp(self):
        # Mock OS sockets to prevent port conflicts during test execution
        self.patcher = patch('src.servers.app_server.app.socket.socket')
        self.mock_socket = self.patcher.start()

        self.server = AppServer()
        self.server.logic = MagicMock()
        self.server.agent = MagicMock()

    def tearDown(self):
        self.patcher.stop()

    def test_process_request_ftp_list(self):
        self.server.agent.get_ftp_file_list.return_value = "MOCK_FTP_LIST"
        payload = {"action": "FTP_LIST"}

        response = self.server.process_request(payload)

        self.assertEqual(response, "MOCK_FTP_LIST")
        self.server.agent.get_ftp_file_list.assert_called_once()

    def test_process_request_unknown_action(self):
        payload = {"action": "HACK_SERVER"}

        response = self.server.process_request(payload)

        self.assertEqual(response, "Error: Unknown action requested.")
        self.server.logic.fetch_weather.assert_not_called()
        self.server.agent.get_ftp_file_list.assert_not_called()

    def test_handle_tcp_client(self):
        # Mocking a TCP client socket connection
        mock_client_sock = MagicMock()

        # Simulate the client sending a valid JSON payload for Ariel
        test_payload = {"action": "FORECAST", "city": "Ariel"}
        mock_client_sock.recv.return_value = json.dumps(test_payload).encode('utf-8')

        # Intercept the server's routing function to return a fixed string
        self.server.process_request = MagicMock(return_value="Wear a jacket!")

        # Execute the TCP handler with the mocked socket
        self.server.handle_tcp_client(mock_client_sock, ("127.0.0.1", 55555))

        # Verify the entire TCP lifecycle: receive -> process -> send -> close
        mock_client_sock.recv.assert_called_once_with(4096)
        self.server.process_request.assert_called_once_with(test_payload)
        mock_client_sock.sendall.assert_called_once_with(b"Wear a jacket!")
        mock_client_sock.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()