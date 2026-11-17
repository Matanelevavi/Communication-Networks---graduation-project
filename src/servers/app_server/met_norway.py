"""
MET Norway's Locationforecast: the fallback weather provider.

Open-Meteo is the first choice, but its free tier limits requests per address and
a free host shares one address among many apps, so there are days it answers
"Daily API request limit exceeded" to a site that has had a handful of visitors.
MET Norway needs no key, covers the world, and is a different service with its
own limits, so the site asks it when Open-Meteo cannot answer.

It is not the same data in the same shape, and this module does not pretend it
is. What differs, and what is done about it:

* times are UTC, so they are converted to the place's own time zone, which the
  geocoder or the browser supplies; with no zone the longitude gives an
  approximation rather than UTC being shown as if it were local;
* there is no chance of rain, only an amount in millimetres. It is reported as
  an amount (``mm``) and never as a percentage it is not;
* the UV index is a clear sky value, so it is reduced for cloud cover;
* there is no sunrise or sunset, and the page leaves that tile out.

The data is licensed CC BY 4.0, so every forecast it produces says where it
came from, and the request identifies this application as their terms require.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from src.config import HTTP_TIMEOUT
from src.servers.app_server.external_service import (ExternalService, ProviderUnavailable,
                                                     RateLimited, ServiceError)
from src.servers.app_server.weather_api import FORECAST_DAYS, FORECAST_HOURS, Forecast, Place

log = logging.getLogger(__name__)

URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
PROVIDER = "MET Norway"
# Their terms ask for an identifying agent with a way to reach the operator.
USER_AGENT = ("WeatherWear/2.0 "
              "(+https://github.com/Matanelevavi/Communication-Networks---graduation-project)")

MIN_RAIN_MM = 0.2          # an hour with at least this much counts as wet
KMH_PER_MS = 3.6
BACKOFF_SECONDS = 120.0

# MET's symbol names, mapped to the WMO weather codes the page already draws.
# Day and night variants share one code; the page picks the icon from the hour.
SYMBOLS = {
    "clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3, "fog": 45,
    "lightrain": 61, "rain": 63, "heavyrain": 65,
    "lightrainshowers": 80, "rainshowers": 81, "heavyrainshowers": 82,
    "lightsleet": 67, "sleet": 67, "heavysleet": 67,
    "lightsleetshowers": 67, "sleetshowers": 67, "heavysleetshowers": 67,
    "lightsnow": 71, "snow": 73, "heavysnow": 75,
    "lightsnowshowers": 85, "snowshowers": 85, "heavysnowshowers": 86,
}


def weather_code(symbol: str | None) -> int | None:
    """The WMO code for a MET symbol such as ``lightrainandthunder_night``."""
    if not symbol:
        return None
    base = symbol.rsplit("_", 1)[0] if symbol.endswith(("_day", "_night", "_polartwilight")) else symbol
    if "thunder" in base:
        return 95
    return SYMBOLS.get(base)


def uv_under_cloud(clear_sky: float | None, cloud_percent: float | None) -> float | None:
    """
    The clear sky UV index, reduced for cloud (Calbo et al., 2005).

    MET reports what the index would be under a cloudless sky, which on an
    overcast day is far too high to tell someone to wear sunscreen by.
    """
    if clear_sky is None:
        return None
    if cloud_percent is None:
        return clear_sky
    return clear_sky * (1 - 0.75 * (max(0.0, min(100.0, cloud_percent)) / 100) ** 3.4)


class MetNorway(ExternalService):
    """Fetches a forecast from MET Norway, in the same shape Open-Meteo's is read into."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._blocked_until = 0.0

    # ----------------------------------------------------------- the request
    def forecast_for(self, place: Place) -> Forecast:
        return self.parse(self._get(place), place)

    def fetch_at(self, name: str, latitude: float, longitude: float,
                 tz: str | None = None) -> Forecast:
        return self.forecast_for(Place(name, latitude, longitude, tz))

    def _get(self, place: Place) -> dict:
        if self._blocked_until - self.clock() > 0:
            raise RateLimited("The fallback weather provider is busy as well.")

        try:
            response = requests.get(
                URL, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT,
                # at most four decimals, which their terms require and a kilometre does not need
                params={"lat": f"{place.latitude:.4f}", "lon": f"{place.longitude:.4f}"})
        except requests.RequestException as e:
            log.error(f"MET Norway unreachable: {e}")
            raise ProviderUnavailable("Could not reach the fallback weather provider.") from e

        if not response.ok:
            log.error(f"MET Norway answered HTTP {response.status_code}")
            if response.status_code in (403, 429):        # throttled, or told off
                self._blocked_until = self.clock() + BACKOFF_SECONDS
                raise RateLimited("The fallback weather provider is busy as well.")
            raise ProviderUnavailable("The fallback weather provider is unavailable.")

        try:
            return response.json()
        except ValueError as e:
            raise ProviderUnavailable("The fallback weather provider returned "
                                      "an unexpected answer.") from e

    # ----------------------------------------------------------- the reading
    @staticmethod
    def _zone(place: Place):
        """The place's own clock: its zone, or failing that one hour per 15 degrees of longitude."""
        if place.tz:
            try:
                return ZoneInfo(place.tz)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                log.warning(f"Unknown time zone {place.tz!r}, approximating from longitude")
        return timezone(timedelta(hours=round(place.longitude / 15)))

    def parse(self, payload: dict, place: Place) -> Forecast:
        """Read a Locationforecast response into a :class:`Forecast`."""
        try:
            series = payload["properties"]["timeseries"]
            zone = self._zone(place)
            rows = [self._row(entry, zone) for entry in series]
        except (KeyError, TypeError, ValueError) as e:
            raise ProviderUnavailable("The fallback weather provider returned "
                                      "an unexpected answer.") from e

        hourly_rows = [row for row in rows if row["hour"] is not None][:FORECAST_HOURS]
        if len(hourly_rows) < 2:
            raise ProviderUnavailable("The fallback weather provider returned too little data.")

        first = hourly_rows[0]
        hourly = [{"t": row["local"].strftime("%Y-%m-%dT%H:%M"), "temp": row["temp"],
                   "rain": None, "mm": row["hour"]["mm"], "code": row["hour"]["code"]}
                  for row in hourly_rows]
        temps = [row["temp"] for row in hourly_rows]
        daily = self._daily(rows)

        symbol_day = (first["hour"] or {}).get("symbol") or ""
        return Forecast(
            place=Place(place.name, place.latitude, place.longitude, place.tz),
            min_temp=min(temps), max_temp=max(temps), current_temp=first["temp"],
            rain_summary=self._rain_summary(hourly_rows),
            feels_like=first["feels"],
            humidity=None if first["humidity"] is None else round(first["humidity"]),
            wind_kmh=None if first["wind"] is None else round(first["wind"] * KMH_PER_MS, 1),
            weather_code=first["hour"]["code"],
            is_day=True if symbol_day.endswith("_day") else False if symbol_day.endswith("_night") else None,
            uv_max=daily[0]["uv"] if daily else None,
            sunrise=None, sunset=None,
            hourly=hourly, daily=daily, provider=PROVIDER,
        )

    @staticmethod
    def _row(entry: dict, zone) -> dict:
        moment = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        data = entry["data"]
        details = data["instant"]["details"]
        one, six = data.get("next_1_hours"), data.get("next_6_hours")

        def block(part):
            if not part:
                return None
            symbol = (part.get("summary") or {}).get("symbol_code")
            return {"symbol": symbol, "code": weather_code(symbol),
                    "mm": (part.get("details") or {}).get("precipitation_amount") or 0.0,
                    "max": (part.get("details") or {}).get("air_temperature_max"),
                    "min": (part.get("details") or {}).get("air_temperature_min")}

        return {
            "local": moment.astimezone(zone).replace(tzinfo=None),
            "temp": details["air_temperature"],
            "feels": details.get("apparent_air_temperature"),
            "humidity": details.get("relative_humidity"),
            "wind": details.get("wind_speed"),
            "uv": uv_under_cloud(details.get("ultraviolet_index_clear_sky"),
                                 details.get("cloud_area_fraction")),
            "hour": block(one), "six": block(six),
        }

    @staticmethod
    def _rain_summary(rows: list[dict]) -> str:
        wet = [f"{row['local'].strftime('%H:%M')} ({row['hour']['mm']:g} mm)"
               for row in rows if row["hour"]["mm"] >= MIN_RAIN_MM]
        return ", ".join(wet) if wet else "No rain expected"

    @staticmethod
    def _daily(rows: list[dict]) -> list[dict]:
        """One entry per local calendar day, for as many days as were asked for."""
        by_day: dict[str, list[dict]] = {}
        for row in rows:
            by_day.setdefault(row["local"].strftime("%Y-%m-%d"), []).append(row)

        days = []
        for date, day in list(by_day.items())[:FORECAST_DAYS]:
            highs = [r["temp"] for r in day] + [r["six"]["max"] for r in day if r["six"] and r["six"]["max"] is not None]
            lows = [r["temp"] for r in day] + [r["six"]["min"] for r in day if r["six"] and r["six"]["min"] is not None]
            # rain: the hourly figure where there is one, and the six hour block where there is not
            rain = sum((r["hour"] or r["six"] or {"mm": 0.0})["mm"] for r in day)
            noon = min(day, key=lambda r: abs(r["local"].hour - 12))
            symbol = (noon["six"] or noon["hour"] or {}).get("code")
            # a day's UV comes from its daylight readings: a 2 a.m. zero is not the day's UV
            uvs = [r["uv"] for r in day if r["uv"] is not None and 9 <= r["local"].hour <= 15]
            winds = [r["wind"] for r in day if r["wind"] is not None]
            days.append({
                "date": date, "code": symbol, "max": max(highs), "min": min(lows),
                "rain": None, "mm": round(rain, 1),
                "uv": round(max(uvs), 1) if uvs else None,
                "wind": round(max(winds) * KMH_PER_MS, 1) if winds else None,
                "sunrise": None, "sunset": None,
            })
        return days
