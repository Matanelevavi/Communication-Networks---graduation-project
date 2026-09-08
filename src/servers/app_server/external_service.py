"""
Shared ground for the clients that reach outside the project.

Both the weather service and the AI advisor talk HTTP to somebody else's
server, so both share the same two concerns: the input has to be English,
because that is all the remote services accept, and a failure has to reach the
user as a sentence rather than as a stack trace.
"""
import re

# The remote services are queried in English and prompted in English, so
# Hebrew input would break them rather than return a wrong answer.
HEBREW_LETTERS = re.compile(r'[\u0590-\u05FF]')


class ServiceError(Exception):
    """
    A failure the user should be shown, phrased for them.

    Raising instead of returning an error string means the caller cannot
    accidentally treat a failure as a result, which is what used to let an API
    error get written into the daily forecast cache.
    """


class ExternalService:
    """Base for an HTTP client that depends on a service outside the project."""

    @staticmethod
    def is_english_only(text) -> bool:
        """False when the text contains Hebrew letters."""
        return not bool(HEBREW_LETTERS.search(str(text)))

    @classmethod
    def require_english(cls, text, subject: str) -> None:
        """Reject Hebrew input before it reaches the network."""
        if not cls.is_english_only(text):
            raise ServiceError(f"Input Error: {subject} must be in English.")
