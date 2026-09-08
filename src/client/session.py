"""
The interactive session.

Joins the network, then loops: ask the user what they want, send it, show the
answer. This is the only place where the network client and the windows meet;
neither of them knows about the other.
"""
import json
import logging
import sys

from src.client.client import NetworkClient
from src.client.gui import (ask_request, choose_archived_file, show_error,
                            show_forecast, show_text, with_progress)
from src.config import MY_DOMAIN, setup_logging

log = logging.getLogger(__name__)

NO_ANSWER = ("The server did not answer.\n\n"
             "Check that the App Server is running, then try again.")


def build_request(action: str, city: str, profiles: list) -> str:
    """Turn the user's choices into the JSON the application server expects."""
    request = {"action": action}
    if action == "FORECAST":
        request["city"] = city
        request["profiles"] = profiles
    return json.dumps(request)


def as_forecast(answer) -> dict | None:
    """
    A forecast answer is a JSON card; anything else is a plain message.

    Returning ``None`` rather than raising keeps the caller's branch simple:
    a card is laid out, everything else is shown as text.
    """
    if not isinstance(answer, str):
        return None
    try:
        card = json.loads(answer)
    except ValueError:
        return None
    return card if isinstance(card, dict) and card.get("kind") == "forecast" else None


def show_answer(action: str, answer) -> None:
    """Pick the right screen for whatever came back."""
    card = as_forecast(answer)
    if card:
        show_forecast(card)
    elif isinstance(answer, str) and answer.startswith("Error:"):
        show_error(answer)
    else:
        show_text("Result", answer)


def handle_archive(client: NetworkClient, listing: str, protocol: str) -> None:
    """Let the user pick a file from the listing, then fetch and show it."""
    filename = choose_archived_file(listing)
    if not filename:
        return

    request = json.dumps({"action": "FTP_GET", "filename": filename})
    content = with_progress(f"Fetching {filename}",
                            lambda: client.request(request, protocol))
    if content:
        show_text(filename, content, f"Downloaded over {protocol}")
    else:
        show_error(NO_ANSWER)


def run(client: NetworkClient) -> None:
    """One request per pass, until the user closes the first window."""
    while True:
        action, city, profiles, protocol = ask_request()
        if not action:
            return

        message = f"Checking the weather in {city}" if action == "FORECAST" \
            else "Loading the archive"
        answer = with_progress(
            message, lambda: client.request(build_request(action, city, profiles),
                                            protocol))

        if not answer:
            show_error(NO_ANSWER)
            continue

        if action == "FTP_LIST":
            handle_archive(client, answer, protocol)
        else:
            show_answer(action, answer)


def main() -> None:
    setup_logging("CLIENT")
    client = NetworkClient()

    if not client.connect(MY_DOMAIN):
        log.error("Could not join the network, exiting")
        show_error("Could not join the network.\n\n"
                   "Start the servers with `python run.py` and try again.")
        client.close()
        sys.exit(1)

    log.info("Starting GUI")
    try:
        run(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
