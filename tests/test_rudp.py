import unittest
from unittest.mock import MagicMock, patch
from src.servers.app_server.rudp import RUDP

class TestRUDPHandler(unittest.TestCase):
    @patch('src.servers.app_server.rudp.LOSS_RATE', 0.0)
    @patch('src.servers.app_server.rudp.SIMULATE_LOSS', False)
    def test_chunking_and_sending(self):
        mock_sock = MagicMock()
        handler = RUDP(mock_sock)

        # test small chunk size
        handler.chunk_size = 10
        test_data = "Hello World 123"

        mock_sock.recvfrom.side_effect = [
            (b"ACK:1", ("127.0.0.1",9999)),
            (b"ACK:2", ("127.0.0.1",9999))
        ]

        handler.reliable_send(test_data, ("127.0.0.1",9999))

        self.assertGreaterEqual(mock_sock.sendto.call_count,2)

        first_packet = mock_sock.sendto.call_args_list[0][0][0]
        second_packet = mock_sock.sendto.call_args_list[1][0][0]

        # check headers and payload
        self.assertTrue(first_packet.startswith(b"SEQ:1|TOTAL:2|"))
        self.assertIn(b"Hello Worl", first_packet)

        self.assertTrue(second_packet.startswith(b"SEQ:2|TOTAL:2|"))
        self.assertIn(b"d 123", second_packet)


if __name__ == '__main__':
    unittest.main()