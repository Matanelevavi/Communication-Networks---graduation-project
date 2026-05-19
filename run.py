import subprocess
import time
import sys


def start(module_name, name):
    print(f"Starting {name}")

    #if we are on Windows open terminal for each server
    if sys.platform == "win32":
        subprocess.Popen(["python", "-m", module_name], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        #for Mac/Linux
        subprocess.Popen(["python", "-m", module_name])

if __name__ == "__main__":
    print("Starting WeatherWear Project")
    # Start all servers
    start("src.servers.dhcp_server", "DHCP Server")
    start("src.servers.dhcp_backup", "DHCP Backup")
    start("src.servers.dns_server", "DNS Server")
    start("src.servers.app_server.app", "App Server")
    print("Waiting 2 seconds until servers wake up and bind to ports")
    time.sleep(2)
    start("src.client.client", "Client GUI")
    print("All services started successfully!")