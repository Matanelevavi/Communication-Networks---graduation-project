"""
The interactive session.

Joins the network, then loops: ask the user what they want, send it, show the
answer.  This is the only place where the network client and the windows meet;
neither of them knows about the other.
"""
import json
import logging
import sys

from src.client.client import NetworkClient
from src.client.gui import show_ftp_list_gui, show_result_gui, get_user_data_gui
from src.config import MY_DOMAIN, setup_logging

log = logging.getLogger(__name__)

NO_ANSWER = ("The server did not answer.\n"
             "Check that the App Server is running and try again.")


def build_request(action: str, city: str, profiles: list) -> str:
    """Turn the user's choices into the JSON the application server expects."""
    request = {"action": action}
    if action == "FORECAST":
        request["city"] = city
        request["profiles"] = profiles
    return json.dumps(request)


def handle_archive(client: NetworkClient, listing: str, protocol: str) -> None:
    """Let the user pick a file from the archive listing, then fetch and show it."""
    filename = show_ftp_list_gui(listing)
    if not filename:
        return

    request = json.dumps({"action": "FTP_GET", "filename": filename})
    content = client.request(request, protocol)
    if content:
        show_result_gui("FTP_GET", filename, content)


def run(client: NetworkClient) -> None:
    """One request per pass, until the user closes the first window."""
    while True:
        action, city, profiles, protocol = get_user_data_gui()
        if not action:
            return

        answer = client.request(build_request(action, city, profiles), protocol)
        if not answer:
            show_result_gui("ERROR", city, NO_ANSWER)
            continue

        if action == "FTP_LIST":
            handle_archive(client, answer, protocol)
        else:
            show_result_gui(action, city, answer)


def main() -> None:
    setup_logging("CLIENT")
    client = NetworkClient()

    if not client.connect(MY_DOMAIN):
        log.error("Could not join the network, exiting")
        client.close()
        sys.exit(1)

    log.info("Starting GUI")
    try:
        run(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
