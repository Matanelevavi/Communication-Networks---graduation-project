"""
Choosing where the recommendation comes from.

Two advisors, one policy: ask the AI when a key is configured, and fall back to
the local rules whenever it is missing, refused or unreachable. The caller gets
a recommendation either way and is told which one produced it, so the interface
can be honest about it rather than pretending.
"""
import logging
from dataclasses import dataclass

from src.servers.app_server.ai_advisor import AiAdvisor
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.local_advisor import LocalAdvisor
from src.servers.app_server.weather_api import Forecast

log = logging.getLogger(__name__)

AI = "ai"
LOCAL = "local"


@dataclass(frozen=True)
class Advice:
    """A recommendation and where it came from."""
    text: str
    source: str

    @property
    def is_ai(self) -> bool:
        return self.source == AI


class ClothingAdvisor:
    """Prefers the AI, guarantees an answer."""

    def __init__(self, ai: AiAdvisor | None = None,
                 local: LocalAdvisor | None = None) -> None:
        self.ai = ai if ai is not None else AiAdvisor()
        self.local = local if local is not None else LocalAdvisor()

    def recommend(self, forecast: Forecast, profiles) -> Advice:
        """Never raises for a service failure: that is what the fallback is for."""
        if self.ai.is_configured:
            try:
                return Advice(self.ai.recommend(forecast, profiles), AI)
            except ServiceError as e:
                # A bad key, an exhausted quota or an outage: say so once and
                # carry on with the local rules rather than failing the request.
                log.warning(f"AI advisor unavailable ({e}), using the local advisor")

        return Advice(self.local.recommend(forecast, profiles), LOCAL)
