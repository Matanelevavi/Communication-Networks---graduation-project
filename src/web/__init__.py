"""
The web front door.

A browser cannot speak RUDP, and the RUDP port must never face the internet: a
small request that triggers a large answer is exactly what a reflection attack
needs. So the website is one more *host on the simulated network*. It joins
through DHCP, resolves the application server through DNS, and then carries
each visitor's request over real TCP or real RUDP on the loopback interface,
inside the same container. Only HTTP is exposed.

    gateway.py   the host on the network, and what each request went through
    app.py       the HTTP API and the static site
    limits.py    a per visitor rate limit
    serve.py     starts every server, then the website
"""
