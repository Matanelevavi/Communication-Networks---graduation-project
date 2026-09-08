"""One conversion both listeners need: an answer, as bytes for the wire."""
from src.config import ENCODING

NO_RESPONSE = b"Error: the server produced no response."


def as_bytes(answer) -> bytes:
    """Answers may be text or a raw file; a socket only carries bytes."""
    if answer is None:
        return NO_RESPONSE
    return answer.encode(ENCODING) if isinstance(answer, str) else answer
