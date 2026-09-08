# WeatherWear

A client/server system that walks through the full path a new host takes when
it joins a network: it obtains an address over **DHCP**, resolves a name
through a local **DNS** server, and then talks to an **application server**
over either standard **TCP** or **RUDP**, a reliable protocol built from
scratch on top of UDP.

The service itself is a real forecast with clothing advice written for the
people you are dressing: it reads live weather from Open-Meteo, then says
something different for a baby than for an adult, and mentions the hour rain
starts rather than that it might rain. A Gemini key upgrades the wording to an
AI written paragraph; without one the advice is generated locally from the same
numbers, so the app is fully usable with no configuration at all.

There is also a small FTP style archive of past forecasts and raw hourly
reports.

## Running it

```bash
pip install -r requirements.txt
python run.py
```

`run.py` starts every server, waits until each one has actually claimed its
port — a readiness check, not a fixed sleep — and only then starts the client.
Press `Ctrl+C` in the launcher window to stop everything.

To start a second client for a concurrency demo:

```bash
python -m src.client.client
```

## Architecture

Five independent operating system processes, all over loopback:

| Component | Port | Transport | Notes |
|---|---|---|---|
| DHCP server (primary) | 8067 | UDP | pool `192.168.1.100-150` |
| DHCP server (backup) | 8069 | UDP | pool `192.168.2.100-150`, answers 2s late |
| DNS server | 8053 | UDP | one zone: `weatherwear.local -> 127.0.0.1` |
| App server | 8080 | TCP **and** UDP | same port number, separate namespaces |
| Client | 8068 | UDP control socket | falls back to an ephemeral port if 8068 is busy |

Ports above 1024 are used deliberately: 53/67/68 need administrator rights and
collide with services the operating system already runs.

```
                        +---------------------------+
                        |          Client           |
                        |  UDP:8068 control socket  |
                        |  DhcpClient + DnsResolver |
                        |  TcpTransport|RudpTransport
                        +-------------+-------------+
                                      |
        +---------------+-------------+-------------+----------------+
        v               v                           v                v
+---------------+ +----------------+ +----------------+ +--------------------+
| DHCP primary  | | DHCP backup    | |  DNS server    | |    App server      |
| UDP:8067      | | UDP:8069       | |  UDP:8053      | | TCP:8080 UDP:8080  |
| AddressPool   | | AddressPool    | |  one zone      | | TcpListener        |
|               | | + 2s delay     | |  + TTL         | | RudpListener       |
+---------------+ +----------------+ +----------------+ +---------+----------+
                                                                  |
                                                          RequestRouter
                                          +-----------------------+------------+
                                          v                       v            v
                                   +-------------+        +-------------+ +---------+
                                   |WeatherService        |  FileAgent  | |RudpSender
                                   |AiAdvisor    |        | cache + FTP | |  window |
                                   | Open-Meteo  |        |  FileStore  | | + CRC32 |
                                   | + Gemini    |        |             | |         |
                                   +-------------+        +-------------+ +---------+
```

## Layout

Each module has one job. 39 modules, averaging 98 lines, none over 211.

```
run.py                                launcher with a port readiness check
src/config.py                         every port, timeout and protocol constant

src/rudp/                             the protocol, shared by both endpoints
  packet.py                           wire format and checksum, one definition
  congestion.py                       the congestion window, as pure arithmetic
  window.py                           state of one transfer in flight
  sender.py                           sliding window transmitter
  receive_buffer.py                   the receiver's buffer and its rwnd
  receiver.py                         reassembly and acknowledgement

src/client/
  client.py                           NetworkClient, composes the pieces below
  dhcp_client.py                      DORA with per step retries
  dns_resolver.py                     queries and a TTL aware cache
  transport.py                        Transport -> TcpTransport | RudpTransport
  session.py                          the interactive loop
  gui/theme.py                        palette and type scale, named once
  gui/base.py                         the window every screen inherits
  gui/parsing.py                      input and listings as data, no display needed
  gui/request_window.py               the dashboard
  gui/forecast_window.py              the answer, laid out as a card
  gui/file_windows.py                 the archive listing and the file viewer
  gui/busy_window.py                  shown while a request is on the wire

src/servers/
  address_pool.py                     reservations, leases and their expiry
  dhcp_server.py                      the DORA state machine over UDP
  dhcp_backup.py                      the same server, second pool, delayed
  dns_server.py                       authoritative answers with a TTL
  app_server/app.py                   runs both listeners over one router
  app_server/tcp_listener.py          TCP, and the message framing TCP lacks
  app_server/rudp_listener.py         RUDP handshakes and transfers
  app_server/router.py                request -> answer, transport agnostic
  app_server/weather_api.py           Open-Meteo client
  app_server/advisor.py               prefers the AI, guarantees an answer
  app_server/ai_advisor.py            Gemini client, optional
  app_server/local_advisor.py         advice from the forecast, no key needed
  app_server/external_service.py      shared validation and error type
  app_server/agent.py                 FileAgent: the cache and the archive
  app_server/forecast_cache.py        one forecast per city per day
  app_server/file_archive.py          list, read, render a CSV as a table
  app_server/storage.py               guarded access to the data directory

tests/                                265 unit tests, one file per module
```

