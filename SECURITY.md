# Security

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository. I will acknowledge a
report within a few days and say what I can reproduce.

## What is in scope

The deployed website, the HTTP API behind it, and the code in this repository.
The network servers (DHCP, DNS, the application server) are *not* reachable from
the internet in the deployment: they listen on loopback inside the container,
and only the HTTP port is published. They are in scope as code, because a
request that reaches the website reaches them.

## Threat model

**What is worth protecting**

| Asset | Why |
|---|---|
| The Gemini API key | It costs money and can be revoked if abused |
| The availability of the site and of its upstream quotas | Open-Meteo and Gemini are rate limited |
| The family description a visitor types | Names and notes about children |
| The host: file system, processes, memory | The usual |

**Trust boundaries.** Everything from the browser is hostile. Everything the
website sends onward over TCP or RUDP is still treated as hostile by the servers
behind it, because they are also run directly in the desktop client.

### Threats and what answers them

| # | Threat | Mitigation | Where |
|---|---|---|---|
| 1 | One visitor spends the whole upstream quota | 30 requests a minute per visitor, keyed on the address Cloudflare reports, not on a header a client can write | `src/web/limits.py`, `visitor()` in `src/web/app.py` |
| 2 | A forged `X-Forwarded-For` to dodge that limit | The key is `CF-Connecting-IP`, which Cloudflare overwrites; headers are trusted only when `TRUST_PROXY` says a proxy really is in front | `src/web/app.py`, tested |
| 3 | A huge or malformed request body | Fields are validated and bounded before anything leaves the website; bodies over 16 KB are refused unread; a missing or odd `Content-Length` is refused | `src/web/app.py` |
| 4 | Injection through the family description into the AI prompt | Unknown fields are dropped, values are cut to 40 characters and one line, at most 10 people; the text is sent as marked data after the instructions | `clean_profiles`, `AiAdvisor.build_prompt` |
| 5 | Cross site scripting | Every value is put on the page with `textContent`, never `innerHTML`; a CSP forbids inline script and foreign origins; `frame-ancestors 'none'` | `src/web/static/app.js`, `SECURITY_HEADERS` |
| 6 | Path traversal through the archive | Both separators are split on every platform, `..`, drive and stream names and control characters are refused, and the resolved path must still sit inside the data directory | `FileStore.resolve`, fuzzed |
| 7 | One family's advice shown to the next visitor | Only the weather is cached or archived; advice is written per request and never stored | `ForecastCache`, `RequestRouter` |
| 8 | A malformed datagram stopping the DHCP server | Every message is handled inside a guard, and the parsers accept ASCII digits only | `DHCPServer._handle_safely`, fuzzed |
| 9 | Forged or non-canonical RUDP packets | A packet is accepted only if its bytes are exactly what the encoder would produce; every number is bounded; the CRC covers the header | `src/rudp/packet.py`, fuzzed |
| 10 | Memory growth from hostile sequence numbers | The receive buffer holds at most `RUDP_RECV_BUFFER` out of order chunks, whatever numbers arrive | `ReceiveBuffer`, fuzzed |
| 11 | Thread exhaustion: many connections, or one that trickles | 64 TCP connections at once (more are refused, not queued), 32 RUDP transfers overall, and a 10 second deadline for a whole request | `TcpListener`, `RudpListener` |
| 12 | Reflection and amplification through RUDP | The RUDP port is never published. The website is a host on the simulated network and speaks RUDP only over loopback | architecture |
| 13 | Internal details in error messages | Failures the user should see are written for them; anything else is logged and answered with a generic line; no stack traces over HTTP | tested |
| 14 | A secret committed to the repository | The key is read from the environment only; gitleaks runs on every push over the whole history; the history was rewritten after a key leaked early on | `.github/workflows/secrets.yml` |
| 15 | A vulnerable dependency | `pip-audit` on every push and weekly, Dependabot, and Trivy on the built image | `.github/workflows/security.yml` |
| 16 | The container running as root | It runs as an unprivileged user (uid 10001) | `Dockerfile` |

### What fuzzing found

The fuzz suite (`tests/test_fuzz.py`, Hypothesis) throws arbitrary bytes at every
parser that faces the network. It found three real bugs, all fixed and each now
covered by a named regression test:

1. **A single datagram stopped the DHCP server.** `"²".isdigit()` is true and
   `int("²")` raises; nothing caught it in the main loop.
2. **The packet parser accepted datagrams nobody sent.** It read the numbers with
   `int()`, which accepts padding, signs and non ASCII digits, and did not check
   the field names, so `REQ:2` parsed as `SEQ:2`. Now only the canonical encoding
   is accepted.
3. **A file name could raise instead of being refused**, and the exception text
   would have reached the client.

Static analysis (Bandit) reports nothing; its seven low severity notes are marked
`# nosec` in the code, each with the reason it is safe (simulation randomness,
subprocesses started from fixed module names).

## Known limitations

These are real and deliberate, for a project of this size:

* **The rate limit lives in memory, per instance.** It resets on restart and would
  not be shared between several instances. A shared store such as Redis would fix
  that; it is not needed for one container.
* **The archive is readable by every visitor.** It holds only city weather, which
  is public data, but it does show which cities people asked about.
* **With a Gemini key set, the family description is sent to Google** to write the
  advice. Without a key it never leaves the server. The page says where it is kept
  (on your device) but not this; a privacy note is on the list.
* **There are no accounts.** Nothing is personal enough to need them, and the cost
  is that abuse is limited by address only.
* **Traffic between the website and the servers is plain**, over loopback inside one
  container. That is a boundary the container provides, not one the code enforces.
* **The first request after the free tier sleeps takes about a minute.** That is
  the hosting plan, not the code.

## Running the checks yourself

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .        # includes the fuzz suite
bandit -r src run.py -ll -ii
pip-audit -r requirements.txt
```
