"""Failed-attempt counter, shared by every gunicorn worker: one sqlite file on tmpfs.

The container runs ~30 workers in separate address spaces, so a module-level dict would be thirty
independent counters and thirty times the intended ceiling. `/dev/shm` is tmpfs — RAM, shared by
every process in the container, empty again after a redeploy, which is exactly the lifetime a
brute-force counter wants. sqlite gives the cross-process locking, the expiry and the unbounded key
space for a fraction of the code a hand-packed mmap table would need.

# ponytail: per container. Scale the service to two replicas and each gets its own counter, so the
# effective limit doubles; move the keys to Redis if that day comes.
"""
import ipaddress
import sqlite3
import time

from flask import current_app, request

# The headers a proxy uses to pass the visitor along, best first. CF-Connecting-IP is Cloudflare's and
# carries no chain; X-Forwarded-For is a list and is read from the right (below); X-Real-IP is what a
# plain reverse proxy sets. Only consulted when the connection came from a network in TRUSTED_PROXIES.
FORWARDED = ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP")


def _from_proxy(peer):
    """True when this connection came from a proxy we put there ourselves, so its forwarding headers
    are ours and not the visitor's."""
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    addr = getattr(addr, "ipv4_mapped", None) or addr   # ::ffff:10.0.1.7 is 10.0.1.7
    return any(addr in net for net in current_app.config["TRUSTED_PROXIES"])


def client_ip():
    """The visitor, not the hop in front of them. There are two ways into this app and each needs a
    different answer: through the Cloudflare tunnel the address is in CF-Connecting-IP, which the edge
    sets and which it strips off anything the client sent, and on the LAN port the connection is the
    visitor already, so remote_addr is the whole truth.

    Which is why nothing is believed until the peer is one of ours. A forwarding header is a claim by
    whoever opened the connection; it is only evidence when that was a proxy we deployed. Take it from
    anybody and a LAN client can set CF-Connecting-IP by hand, rotate it past LOGIN_MAX_FAILURES for
    unlimited password guesses, and write whatever they like into the audit log's From column.

    X-Forwarded-For is read from the RIGHT. A proxy appends the peer it saw, so with one trusted hop
    the last entry is the real connection and everything before it is client-supplied.

    # ponytail: one hop. Two trusted proxies in a row and the rightmost entry is the inner one, not the
    # visitor -- count back as many entries as there are hops if that day comes. And the default ranges
    # are all of RFC1918, so a LAN client is inside them and its own headers are believed: name the one
    # subnet the proxy sits on in TRUSTED_PROXIES to close that, no code change."""
    peer = request.remote_addr or ""
    if _from_proxy(peer):
        for h in FORWARDED:
            if fwd := request.headers.get(h, "").rsplit(",", 1)[-1].strip():
                return fwd
    # never None: the key is an f-string, and None would share one bucket named "None"
    return peer or "-"


def connection():
    """What this request looks like from inside, for the panel on the Activity screen.

    There are two ways into this app and they produce an address from different places, so "is the log
    recording real visitors" was a question nobody could answer without a deploy and a guess. This
    answers it: what the log will store, who actually opened the connection, whether that peer is one
    of ours, and what -- if anything -- the connection claimed on the way in. It lives here because
    every one of those facts is this module's, and the screen should not have to know how they are
    worked out."""
    peer = request.remote_addr or ""
    return {"seen": client_ip(), "peer": peer, "trusted": _from_proxy(peer),
            "headers": {h: request.headers[h] for h in FORWARDED if h in request.headers}}


def _db():
    # CREATE IF NOT EXISTS on every connect is not defensiveness: /dev/shm is empty in a fresh
    # container, so the file has to build itself the first time anyone fails a login.
    db = sqlite3.connect(current_app.config["THROTTLE_DB"], timeout=2)
    db.execute("PRAGMA busy_timeout=2000")
    db.execute("CREATE TABLE IF NOT EXISTS failures (k TEXT NOT NULL, at REAL NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS ix_failures ON failures (k, at)")
    return db


def _off():
    """Tests share one file across runs and post to the login route several times in a row; a limit
    that leaked into them would fail the suite for reasons that are nothing to do with the test."""
    return current_app.config.get("TESTING")


def retry_after(key, limit=None, window=None):
    """Seconds this key must wait, or 0 if it may try now.

    Fails OPEN. A counter that cannot open its file must not be able to lock the owner out of their
    own site, so every error here allows the attempt through."""
    if _off():
        return 0
    limit = current_app.config["LOGIN_MAX_FAILURES"] if limit is None else limit
    window = current_app.config["LOGIN_WINDOW"] if window is None else window
    cutoff = time.time() - window
    try:
        with _db() as db:
            db.execute("DELETE FROM failures WHERE at < ?", (cutoff,))
            n, oldest = db.execute("SELECT count(*), min(at) FROM failures WHERE k = ? AND at >= ?",
                                   (key, cutoff)).fetchone()
    except sqlite3.Error:
        return 0
    return max(1, int(oldest + window - time.time())) if n >= limit else 0


def record_failure(key, limit=None, window=None):
    """Records one failure. Returns True only for the attempt that *crossed* the limit, so a caller
    can log the lockout once. Logging it from retry_after() instead would write a row on every
    blocked attempt for the whole window -- which hands anyone hammering a locked login the ability
    to fill the audit log at will."""
    if _off():
        return False
    limit = current_app.config["LOGIN_MAX_FAILURES"] if limit is None else limit
    window = current_app.config["LOGIN_WINDOW"] if window is None else window
    try:
        with _db() as db:
            db.execute("INSERT INTO failures (k, at) VALUES (?, ?)", (key, time.time()))
            (n,) = db.execute("SELECT count(*) FROM failures WHERE k = ? AND at >= ?",
                              (key, time.time() - window)).fetchone()
    except sqlite3.Error:
        return False
    return n == limit   # exactly at the limit: later failures are already behind a closed door


def clear(key):
    """Called after a password checks out, so two typos followed by the right one cost nothing."""
    if _off():
        return
    try:
        with _db() as db:
            db.execute("DELETE FROM failures WHERE k = ?", (key,))
    except sqlite3.Error:
        pass


def wait_text(seconds):
    """'Try again in 12 minutes' — a refusal with no end in sight reads like a broken site."""
    mins = (seconds + 59) // 60
    return f"Too many attempts. Try again in {mins} minute{'' if mins == 1 else 's'}."