Three design decisions are worth pointing at:

* **`src/rudp/` sits beside the client and the servers, not inside either.**
  Both ends of a transfer depend on the wire format, so it has exactly one
  definition. Previously each side built and parsed the header by hand.
* **`Transport` is an abstract base with two implementations.** Nothing above
  it branches on TCP versus RUDP; the difference between the two *is* the
  project, and it lives in one file.
* **The router never learns how a request arrived.** Both listeners hand it a
  dictionary and send back whatever it returns.

## Configuration

Everything tunable lives in [`src/config.py`](src/config.py). The values that
matter during a demo can also be set through the environment, so nothing has to
be edited mid-presentation:

| Variable | Effect |
|---|---|
| `GEMINI_API_KEY` | Optional. Upgrades the advice to an AI written paragraph |
| `SIMULATE_LOSS=1` | Drop packets at random (`LOSS_RATE`, default 0.2) |
| `SIMULATE_DELAY=1` | Delay one packet (`DELAY_SEQ`, `DELAY_SECONDS`) to force a retransmit |
| `RUDP_RECV_BUFFER=2` | Shrink the receive buffer to watch flow control throttle the sender |

```bash
SIMULATE_LOSS=1 python run.py          # watch retransmission and the window collapse
RUDP_RECV_BUFFER=2 python run.py       # watch the receiver throttle the sender
```

On Windows PowerShell: `$env:SIMULATE_LOSS=1; python run.py`

### The Gemini key is optional

Copy `.env.example` to `.env` and put a key in it if you want AI written
advice. `.env` is git ignored, and a key should never be committed: Google
scans public code for its own keys and revokes the ones it finds, so a
hardcoded key stops working on its own.

Without a key the app is not degraded into a placeholder. `LocalAdvisor`
writes the recommendation from the same live numbers, and the interface says
which advisor produced the text.

## The RUDP protocol

Data packet, and the acknowledgement that answers it:

```
SEQ:<n>|TOTAL:<t>|CHK:<crc32>|<up to 800 payload bytes>
ACK:<n>|WIN:<rwnd>
```

The CRC32 covers `SEQ:<n>|TOTAL:<t>|` **and** the payload, so a bit flip in a
header field is detected too, not only a bit flip in the data.

| Mechanism | Behaviour |
|---|---|
| Reliability | per packet sequence numbers, CRC32, retransmission on timeout |
| Congestion control | slow start (`cwnd += 1` per ACK) until `ssthresh`, then congestion avoidance (`cwnd += 1/cwnd`) |
| Loss recovery | a timeout halves `ssthresh` and restarts at `cwnd = 1`; three duplicate ACKs trigger a Fast Retransmit and halve the window |
| Flow control | the receiver advertises its free buffer space as `rwnd` in every ACK; the sender is limited by `min(cwnd, rwnd)` |
| Connection setup | `SEQ:1` / `ACK:1`, retried up to `MAX_RETRIES` times |
| Teardown | `FIN` / `FIN-ACK` |

Congestion control and flow control answer two different questions, and the
smaller answer wins: *what can the network carry* versus *what can the receiver
hold*. The receiver hands in-order bytes on immediately and only buffers chunks
that arrive early, so `rwnd` is the space left for those gaps. One packet is
always allowed through, so a zero window is probed rather than deadlocked.

The server answers from a fresh ephemeral socket rather than the well known
port, so the data acknowledgements never race with new incoming requests.

## DHCP

DORA over unicast, with two mechanisms that keep the pool honest:

* an offered address is **reserved**, not leased, and returns to the pool after
  `OFFER_HOLD_TIME` if the REQUEST never arrives;
* a granted address is leased for `LEASE_TIME` and returns to the pool when the
  lease expires, even without a RELEASE.

The REQUEST carries the port of the server whose offer was accepted and goes to
both servers — the role the *server identifier* option plays in RFC 2131. The
server that was not chosen frees its reservation immediately instead of holding
an address nobody will claim.

## Tests

```bash
python -m unittest discover -s tests -t .
```

265 unit tests covering the DHCP lease state machine, DNS answers, RUDP framing,
congestion control and flow control, TCP message framing, storage, the advisor
fallback and the external API clients. They use mocked sockets, so no server has
to be running and nothing touches the network.

## How a forecast is produced

```
FORECAST request
      |
      v
  daily cache ---- hit ----> the stored card, marked cached
      |
     miss
      v
  Open-Meteo: geocode the city, then 24 hours of temperature and rain
      |
      v
  ClothingAdvisor
      |-- a key is set?  -> Gemini writes the paragraph        (source: ai)
      |-- no key, or the call fails -> LocalAdvisor writes it  (source: local)
      v
  store the card and the raw CSV, answer with the card
```

The answer is a JSON object rather than prose, so the client lays the numbers
out itself instead of parsing sentences:

```json
{
  "kind": "forecast", "city": "Ariel",
  "min_temp": 19.9, "max_temp": 33.3, "current_temp": 22.6,
  "rain": "No rain expected",
  "advice": "Ariel is hot today, 19.9° to 33.3°, so go with ...",
  "source": "local", "cached": false
}
```
