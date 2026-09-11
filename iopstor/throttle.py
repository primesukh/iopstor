"""Failed-attempt counter, shared by every gunicorn worker: one sqlite file on tmpfs.

The container runs ~30 workers in separate address spaces, so a module-level dict would be thirty
independent counters and thirty times the intended ceiling. `/dev/shm` is tmpfs — RAM, shared by
every process in the container, empty again after a redeploy, which is exactly the lifetime a
brute-force counter wants. sqlite gives the cross-process locking, the expiry and the unbounded key
space for a fraction of the code a hand-packed mmap table would need.

# ponytail: per container. Scale the service to two replicas and each gets its own counter, so the
# effective limit doubles; move the keys to Redis if that day comes.
"""
import sqlite3
import time

from flask import current_app, request


def client_ip():
    """The visitor, not the tunnel. Cloudflare sets CF-Connecting-IP to the real client address and
    strips any copy the client sent, and cloudflared is outbound-only — nothing can reach this app
    around it — which is what makes the header trustworthy here. remote_addr is the fallback for
    local development, where there is no proxy in the way at all.

    # ponytail: trusts that header. Publish port 8000 on a network someone else is on and they can
    # spoof it past the limit; switch to ProxyFix with the real hop count if that ever happens."""
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "-"


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
