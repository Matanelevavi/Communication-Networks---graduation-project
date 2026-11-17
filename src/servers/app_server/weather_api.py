"""
Open-Meteo client.

Two calls make a forecast: geocoding turns a city name into coordinates, and
the forecast endpoint returns the next 24 hours and the next week for them. A
place chosen from the suggestions already has coordinates, so it costs one.

The free API limits requests per address, and a shared host shares one address
among many apps, so calls are kept to the minimum: the archive's CSV report is
written from the hourly data already in hand, not fetched again, and after an
HTTP 429 the client stands down for a while instead of prolonging the limit.

The request asks for ``forecast_hours`` rather than a calendar day, so the 24
hours start at the current hour: a forecast fetched in the evening does not
warn about rain that fell that morning. It also asks for the city's own time
zone, so every hour on screen and in the archive is local.
"""
import logging
import time
from dataclasses import dataclass, field

import requests

from src.config import HTTP_TIMEOUT, OPEN_METEO_API_KEY
from src.servers.app_server.external_service import (ExternalService, ProviderUnavailable,
                                                     RateLimited, ServiceError)

log = logging.getLogger(__name__)

RATE_LIMITED_MESSAGE = ("The weather provider is receiving too many requests right now. "
                        "Please try again in a few minutes.")
BACKOFF_SECONDS = 60.0
MAX_BACKOFF_SECONDS = 600.0

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

RAIN_THRESHOLD = 30          # percent: below this, "rain is likely" would mislead
FORECAST_HOURS = 24
FORECAST_DAYS = 7
MAX_SUGGESTIONS = 5

CURRENT_FIELDS = ("temperature_2m,apparent_temperature,relative_humidity_2m,"
                  "weather_code,wind_speed_10m,is_day")
HOURLY_FIELDS = "temperature_2m,precipitation_probability,weather_code"
DAILY_FIELDS = ("weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,uv_index_max,wind_speed_10m_max,"
                "sunrise,sunset")

# Open-Meteo knows the big cities by their Hebrew names but not every town:
# "אריאל" finds nothing while "Ariel" does. When a Hebrew search comes back
# empty, the English name from this table is tried, and the Hebrew name the
# user typed is kept for display.
HEBREW_CITY_NAMES = {
    "אריאל": "Ariel", "תל אביב": "Tel Aviv", "תל אביב יפו": "Tel Aviv",
    "ירושלים": "Jerusalem", "חיפה": "Haifa", "באר שבע": "Beersheba",
    "אילת": "Eilat", "נתניה": "Netanya", "אשדוד": "Ashdod", "אשקלון": "Ashkelon",
    "חולון": "Holon", "בת ים": "Bat Yam", "רמת גן": "Ramat Gan",
    "גבעתיים": "Givatayim", "בני ברק": "Bnei Brak", "פתח תקווה": "Petah Tikva",
    "פתח תקוה": "Petah Tikva", "ראשון לציון": "Rishon LeZion", "רחובות": "Rehovot",
    "נס ציונה": "Ness Ziona", "לוד": "Lod", "רמלה": "Ramla", "מודיעין": "Modiin",
    "מודיעין מכבים רעות": "Modiin", "כפר סבא": "Kfar Saba", "רעננה": "Ra'anana",
    "הרצליה": "Herzliya", "הוד השרון": "Hod HaSharon", "ראש העין": "Rosh HaAyin",
    "חדרה": "Hadera", "זכרון יעקב": "Zikhron Ya'akov", "עפולה": "Afula",
    "נצרת": "Nazareth", "טבריה": "Tiberias", "צפת": "Safed", "עכו": "Acre",
    "נהריה": "Nahariya", "כרמיאל": "Karmiel", "קריית שמונה": "Kiryat Shmona",
    "יקנעם": "Yokneam", "בית שמש": "Beit Shemesh", "מעלה אדומים": "Ma'ale Adummim",
    "דימונה": "Dimona", "ערד": "Arad", "קריית גת": "Kiryat Gat", "שדרות": "Sderot",
    "אופקים": "Ofakim", "נתיבות": "Netivot", "יבנה": "Yavne", "אור יהודה": "Or Yehuda",
}


