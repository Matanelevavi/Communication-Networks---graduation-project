"""
The website: the gateway onto the simulated network, the rate limit, and the
HTTP API in front of them.

The gateway is tested against a fake network client, and the API against a
fake gateway, so nothing here opens a socket.
"""
import json
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.web.app import SECURITY_HEADERS, create_app
from src.web.gateway import Exchange, GatewayError, NetworkGateway
from src.web.limits import RateLimiter

CARD = {"kind": "forecast", "city": "Ariel", "min_temp": 18, "max_temp": 30,
        "current_temp": 25, "rain": "No rain expected", "advice": "Wear a hat",
        "source": "local", "cached": False}
LISTING = ("--- WEATHERWEAR FTP ARCHIVE ---\n"
           "- ariel_forecast.json (Size: 0.3 KB)\n")


def fake_client(answer=json.dumps(CARD), joins=True, stats=None):
    """A NetworkClient stand-in whose transport answers with ``answer``."""
    transport = MagicMock(stats=stats or {})
    transport.request.return_value = answer
    client = MagicMock(my_ip="192.168.1.100", app_server_ip="127.0.0.1")
    client.connect.return_value = joins
    client.transport_for.return_value = transport
    return client


class TestGateway(unittest.TestCase):

    def gateway(self, client):
        return NetworkGateway(client_factory=lambda: client)

    def test_it_joins_the_network_once(self):
        client = fake_client()
        gateway = self.gateway(client)

        gateway.forecast("Ariel", [], "RUDP")
        gateway.forecast("Ariel", [], "TCP")

        client.connect.assert_called_once()
        self.assertEqual(gateway.status["ip"], "192.168.1.100")

    def test_a_forecast_comes_back_as_a_card_with_its_transfer(self):
        gateway = self.gateway(fake_client(stats={"chunks": 1, "datagrams": 1}))

        card, exchange = gateway.forecast("Ariel", [{"name": "Dana"}], "RUDP")

        self.assertEqual(card, CARD)
        transfer = exchange.transfer()
        self.assertEqual(transfer["protocol"], "RUDP")
        self.assertEqual(transfer["chunks"], 1)
        self.assertGreater(transfer["bytes"], 0)

    def test_the_request_travels_as_the_app_server_expects(self):
        client = fake_client()
        self.gateway(client).forecast("אריאל", [{"name": "נועם"}], "TCP")

        client.transport_for.assert_called_with("TCP")
        sent = json.loads(client.transport_for.return_value.request.call_args[0][0])
        self.assertEqual(sent, {"action": "FORECAST", "city": "אריאל",
                                "profiles": [{"name": "נועם"}]})

    def test_a_server_error_is_not_a_card(self):
        gateway = self.gateway(fake_client("Error: 'Atlantis' was not found."))

        card, exchange = gateway.forecast("Atlantis", [], "RUDP")

        self.assertIsNone(card)
        self.assertEqual(exchange.error_message, "'Atlantis' was not found.")

    def test_silence_is_a_gateway_error(self):
        with self.assertRaises(GatewayError):
            self.gateway(fake_client(answer=None)).forecast("Ariel", [], "RUDP")

    def test_a_network_that_cannot_be_joined_is_a_gateway_error(self):
        client = fake_client(joins=False)

        with self.assertRaises(GatewayError):
            self.gateway(client).forecast("Ariel", [], "RUDP")
        client.close.assert_called_once()

    def test_an_unknown_protocol_is_refused(self):
        with self.assertRaises(ValueError):
            self.gateway(fake_client()).exchange({}, "SCTP")

    def test_the_archive_listing_becomes_data(self):
        files, _ = self.gateway(fake_client(LISTING)).archive("TCP")

        self.assertEqual(files, [{"name": "ariel_forecast.json", "size": "0.3 KB"}])


class TestRateLimiter(unittest.TestCase):

    def test_it_allows_up_to_the_limit_then_refuses(self):
        limiter = RateLimiter(3, clock=lambda: 100.0)

        self.assertEqual([limiter.allow("a") for _ in range(4)], [True, True, True, False])

    def test_each_visitor_has_their_own_budget(self):
        limiter = RateLimiter(1, clock=lambda: 100.0)

        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("b"))

    def test_the_window_slides(self):
        now = [100.0]
        limiter = RateLimiter(1, window=60, clock=lambda: now[0])

        limiter.allow("a")
        now[0] += 61
        self.assertTrue(limiter.allow("a"))

    def test_it_says_when_to_try_again(self):
        now = [100.0]
        limiter = RateLimiter(1, window=60, clock=lambda: now[0])
        limiter.allow("a")
        now[0] += 20

        self.assertEqual(limiter.retry_after("a"), 41)


