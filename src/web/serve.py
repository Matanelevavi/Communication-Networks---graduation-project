"""
Starts the whole system behind one HTTP port.

The four servers run as their own processes, exactly as they do under
``run.py``, and only once every one of them has claimed its port does the
website start and join the network. Stopping this process stops them all.

    python -m src.web.serve                 # http://127.0.0.1:8000
    PORT=10000 BIND=0.0.0.0 python -m src.web.serve
"""
import logging
import os
import signal
import subprocess
import sys

import uvicorn

from run import SERVERS, wait_for_servers
from src.config import BASE_DIR, setup_logging
from src.web.app import create_app

log = logging.getLogger(__name__)


def start_servers() -> list[subprocess.Popen]:
    return [subprocess.Popen([sys.executable, "-m", module], cwd=BASE_DIR)
            for module, _name, _port, _kind in SERVERS]


def stop(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> None:
    setup_logging("WEB")
    processes = start_servers()
    # A container is stopped with SIGTERM; turning it into the same exit path
    # as Ctrl+C means no server outlives the website.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        if not wait_for_servers([(name, port, kind) for _m, name, port, kind in SERVERS]):
            log.error("Not every server started; the site will report it")
        uvicorn.run(create_app(),
                    host=os.environ.get("BIND", "127.0.0.1"),
                    port=int(os.environ.get("PORT", 8000)),
                    proxy_headers=False, server_header=False, log_level="info")
    finally:
        stop(processes)


if __name__ == "__main__":
    main()