@dataclass(frozen=True)
class Place:
    """A city resolved to coordinates, and the time zone it keeps, when that is known."""
    name: str
    latitude: float
    longitude: float
    tz: str | None = None


# Bumped whenever to_dict gains a field, so an entry written by an older version
# is refetched instead of served with half the picture missing.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Forecast:
    """
    The next 24 hours and the next week for one place.

    The first five fields are what the clothing advice has always needed; the
    rest is what the page draws: how it feels, the wind, the UV index, the
    weather code for an icon, and the hour by hour and day by day series.
    Everything added later is optional, so a response that lacks it still makes
    a usable forecast.
    """
    place: Place
    min_temp: float
    max_temp: float
    current_temp: float | None
    rain_summary: str
    feels_like: float | None = None
    humidity: int | None = None
    wind_kmh: float | None = None
    weather_code: int | None = None
    is_day: bool | None = None
    uv_max: float | None = None
    sunrise: str | None = None
    sunset: str | None = None
    hourly: list = field(default_factory=list)     # [{"t", "temp", "rain", "code"}]
    daily: list = field(default_factory=list)      # [{"date", "code", "min", "max", ...}]
    provider: str = "Open-Meteo"                   # who the weather came from, to credit them

    def to_csv(self) -> bytes:
        """
        The hourly series as CSV, for the archive.

        Written from data already fetched. It used to be a second request to the
        provider for the same hours, which doubled the load on a shared address
        for a file nobody needed to be fresher than the forecast beside it.
        """
        rows = ["time,temperature_2m,precipitation_probability"]
        for hour in self.hourly:
            rain = "" if hour.get("rain") is None else hour["rain"]
            rows.append(f"{hour['t']},{hour['temp']},{rain}")
        return ("\n".join(rows) + "\n").encode("utf-8")

    @property
    def peak_wind_kmh(self) -> float:
        """The stronger of the wind now and today's strongest gust of it, in km/h."""
        today = self.daily[0].get("wind") if self.daily else None
        return max(self.wind_kmh or 0, today or 0)

    def to_dict(self) -> dict:
        """The forecast as plain data, which is what the cache stores."""
        return {
            "v": SCHEMA_VERSION,
            "city": self.place.name,
            "latitude": self.place.latitude,
            "longitude": self.place.longitude,
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "current_temp": self.current_temp,
            "rain": self.rain_summary,
            "feels_like": self.feels_like,
            "humidity": self.humidity,
            "wind_kmh": self.wind_kmh,
            "weather_code": self.weather_code,
            "is_day": self.is_day,
            "uv_max": self.uv_max,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "hourly": self.hourly,
            "daily": self.daily,
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Forecast":
        """Rebuild a forecast from :meth:`to_dict`.  Raises KeyError if incomplete or old."""
        if data["v"] != SCHEMA_VERSION:
            raise KeyError("v")
        return cls(
            place=Place(data["city"], data["latitude"], data["longitude"]),
            min_temp=data["min_temp"],
            max_temp=data["max_temp"],
            current_temp=data.get("current_temp"),
            rain_summary=data["rain"],
            feels_like=data.get("feels_like"),
            humidity=data.get("humidity"),
            wind_kmh=data.get("wind_kmh"),
            weather_code=data.get("weather_code"),
            is_day=data.get("is_day"),
            uv_max=data.get("uv_max"),
            sunrise=data.get("sunrise"),
            sunset=data.get("sunset"),
            hourly=list(data.get("hourly") or []),
            daily=list(data.get("daily") or []),
            provider=data.get("provider") or "Open-Meteo",
        )


class WeatherService(ExternalService):
    """Fetches forecasts from Open-Meteo."""

    def __init__(self, api_key: str = OPEN_METEO_API_KEY, clock=time.monotonic) -> None:
        # Optional. The free API limits requests per address, and a shared host
        # shares one address among many apps; a key lifts that for a paying user.
        self.api_key = api_key
        self.clock = clock
        # per endpoint: the forecast and the geocoder have separate quotas, and
        # being throttled on one says nothing about the other
        self._blocked_until: dict[str, float] = {}

    def fetch(self, city_name: str) -> Forecast:
        """Resolve a city and return its forecast.  Raises :class:`ServiceError`."""
        place = self._geocode(city_name)
        return self._forecast(place)

    def _geocode(self, city_name: str) -> Place:
        hebrew = not self.is_english_only(city_name)
        results = self._search(city_name, "he" if hebrew else "en")

        # A Hebrew name Open-Meteo does not know: try the English one, but
        # show the city by the name the user typed.
        english = HEBREW_CITY_NAMES.get(" ".join(city_name.replace("-", " ").split()))
        display_name = None
        if not results and hebrew and english:
            results = self._search(english, "he")
            display_name = city_name

        if not results:
            raise ServiceError(f"'{city_name}' was not found.")

        first = results[0]
        try:
            return Place(display_name or first.get("name", city_name),
                         first["latitude"], first["longitude"], first.get("timezone"))
        except (KeyError, TypeError) as e:
            raise ServiceError("The geocoding service returned "
                               "an unexpected answer.") from e

    def _search(self, name: str, language: str, count: int = 1) -> list:
        # Parameters go to requests rather than into an f-string, so a name
        # such as "Tel Aviv" is percent encoded correctly.  A Hebrew query is
        # answered with the Hebrew name, so the card shows what the user typed.
        payload = self._get(GEOCODING_URL, {
            "name": name, "count": count, "format": "json", "language": language,
        })
        return payload.get("results") or []

    # --------------------------------------------------------- place search
    def search(self, query: str) -> list[dict]:
        """
        Up to five places that match what the user has typed so far.

        "Ariel" alone names five places in four countries, so picking the first
        match silently gives some people the wrong weather. Offering the list
        lets them choose, and the choice travels as coordinates.
        """
        hebrew = not self.is_english_only(query)
        results = self._search(query, "he" if hebrew else "en", count=MAX_SUGGESTIONS)

        if not results and hebrew:
            english = HEBREW_CITY_NAMES.get(" ".join(query.replace("-", " ").split()))
            if english:
                # The name the user typed, on the one town the table points to.
                results = [{**r, "name": query} for r in self._search(english, "he", count=1)[:1]]

        return [{"name": r.get("name") or query, "admin1": r.get("admin1") or "",
                 "country": r.get("country") or "", "timezone": r.get("timezone") or "",
                 "latitude": r["latitude"], "longitude": r["longitude"]}
                for r in results if "latitude" in r and "longitude" in r][:MAX_SUGGESTIONS]

    # ------------------------------------------------------------ forecasts
    def locate(self, city_name: str) -> Place:
        """Resolve a typed name to a place. Raises :class:`ServiceError` if there is none."""
        return self._geocode(city_name)

    def forecast_for(self, place: Place) -> Forecast:
        """The forecast for a place that is already resolved."""
        return self._forecast(place)

    def fetch_at(self, name: str, latitude: float, longitude: float,
                 tz: str | None = None) -> Forecast:
        """The forecast for coordinates the user already chose or shared."""
        return self._forecast(Place(name, latitude, longitude, tz))

    def _forecast(self, place: Place) -> Forecast:
        payload = self._get(FORECAST_URL, {
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current": CURRENT_FIELDS,
            "hourly": HOURLY_FIELDS,
            "daily": DAILY_FIELDS,
            "forecast_hours": FORECAST_HOURS,
            "forecast_days": FORECAST_DAYS,
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        })

        hourly = payload.get("hourly") or {}
        times = (hourly.get("time") or [])[:FORECAST_HOURS]
        temps = [t for t in (hourly.get("temperature_2m") or [])[:FORECAST_HOURS] if t is not None]
        if not temps:
            raise ServiceError(f"No forecast is available for '{place.name}'.")

        current = payload.get("current") or {}
        legacy = payload.get("current_weather") or {}
        daily = self._daily(payload.get("daily") or {})
        today = daily[0] if daily else {}

        return Forecast(
            place=place,
            min_temp=min(temps),
            max_temp=max(temps),
            current_temp=current.get("temperature_2m", legacy.get("temperature")),
            rain_summary=self._summarise_rain(
                (hourly.get("precipitation_probability") or [])[:FORECAST_HOURS], times),
            feels_like=current.get("apparent_temperature"),
            humidity=current.get("relative_humidity_2m"),
            wind_kmh=current.get("wind_speed_10m"),
            weather_code=current.get("weather_code"),
            is_day=None if current.get("is_day") is None else bool(current["is_day"]),
            uv_max=today.get("uv"),
            sunrise=today.get("sunrise"),
            sunset=today.get("sunset"),
            hourly=self._hours(hourly, times),
            daily=daily,
        )

    @staticmethod
    def _column(source: dict, name: str, length: int) -> list:
        """One series from the response, padded so a short one cannot raise."""
        values = list(source.get(name) or [])
        return (values + [None] * length)[:length]

    @classmethod
    def _hours(cls, hourly: dict, times: list) -> list[dict]:
        n = len(times)
        temps = cls._column(hourly, "temperature_2m", n)
        rain = cls._column(hourly, "precipitation_probability", n)
        codes = cls._column(hourly, "weather_code", n)
        return [{"t": times[i], "temp": temps[i], "rain": rain[i], "code": codes[i]}
                for i in range(n)]

    @classmethod
    def _daily(cls, daily: dict) -> list[dict]:
        dates = (daily.get("time") or [])[:FORECAST_DAYS]
        n = len(dates)
        columns = {key: cls._column(daily, name, n) for key, name in (
            ("code", "weather_code"), ("max", "temperature_2m_max"),
            ("min", "temperature_2m_min"), ("rain", "precipitation_probability_max"),
            ("uv", "uv_index_max"), ("wind", "wind_speed_10m_max"),
            ("sunrise", "sunrise"), ("sunset", "sunset"))}
        return [{"date": dates[i], **{key: column[i] for key, column in columns.items()}}
                for i in range(n)]

    @staticmethod
    def _summarise_rain(probabilities, times) -> str:
        """List the hours likely to be wet, or say that none are."""
        alerts = [
            f"{times[i].split('T')[1]} ({probabilities[i]}%)"
            for i in range(min(len(probabilities), len(times)))
            if probabilities[i] is not None and probabilities[i] > RAIN_THRESHOLD
        ]
        return ", ".join(alerts) if alerts else "No rain expected"

    # --------------------------------------------------------------- shared
    def _get(self, url: str, params: dict) -> dict:
        """One GET returning JSON, with every failure turned into ServiceError."""
        # After a 429 every further request only prolongs it, and the same
        # shared address is asking on behalf of everyone: stand down for a while.
        wait = self._blocked_until.get(url, 0.0) - self.clock()
        if wait > 0:
            raise RateLimited(RATE_LIMITED_MESSAGE)

        blocked_url = url                 # the wait is remembered against the endpoint asked for
        if self.api_key:
            url = url.replace("//api.", "//customer-api.").replace("//geocoding-api.", "//customer-geocoding-api.")
            params = {**params, "apikey": self.api_key}

        try:
            response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            log.error(f"Weather service unreachable: {e}")
            raise ProviderUnavailable("Could not reach the weather service.") from e

        # Checked before the body is read: Open-Meteo answers a bad request
        # with a JSON error object, which would otherwise read as "not found".
        if not response.ok:
            reason = self._reason(response)
            log.error(f"Weather service answered HTTP {response.status_code}: {reason}")
            if response.status_code == 429:
                self._blocked_until[blocked_url] = self.clock() + self._retry_after(response)
                raise RateLimited(RATE_LIMITED_MESSAGE)
            raise ProviderUnavailable("The weather service is unavailable right now, "
                                      "please try again shortly.")

        try:
            return response.json()
        except ValueError as e:
            log.error(f"Weather service returned invalid JSON: {e}")
            raise ProviderUnavailable("The weather service returned "
                                      "an unexpected answer.") from e

    @staticmethod
    def _reason(response) -> str:
        """What the provider said was wrong, for the log: it names which limit was hit."""
        try:
            return str(response.json().get("reason", ""))[:200]
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _retry_after(response) -> float:
        """How long to stand down: what the provider asked for, within sensible bounds."""
        try:
            asked = float(response.headers.get("Retry-After", ""))
        except (TypeError, ValueError, AttributeError):
            asked = BACKOFF_SECONDS
        return min(max(asked, 10.0), MAX_BACKOFF_SECONDS)