class ApiTestCase(unittest.TestCase):

    def setUp(self):
        self.gateway = MagicMock()
        self.gateway.join.return_value = True
        self.gateway.status = {"joined": True, "ip": "192.168.1.100"}
        self.limiter = RateLimiter(1000)
        self.client = TestClient(create_app(self.gateway, self.limiter))

    @staticmethod
    def exchange(answer, protocol="RUDP"):
        return Exchange(protocol, answer, 12.3, len(answer), {"chunks": 1})


class TestForecastApi(ApiTestCase):

    def post(self, **body):
        return self.client.post("/api/forecast", json={"city": "Ariel", **body})

    def test_a_forecast(self):
        self.gateway.forecast.return_value = (CARD, self.exchange(json.dumps(CARD)))

        response = self.post(profiles=[{"name": "Dana", "age_category": "adult"}],
                             protocol="TCP")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["forecast"], CARD)
        self.assertEqual(response.json()["transfer"]["chunks"], 1)
        city, profiles, protocol = self.gateway.forecast.call_args[0]
        self.assertEqual((city, protocol), ("Ariel", "TCP"))
        self.assertEqual(profiles, [{"name": "Dana", "age_category": "adult", "notes": ""}])

    def test_a_server_error_is_a_422_with_its_message(self):
        self.gateway.forecast.return_value = (None, self.exchange("Error: 'X' was not found."))

        response = self.post()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "'X' was not found.")

    def test_an_unreachable_network_is_a_503(self):
        self.gateway.forecast.side_effect = GatewayError("no answer")

        response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("no answer", response.text)      # no internals

    def test_input_is_validated_before_it_reaches_the_network(self):
        for body in ({"city": ""}, {"city": "x" * 81},
                     {"city": "Ariel", "protocol": "SCTP"},
                     {"city": "Ariel", "profiles": [{"name": "A"}] * 11},
                     {"city": "Ariel", "profiles": [{"name": "A" * 41}]},
                     {"city": "Ariel", "profiles": [{"notes": "no name"}]}):
            self.assertEqual(self.client.post("/api/forecast", json=body).status_code,
                             422, body)
        self.gateway.forecast.assert_not_called()


class TestArchiveApi(ApiTestCase):

    def test_the_listing(self):
        self.gateway.archive.return_value = ([{"name": "a.json", "size": "1 KB"}],
                                             self.exchange(LISTING))

        body = self.client.get("/api/archive?protocol=TCP").json()

        self.assertEqual(body["files"], [{"name": "a.json", "size": "1 KB"}])
        self.gateway.archive.assert_called_once_with("TCP")

    def test_a_file(self):
        self.gateway.archived_file.return_value = self.exchange("Forecast for Ariel")

        body = self.client.get("/api/archive/ariel_forecast.json").json()

        self.assertEqual(body["content"], "Forecast for Ariel")

    def test_a_missing_file_is_a_404(self):
        self.gateway.archived_file.return_value = self.exchange("Error: The file does not exist.")

        self.assertEqual(self.client.get("/api/archive/nope.json").status_code, 404)

    def test_a_binary_file_is_not_sent_as_text(self):
        self.gateway.archived_file.return_value = Exchange("RUDP", b"\x89PNG", 1, 4)

        self.assertEqual(self.client.get("/api/archive/photo.png").status_code, 415)


class TestProtection(ApiTestCase):

    def test_every_response_carries_the_security_headers(self):
        for path in ("/", "/api/health"):
            response = self.client.get(path)
            for name in SECURITY_HEADERS:
                self.assertIn(name, response.headers, path)

    def test_api_answers_are_never_cached(self):
        self.assertEqual(self.client.get("/api/health").headers["cache-control"], "no-store")

    def test_a_visitor_over_the_limit_is_told_to_wait(self):
        client = TestClient(create_app(self.gateway, RateLimiter(2)))
        self.gateway.archive.return_value = ([], self.exchange(LISTING))

        codes = [client.get("/api/archive").status_code for _ in range(3)]

        self.assertEqual(codes, [200, 200, 429])
        self.assertIn("retry-after", client.get("/api/archive").headers)

    def test_the_health_check_is_never_rate_limited(self):
        client = TestClient(create_app(self.gateway, RateLimiter(1)))

        codes = {client.get("/api/health").status_code for _ in range(5)}

        self.assertEqual(codes, {200})

    def test_the_site_is_served(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("WeatherWear", response.text)
        self.assertIn("app.js", response.text)


if __name__ == "__main__":
    unittest.main()
