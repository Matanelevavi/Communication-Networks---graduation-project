"""
The protocol lab: transfers you can break on purpose.

``rudp_run`` runs the project's real RUDP sender and receiver over a simulated
link, and ``tcp_model`` runs a TCP Reno sender over the same link, so the two
can be compared under identical loss, delay and receive buffer. The link keeps
its own virtual clock, which makes a run instant and repeatable.

    link.py        the virtual clock, the wire, and deterministic loss
    trace.py       what a run records, and the congestion window that records it
    rudp_run.py    the real RudpSender and RudpReceiver on the link
    tcp_model.py   Reno, written out, on the same link
    runner.py      bounded parameters and the numbers the page shows
"""
