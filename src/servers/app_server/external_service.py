"""
Shared ground for the clients that reach outside the project.

Both the weather service and the AI advisor talk HTTP to somebody else's
server, so both share the same two concerns: knowing which language the user
wrote in, so the answer can come back in it, and making sure a failure reaches
the user as a sentence rather than as a stack trace.
"""
import re

HEBREW_LETTERS = re.compile(r'[֐-׿]')


class ServiceError(Exception):
    """
    A failure the user should be shown, phrased for them.

    Raising instead of returning an error string means the caller cannot
    accidentally treat a failure as a result, which is what used to let an API
    error get written into the forecast cache.
    """


class ExternalService:
    """Base for an HTTP client that depends on a service outside the project."""

    @staticmethod
    def is_english_only(text) -> bool:
        """False when the text contains Hebrew letters."""
        return not bool(HEBREW_LETTERS.search(str(text)))
