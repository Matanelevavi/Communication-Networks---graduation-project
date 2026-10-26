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
from src.lab import runner as lab
from src.web.gateway import GatewayError, NetworkGateway
from src.web.limits import RateLimiter

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
REQUESTS_PER_MINUTE = int(os.environ.get("REQUESTS_PER_MINUTE", 30))
LAB_REQUESTS_PER_MINUTE = int(os.environ.get("LAB_REQUESTS_PER_MINUTE", 60))
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
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Over HTTPS only: telling a browser to insist on HTTPS over plain HTTP, such
# as a local run, would lock the developer out of http://127.0.0.1.
HSTS = "max-age=31536000; includeSubDomains"

# A forecast request is a city and a few short names; nothing legitimate comes
# close to this, so anything larger is refused before it is read.
MAX_BODY_BYTES = 16 * 1024


class Person(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_PROFILE_FIELD)
    age_category: str = Field(default="", max_length=MAX_PROFILE_FIELD)
    notes: str = Field(default="", max_length=MAX_PROFILE_FIELD)


class ForecastRequest(BaseModel):
    city: str = Field(min_length=1, max_length=80)
    profiles: list[Person] = Field(default_factory=list, max_length=MAX_PROFILES)
    protocol: Protocol = "RUDP"


class LabRequest(BaseModel):
    """One experiment. The bounds are the lab's own, repeated here so a bad value is a 422."""
    size_kb: int = Field(default=64, ge=lab.SIZE_KB[0], le=lab.SIZE_KB[1])
    loss: float = Field(default=0.05, ge=lab.LOSS[0], le=lab.LOSS[1])
    delay_ms: int = Field(default=40, ge=lab.DELAY_MS[0], le=lab.DELAY_MS[1])
    buffer: int = Field(default=8, ge=lab.BUFFER[0], le=lab.BUFFER[1])
    seed: int = Field(default=1, ge=0, le=2**31 - 1)
    protocols: list[Protocol] = Field(default=["RUDP", "TCP"], min_length=1, max_length=2)


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
               limiter: RateLimiter | None = None,
               lab_limiter: RateLimiter | None = None) -> FastAPI:
    gateway = gateway or NetworkGateway()
    limiter = limiter or RateLimiter(REQUESTS_PER_MINUTE)
    # The lab calls no outside service and costs a few milliseconds, so it gets
    # a more generous budget of its own, which also keeps experimenting with
    # the sliders from using up the budget for real forecasts.
    lab_limiter = lab_limiter or RateLimiter(LAB_REQUESTS_PER_MINUTE)

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

        if request.method in ("POST", "PUT", "PATCH"):
            length = request.headers.get("content-length", "")
            if not length.isascii() or not length.isdigit():
                return error(411, "A Content-Length is required.")
            if int(length) > MAX_BODY_BYTES:
                return error(413, "That request is too large.")

        if path.startswith("/api/") and path not in ("/api/health",) \
                and not path.startswith(("/api/docs", "/api/openapi")):
            key = visitor(request)
            budget = lab_limiter if path == "/api/lab" else limiter
            if not budget.allow(key):
                response = error(429, "Too many requests, please wait a moment.")
                response.headers["Retry-After"] = str(budget.retry_after(key))
                return response

        response = await call_next(request)
        if not path.startswith("/api/docs"):        # the docs page loads its own assets
            for name, value in SECURITY_HEADERS.items():
                response.headers.setdefault(name, value)
        if TRUST_PROXY:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
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

    @app.post("/api/lab")
    def run_lab(body: LabRequest):
        """Run the same transfer under each protocol on a simulated link."""
        params = lab.LabParams(body.size_kb, body.loss, body.delay_ms, body.buffer, body.seed)
        return {"params": {"size_kb": params.size_kb, "loss": params.loss,
                           "delay_ms": params.delay_ms, "buffer": params.buffer,
                           "seed": params.seed},
                "runs": lab.run_lab(params, tuple(dict.fromkeys(body.protocols)))}

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
