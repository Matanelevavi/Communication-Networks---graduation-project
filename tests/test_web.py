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

    def test_a_position_the_browser_shared_goes_as_coordinates_with_the_language(self):
        self.gateway.forecast.return_value = (CARD, self.exchange(json.dumps(CARD)))

        response = self.client.post("/api/forecast", json={
            "lat": 32.1065, "lon": 35.18449, "lang": "he", "protocol": "TCP"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.gateway.forecast.call_args[0][0], "")
        self.assertEqual(self.gateway.forecast.call_args[1],
                         {"lat": 32.1065, "lon": 35.18449, "lang": "he"})

    def test_a_chosen_place_keeps_its_name_beside_its_coordinates(self):
        self.gateway.forecast.return_value = (CARD, self.exchange(json.dumps(CARD)))

        self.post(lat=32.1, lon=35.2)

        self.assertEqual(self.gateway.forecast.call_args[0][0], "Ariel")
        self.assertEqual(self.gateway.forecast.call_args[1], {"lat": 32.1, "lon": 35.2})

    def test_a_plain_city_request_is_still_exactly_the_old_call(self):
        self.gateway.forecast.return_value = (CARD, self.exchange(json.dumps(CARD)))

        self.post()

        self.assertEqual(self.gateway.forecast.call_args[1], {})

    def test_bad_places_are_refused_before_the_network(self):
        for body in ({"lat": 32.1}, {"lon": 35.2}, {"lat": 91, "lon": 0}, {"lat": 0, "lon": -181},
                     {"city": "", "profiles": []}, {"lat": "north", "lon": 1},
                     {"city": "Ariel", "lang": "fr"}):
            self.assertEqual(self.client.post("/api/forecast", json=body).status_code, 422, body)
        self.gateway.forecast.assert_not_called()

    def test_input_is_validated_before_it_reaches_the_network(self):
        for body in ({"city": ""}, {"city": "x" * 81},
                     {"city": "Ariel", "protocol": "SCTP"},
                     {"city": "Ariel", "profiles": [{"name": "A"}] * 11},
                     {"city": "Ariel", "profiles": [{"name": "A" * 41}]},
                     {"city": "Ariel", "profiles": [{"notes": "no name"}]}):
            self.assertEqual(self.client.post("/api/forecast", json=body).status_code,
                             422, body)
        self.gateway.forecast.assert_not_called()


class TestSearchApi(ApiTestCase):

    PLACES = [{"name": "Ariel", "admin1": "Judea", "country": "Israel",
               "latitude": 32.1, "longitude": 35.2}]

    def test_suggestions(self):
        self.gateway.search.return_value = (self.PLACES, self.exchange("{}"))

        body = self.client.get("/api/search", params={"q": "Ariel"}).json()

        self.assertEqual(body, {"places": self.PLACES})
        self.gateway.search.assert_called_once_with("Ariel", "TCP")

    def test_the_query_is_bounded_before_it_goes_anywhere(self):
        for q in ("", "a", "x" * 61):
            self.assertEqual(self.client.get("/api/search", params={"q": q}).status_code, 422, q)
        self.assertEqual(self.client.get("/api/search").status_code, 422)
        self.gateway.search.assert_not_called()

    def test_an_unknown_transport_is_refused(self):
        self.assertEqual(self.client.get("/api/search", params={"q": "Ariel", "protocol": "SCTP"}).status_code, 422)

    def test_an_unreachable_network_is_a_503(self):
        self.gateway.search.side_effect = GatewayError("no answer")

        self.assertEqual(self.client.get("/api/search", params={"q": "Ariel"}).status_code, 503)

    def test_suggestions_have_a_budget_of_their_own(self):
        self.gateway.search.return_value = ([], self.exchange("{}"))
        self.gateway.archive.return_value = ([], self.exchange(LISTING))
        client = TestClient(create_app(self.gateway, RateLimiter(1), RateLimiter(1000),
                                       RateLimiter(3)))

        codes = [client.get("/api/search", params={"q": "Ariel"}).status_code for _ in range(4)]

        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertEqual(client.get("/api/archive").status_code, 200)    # forecasts unaffected


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


class TestVisitorIdentity(unittest.TestCase):
    """Behind Render the peer is 127.0.0.1 and the proxy hops change each time."""

    @staticmethod
    def visitor(headers, trust=True):
        import src.web.app as web
        request = MagicMock(headers=headers, client=MagicMock(host="127.0.0.1"))
        previous, web.TRUST_PROXY = web.TRUST_PROXY, trust
        try:
            return web.visitor(request)
        finally:
            web.TRUST_PROXY = previous

    def test_the_visitor_is_the_address_cloudflare_reports(self):
        # the same person, through two different edge and proxy hops
        first = {"cf-connecting-ip": "192.114.52.12",
                 "x-forwarded-for": "192.114.52.12, 172.70.108.67, 10.30.47.157"}
        second = {"cf-connecting-ip": "192.114.52.12",
                  "x-forwarded-for": "192.114.52.12, 172.71.147.4, 10.31.55.151"}

        self.assertEqual(self.visitor(first), "192.114.52.12")
        self.assertEqual(self.visitor(first), self.visitor(second))

    def test_without_that_header_the_third_hop_from_the_end_is_used(self):
        forwarded = {"x-forwarded-for": "192.114.52.12, 172.70.108.67, 10.30.47.157"}

        self.assertEqual(self.visitor(forwarded), "192.114.52.12")

    def test_an_address_the_visitor_forged_in_front_is_ignored(self):
        forged = {"x-forwarded-for": "6.6.6.6, 192.114.52.12, 172.70.108.67, 10.30.47.157"}

        self.assertEqual(self.visitor(forged), "192.114.52.12")

    def test_headers_are_not_trusted_unless_a_proxy_is_declared(self):
        """Run directly, a visitor could name any address and dodge the limit."""
        headers = {"cf-connecting-ip": "6.6.6.6", "x-forwarded-for": "6.6.6.6, a, b"}

        self.assertEqual(self.visitor(headers, trust=False), "127.0.0.1")


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

    def test_an_oversized_body_is_refused_before_it_is_read(self):
        response = self.client.post("/api/forecast", content=b"x" * (17 * 1024),
                                    headers={"content-type": "application/json"})

        self.assertEqual(response.status_code, 413)
        self.gateway.forecast.assert_not_called()

    def test_a_body_without_an_honest_length_is_refused(self):
        for length in ("abc", "-5", "1e3", "0x10"):
            response = self.client.post("/api/forecast", content=b"{}",
                                        headers={"content-length": length})
            self.assertIn(response.status_code, (400, 411), length)

    def test_hsts_is_sent_only_when_a_proxy_terminates_https(self):
        import src.web.app as web
        previous = web.TRUST_PROXY
        try:
            web.TRUST_PROXY = False
            self.assertNotIn("strict-transport-security", self.client.get("/api/health").headers)
            web.TRUST_PROXY = True
            self.assertIn("max-age", self.client.get("/api/health").headers["strict-transport-security"])
        finally:
            web.TRUST_PROXY = previous

    def test_unknown_methods_and_paths_do_not_leak_internals(self):
        self.gateway.archived_file.return_value = self.exchange("Error: The file does not exist.")
        for method, path in (("DELETE", "/api/forecast"), ("PUT", "/api/archive"),
                             ("GET", "/api/forecast"), ("GET", "/../../etc/passwd"),
                             ("GET", "/api/archive/%00")):
            response = self.client.request(method, path, content=b"" if method != "GET" else None)
            self.assertIn(response.status_code, (400, 404, 405, 411, 422), (method, path))
            self.assertNotIn("Traceback", response.text)

    def test_the_site_is_served(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("WeatherWear", response.text)
        self.assertIn("app.js", response.text)


if __name__ == "__main__":
    unittest.main()
