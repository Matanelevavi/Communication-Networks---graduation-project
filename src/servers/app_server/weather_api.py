"""
Open-Meteo client.

Two calls make a forecast: geocoding turns a city name into coordinates, and
the forecast endpoint returns the next 24 hours for them.  A third call fetches
the same data as CSV for the archive.

Both forecast requests ask for ``forecast_hours`` rather than a calendar day,
so the 24 hours start at the current hour: a forecast fetched in the evening
does not warn about rain that fell that morning.  Both also ask for the city's
own time zone, so the CSV in the archive and the summary on screen name the
same hours.
"""
import logging
from dataclasses import dataclass

import requests

from src.config import HTTP_TIMEOUT
from src.servers.app_server.external_service import ExternalService, ServiceError

log = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

RAIN_THRESHOLD = 30          # percent: below this, "rain is likely" would mislead
FORECAST_HOURS = 24

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
    """A city resolved to coordinates."""
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Forecast:
    """The next 24 hours for one place, reduced to what the advice needs."""
    place: Place
    min_temp: float
    max_temp: float
    current_temp: float | None
    rain_summary: str

    def to_dict(self) -> dict:
        """The forecast as plain data, which is what the cache stores."""
        return {
            "city": self.place.name,
            "latitude": self.place.latitude,
            "longitude": self.place.longitude,
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "current_temp": self.current_temp,
            "rain": self.rain_summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Forecast":
        """Rebuild a forecast from :meth:`to_dict`.  Raises KeyError if incomplete."""
        return cls(
            place=Place(data["city"], data["latitude"], data["longitude"]),
            min_temp=data["min_temp"],
            max_temp=data["max_temp"],
            current_temp=data.get("current_temp"),
            rain_summary=data["rain"],
        )


class WeatherService(ExternalService):
    """Fetches forecasts from Open-Meteo."""

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
                         first["latitude"], first["longitude"])
        except (KeyError, TypeError) as e:
            raise ServiceError("The geocoding service returned "
                               "an unexpected answer.") from e

    def _search(self, name: str, language: str) -> list:
        # Parameters go to requests rather than into an f-string, so a name
        # such as "Tel Aviv" is percent encoded correctly.  A Hebrew query is
        # answered with the Hebrew name, so the card shows what the user typed.
        payload = self._get(GEOCODING_URL, {
            "name": name, "count": 1, "format": "json", "language": language,
        })
        return payload.get("results") or []

    def _forecast(self, place: Place) -> Forecast:
        payload = self._get(FORECAST_URL, {
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current_weather": "true",
            "hourly": "temperature_2m,precipitation_probability",
            "forecast_hours": FORECAST_HOURS,
            "timezone": "auto",
        })

        hourly = payload.get("hourly", {})
        temps = [t for t in hourly.get("temperature_2m", [])[:FORECAST_HOURS] if t is not None]
        if not temps:
            raise ServiceError(f"No forecast is available for '{place.name}'.")

        return Forecast(
            place=place,
            min_temp=min(temps),
            max_temp=max(temps),
            current_temp=payload.get("current_weather", {}).get("temperature"),
            rain_summary=self._summarise_rain(
                hourly.get("precipitation_probability", [])[:FORECAST_HOURS],
                hourly.get("time", [])[:FORECAST_HOURS]),
        )

    @staticmethod
    def _summarise_rain(probabilities, times) -> str:
        """List the hours likely to be wet, or say that none are."""
        alerts = [
            f"{times[i].split('T')[1]} ({probabilities[i]}%)"
            for i in range(min(len(probabilities), len(times)))
            if probabilities[i] is not None and probabilities[i] > RAIN_THRESHOLD
        ]
        return ", ".join(alerts) if alerts else "No rain expected"

    # ------------------------------------------------------------------ csv
    def download_csv_report(self, place: Place) -> bytes | None:
        """The raw hourly data as CSV, for the archive.  ``None`` if unavailable."""
        try:
            log.info(f"Downloading CSV weather report for {place.name}")
            response = requests.get(FORECAST_URL, timeout=HTTP_TIMEOUT, params={
                "latitude": place.latitude,
                "longitude": place.longitude,
                "hourly": "temperature_2m,precipitation_probability",
                "forecast_hours": FORECAST_HOURS,
                "timezone": "auto",
                "format": "csv",
            })
        except requests.RequestException as e:
            log.error(f"HTTP download error: {e}")
            return None

        if response.status_code != 200:
            log.warning(f"Failed to download CSV, status {response.status_code}")
            return None

        log.info("CSV file downloaded successfully")
        return response.content

    # --------------------------------------------------------------- shared
    @staticmethod
    def _get(url: str, params: dict) -> dict:
        """One GET returning JSON, with every failure turned into ServiceError."""
        try:
            response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            log.error(f"Weather service unreachable: {e}")
            raise ServiceError("Could not reach the weather service.") from e

        # Checked before the body is read: Open-Meteo answers a bad request
        # with a JSON error object, which would otherwise read as "not found".
        if not response.ok:
            log.error(f"Weather service answered HTTP {response.status_code}")
            raise ServiceError("The weather service is unavailable right now, "
                               "please try again shortly.")

        try:
            return response.json()
        except ValueError as e:
            log.error(f"Weather service returned invalid JSON: {e}")
            raise ServiceError("The weather service returned "
                               "an unexpected answer.") from e
