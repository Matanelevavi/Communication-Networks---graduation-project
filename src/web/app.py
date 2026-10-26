"""
The HTTP API and the static site.

Every endpoint is a thin translation: validate the visitor's input, hand it to
the gateway, which carries it over TCP or RUDP to the application server, and
turn the answer into JSON along with what the transfer went through.

Endpoints are plain ``def`` functions, so FastAPI runs each one on its thread
pool: the socket calls inside block, and they must not block the event loop.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import MAX_PROFILE_FIELD, MAX_PROFILES
from src.web.gateway import GatewayError, NetworkGateway
from src.web.limits import RateLimiter

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
REQUESTS_PER_MINUTE = int(os.environ.get("REQUESTS_PER_MINUTE", 30))
# On Render the request passes Cloudflare and then Render's own proxy, so the
# peer address is always 127.0.0.1 and X-Forwarded-For reads
#     <visitor>, <cloudflare edge>, <render proxy>
# where the last two change from one request to the next: keying on either
# made every request look like a new visitor and the limit never fired.
# Cloudflare sets CF-Connecting-IP itself and overwrites a forged one, so that
# is the trusted source; the third entry from the end is the fallback. Neither
# is trusted unless TRUST_PROXY says the app really sits behind such a proxy.
TRUST_PROXY = os.environ.get("TRUST_PROXY", "").lower() in ("1", "true", "yes")

Protocol = Literal["RUDP", "TCP"]

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; "
                                "style-src 'self' https://fonts.googleapis.com; "
                                "font-src https://fonts.gstatic.com; "
                                "connect-src 'self'; frame-ancestors 'none'; "
                                "base-uri 'none'; form-action 'self'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_PROFILE_FIELD)
    age_category: str = Field(default="", max_length=MAX_PROFILE_FIELD)
    notes: str = Field(default="", max_length=MAX_PROFILE_FIELD)


class ForecastRequest(BaseModel):
    city: str = Field(min_length=1, max_length=80)
    profiles: list[Person] = Field(default_factory=list, max_length=MAX_PROFILES)
    protocol: Protocol = "RUDP"


def error(status: int, message: str, transfer: dict | None = None) -> JSONResponse:
    body = {"error": message}
    if transfer:
        body["transfer"] = transfer
    return JSONResponse(body, status_code=status)


def visitor(request: Request) -> str:
    if TRUST_PROXY:
        for header in ("cf-connecting-ip", "true-client-ip"):
            address = request.headers.get(header, "").strip()
            if address:
                return address
        hops = [hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",")]
        if len(hops) >= 3 and hops[-3]:
            return hops[-3]
    return request.client.host if request.client else "unknown"


def create_app(gateway: NetworkGateway | None = None,
               limiter: RateLimiter | None = None) -> FastAPI:
    gateway = gateway or NetworkGateway()
    limiter = limiter or RateLimiter(REQUESTS_PER_MINUTE)

    @asynccontextmanager
    async def lifespan(_app):
        # Joining at start up means the first visitor does not pay for DORA;
        # if it fails here, the first request tries again.
        gateway.join()
        yield
        gateway.leave()

    app = FastAPI(title="WeatherWear", version="2.0",
                  docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json", lifespan=lifespan)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in ("/api/health",) \
                and not path.startswith(("/api/docs", "/api/openapi")):
            key = visitor(request)
            if not limiter.allow(key):
                response = error(429, "Too many requests, please wait a moment.")
                response.headers["Retry-After"] = str(limiter.retry_after(key))
                return response

        response = await call_next(request)
        if not path.startswith("/api/docs"):        # the docs page loads its own assets
            for name, value in SECURITY_HEADERS.items():
                response.headers.setdefault(name, value)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # ------------------------------------------------------------ the api
    @app.get("/api/health")
    def health():
        return {"ok": True, "network": gateway.status}

    @app.post("/api/forecast")
    def forecast(body: ForecastRequest):
        profiles = [person.model_dump() for person in body.profiles]
        try:
            card, exchange = gateway.forecast(body.city.strip(), profiles, body.protocol)
        except GatewayError as e:
            log.error(f"Forecast failed on the network: {e}")
            return error(503, "The service is not reachable right now.")

        if card is None:
            return error(422, exchange.error_message or "Unexpected answer from the server.",
                         exchange.transfer())
        return {"forecast": card, "transfer": exchange.transfer()}

    @app.get("/api/archive")
    def archive(protocol: Protocol = "RUDP"):
        try:
            files, exchange = gateway.archive(protocol)
        except GatewayError:
            return error(503, "The service is not reachable right now.")
        if exchange.is_error:
            return error(502, exchange.error_message, exchange.transfer())
        return {"files": files, "transfer": exchange.transfer()}

    @app.get("/api/archive/{filename}")
    def archived_file(filename: str, protocol: Protocol = "RUDP"):
        if len(filename) > 120:
            return error(422, "That file name is too long.")
        try:
            exchange = gateway.archived_file(filename, protocol)
        except GatewayError:
            return error(503, "The service is not reachable right now.")
        if exchange.is_error:
            return error(404, exchange.error_message, exchange.transfer())
        if not isinstance(exchange.answer, str):
            return error(415, "This file is binary and cannot be shown as text.",
                         exchange.transfer())
        return {"name": filename, "content": exchange.answer,
                "transfer": exchange.transfer()}

    # ----------------------------------------------------------- the site
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site")
    return app
