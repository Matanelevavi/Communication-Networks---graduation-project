"""
Gemini client.

Turns a forecast and a family description into one paragraph of clothing
advice. Optional by design: without a key it reports itself as unconfigured and
:class:`~src.servers.app_server.advisor.ClothingAdvisor` falls back to the local
rules. Anything that goes wrong is raised, never returned, so a caller can never
mistake an outage for a recommendation and store it in the cache.
"""
import logging

import requests

from src.config import API_KEY, HTTP_TIMEOUT
from src.servers.app_server.external_service import ExternalService, ServiceError
from src.servers.app_server.weather_api import Forecast

log = logging.getLogger(__name__)

GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/"
              "models/gemini-2.5-flash:generateContent")


class AiAdvisor(ExternalService):
    """Asks Gemini what to wear, when a key is available."""

    def __init__(self, api_key: str = API_KEY) -> None:
        self.api_key = api_key

    @property
    def is_configured(self) -> bool:
        """False when no key is set, which is a normal state and not an error."""
        return bool(self.api_key)

    def recommend(self, forecast: Forecast, profiles) -> str:
        """One paragraph of advice.  Raises :class:`ServiceError` on failure."""
        if not self.is_configured:
            raise ServiceError("AI Error: no GEMINI_API_KEY is configured.")

        self.require_english(profiles, "the family profiles")
        return self._ask(self.build_prompt(forecast, profiles))

    @staticmethod
    def build_prompt(forecast: Forecast, profiles) -> str:
        return (f"Today in {forecast.place.name}: "
                f"{forecast.min_temp}C to {forecast.max_temp}C. "
                f"Rain: {forecast.rain_summary} "
                f"Family info: {profiles} "
                f"Task: Write a short and friendly paragraph in English with "
                f"clothing advice focus on the weather, no lists")

    def _ask(self, prompt: str) -> str:
        try:
            # The key travels in a header rather than the query string, so it
            # stays out of proxy logs and out of a packet capture of the URL.
            payload = requests.post(
                GEMINI_URL,
                headers={"x-goog-api-key": self.api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=HTTP_TIMEOUT,
            ).json()
        except requests.RequestException as e:
            log.error(f"AI service unreachable: {e}")
            raise ServiceError("Recommendation Error: Could not connect "
                               "to AI advisor.") from e
        except ValueError as e:
            log.error(f"AI service returned invalid JSON: {e}")
            raise ServiceError("Recommendation Error: the AI returned "
                               "an unexpected answer.") from e

        return self._read_answer(payload)

    @staticmethod
    def _read_answer(payload: dict) -> str:
        candidates = payload.get("candidates")
        if not candidates:
            message = payload.get("error", {}).get("message", "AI Service Error")
            log.warning(f"Gemini returned no candidate: {message}")
            raise ServiceError(f"AI Error: {message}")

        try:
            return candidates[0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            log.error(f"Unexpected AI payload shape: {e}")
            raise ServiceError("Recommendation Error: the AI returned "
                               "an unexpected answer.") from e
