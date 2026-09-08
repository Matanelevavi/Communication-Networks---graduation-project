"""
Launcher.

Starts each server as its own operating system process, exactly as five
separate machines would run on a real network, and only starts the client once
every server has actually claimed its port.
"""
import socket
import subprocess
import sys
import time

from src.config import (
    HOST,
    DHCP_PORT,
    DHCP_BACKUP_PORT,
    DNS_SERVER_PORT,
    APP_PORT,
    BASE_DIR,
)

SERVERS = [
    ("src.servers.dhcp_server", "DHCP Server", DHCP_PORT, socket.SOCK_DGRAM),
    ("src.servers.dhcp_backup", "DHCP Backup", DHCP_BACKUP_PORT, socket.SOCK_DGRAM),
    ("src.servers.dns_server", "DNS Server", DNS_SERVER_PORT, socket.SOCK_DGRAM),
    ("src.servers.app_server.app", "App Server", APP_PORT, socket.SOCK_STREAM),
]

STARTUP_TIMEOUT = 15.0


def start(module_name, name):
    """Launch one module as a subprocess, in its own console on Windows."""
    print(f"Starting {name}")
    # sys.executable is the interpreter running this script, so the servers
    # inherit the same virtual environment instead of whichever "python"
    # happens to be first on PATH.
    cmd = [sys.executable, "-m", module_name]
    if sys.platform == "win32":
        return subprocess.Popen(cmd, cwd=BASE_DIR,
                                creationflags=subprocess.CREATE_NEW_CONSOLE)
    return subprocess.Popen(cmd, cwd=BASE_DIR)


def port_is_taken(port, kind):
    """True once some process holds the port, i.e. the server is listening."""
    probe = socket.socket(socket.AF_INET, kind)
    try:
        probe.bind((HOST, port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def wait_for_servers(pending, timeout=STARTUP_TIMEOUT):
    """
    Block until every server has bound its port.

    A readiness check replaces a fixed sleep, so a slow machine does not start
    the client before the servers are able to answer it.
    """
    deadline = time.time() + timeout
    remaining = list(pending)

    while remaining and time.time() < deadline:
        remaining = [(name, port, kind) for name, port, kind in remaining
                     if not port_is_taken(port, kind)]
        if remaining:
            time.sleep(0.1)

    for name, port, _kind in remaining:
        print(f"WARNING: {name} did not claim port {port} within {timeout:.0f}s")
    return not remaining


if __name__ == "__main__":
    print("Starting WeatherWear Project")
    processes = []

    try:
        for module_name, name, port, kind in SERVERS:
            processes.append(start(module_name, name))

        print("Waiting for the servers to bind their ports")
        if wait_for_servers([(name, port, kind) for _m, name, port, kind in SERVERS]):
            print("All servers are listening")

        processes.append(start("src.client.client", "Client GUI"))
        print("All services started successfully!")
        print(f"Start another client with: {sys.executable} -m src.client.client")
        print("Press Ctrl+C here to stop every process.")

        # Stay alive so that Ctrl+C tears the whole system down and no server
        # is left orphaned behind a console window.
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping WeatherWear")
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
