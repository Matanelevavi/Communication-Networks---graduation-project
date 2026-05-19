import os

#network
HOST= '127.0.0.1'#localhost
BUFF_SIZE= 1024
ENCODING= 'utf-8'
TIMEOUT= 5.0

#main dhcp
DHCP_PORT = 8067
CLIENT_PORT = 8068
DHCP_ADD = (HOST,DHCP_PORT)
CLIENT_ADD = (HOST,CLIENT_PORT)

#dhcp messages
DISCOVER_MSG = "DHCP_DISCOVER"
OFFER_MSG = "DHCP_OFFER"
REQUEST_MSG = "DHCP_REQUEST"
ACK_MSG = "DHCP_ACK"
POOL_IP = [f"192.168.1.{i}" for i in range(100, 151)]

#dns
DNS_SERVER_PORT = 8053
DNS_ADD = (HOST,DNS_SERVER_PORT)
MY_DOMAIN = "weatherwear.local"
APP_SER_IP = "127.0.0.1"

#backup dhcp
DHCP_BACKUP_PORT = 8069
DHCP_BACKUP_ADD = (HOST, DHCP_BACKUP_PORT)
BACKUP_IPS = [f"192.168.2.{i}" for i in range(100, 151)]

#app server
APP_PORT = 8080
APP_ADD = (HOST, APP_PORT)
HTTP_TIMEOUT = 10

#api config
API_KEY = "AIzaSyB-zhhBeIjMCDMbmVcmEOLm3YJhKcogtTE"
MOCK_LLM = False #set to true to avoid real API

#custom rudp
RUDP_TIMEOUT = 3.0
MAX_RETRIES = 4
SIMULATE_LOSS = True
LOSS_RATE = 0.2

#file system paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")