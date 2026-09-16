"""Load and abuse simulator for the owner-only /admin/stress panel.

Fires concurrent HTTP requests at a target -- this instance itself, or another one (dev -> prod) --
so the owner can watch throughput, latency and how the defences answer under pressure. Two kinds of
worker: *visitors* read real public pages, *attackers* run non-destructive probes (missing paths,
missing media, warranty-serial guesses, and lead posts with the honeypot filled so nothing is stored).

Progress lives in a sqlite file on /dev/shm, the same trick throttle.py uses: the ~30 gunicorn workers
are separate processes, so a run started in one and polled from another need shared memory, and tmpfs
gives it, wiped on redeploy -- exactly a load run's lifetime. Nothing here is application data.

Stdlib only (urllib, threading, sqlite3): pip install is denied and no load tool is in the image.

# ponytail: the controller thread lives inside whichever worker took the Run request. If that worker
# is recycled mid-run the run freezes at its last flush -- acceptable for a manual diagnostic; move the
# controller to its own process, or a broker, if runs must outlive a worker.
# ponytail: the only guard on the target URL is the scheme -- no SSRF allow-list. The panel is
# owner-only behind the office-only admin, and pointing dev at prod on the LAN is the whole point;
# add an allow-list if this ever escapes that trust boundary.
"""
import json
import math
import random
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid

STRESS_DB = "/dev/shm/iopstor-stress.db"   # constant, not an env key: keeps it out of x-app-env

# Caps on the entered numbers. One OS thread and one socket per worker, so the real ceiling is the
# machine's open-file-descriptor limit (often 1024) and thread overhead, not these -- past a few hundred
# to ~1000 the surplus turns into "no answer" errors rather than more concurrency, and on a small
# container it can OOM. These are the "push until it breaks" bound, not a promise of clean 10k concurrency.
# ponytail: thread-per-visitor. True concurrency in the thousands needs an async client (a barred dep);
# until then the honest figure is a few hundred, and the big numbers are a stress bound, not a benchmark.
MAX_VISITORS = 10000
MAX_ATTACKERS = 1000
MAX_SECONDS = 300
REQ_TIMEOUT = 15          # a stuck target must not pin a worker thread forever
LAT_SAMPLE = 2000         # reservoir size for the latency percentiles
FLUSH_EVERY = 0.5         # how often the controller writes progress out for the poll to read
UA = "IOPSTOR-stress/1.0"


def clamp(n, lo, hi):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))


def validate_target(url):
    """Normalise a base URL to scheme://host[:port], no trailing slash. Raises ValueError on anything
    that is not plain http/https with a host -- the one check standing in for an SSRF allow-list."""
    url = (url or "").strip().rstrip("/")
    m = re.match(r"^(https?)://([^/\s]+)$", url, re.I)
    if not m:
        raise ValueError("Enter a full base URL like http://host:port, no path.")
    return url


# ---- the progress store (sqlite on tmpfs) -----------------------------------------------------

def _db(path):
    db = sqlite3.connect(path, timeout=5)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started REAL, state TEXT, "
               "stop INTEGER DEFAULT 0, params TEXT, progress TEXT)")
    return db


def create(params, path=STRESS_DB):
    """Register a run as 'starting' and return its id."""
    rid = uuid.uuid4().hex[:12]
    with _db(path) as db:
        db.execute("INSERT INTO runs (id, started, state, params, progress) VALUES (?,?,?,?,?)",
                   (rid, time.time(), "starting", json.dumps(params), json.dumps({})))
    return rid


def read(rid, path=STRESS_DB):
    with _db(path) as db:
        row = db.execute("SELECT id, started, state, stop, params, progress FROM runs WHERE id=?",
                         (rid,)).fetchone()
    if not row:
        return None
    return {"id": row[0], "started": row[1], "state": row[2], "stop": bool(row[3]),
            "params": json.loads(row[4]), "progress": json.loads(row[5] or "{}")}


def _write(rid, state, progress, path):
    with _db(path) as db:
        db.execute("UPDATE runs SET state=?, progress=? WHERE id=?",
                   (state, json.dumps(progress), rid))


def request_stop(rid, path=STRESS_DB):
    with _db(path) as db:
        cur = db.execute("UPDATE runs SET stop=1 WHERE id=? AND state='running'", (rid,))
    return cur.rowcount > 0


def _stopped(rid, path):
    with _db(path) as db:
        row = db.execute("SELECT stop FROM runs WHERE id=?", (rid,)).fetchone()
    return bool(row and row[0])


# ---- metrics ----------------------------------------------------------------------------------

def percentile(sample, p):
    """Nearest-rank percentile over a latency sample, in ms. Empty -> 0."""
    if not sample:
        return 0.0
    s = sorted(sample)
    k = max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))
    return round(s[k] * 1000, 1)


class Metrics:
    """Thread-safe counters. Latencies are reservoir-sampled so the memory is bounded however long
    the run goes."""
    def __init__(self):
        self.lock = threading.Lock()
        self.sent = 0
        self.errors = 0
        self.status = {}
        self.kind = {"visitor": 0, "attacker": 0}
        self.lat = []
        self._seen = 0

    def record(self, kind, status, latency, error):
        with self.lock:
            self.sent += 1
            self.kind[kind] += 1
            if error:
                self.errors += 1
            else:
                self.status[str(status)] = self.status.get(str(status), 0) + 1
            self._seen += 1
            if len(self.lat) < LAT_SAMPLE:
                self.lat.append(latency)
            else:                                    # reservoir: keep the sample representative
                j = random.randint(0, self._seen - 1)
                if j < LAT_SAMPLE:
                    self.lat[j] = latency

    def snapshot(self, elapsed):
        with self.lock:
            lat = list(self.lat)
            status = dict(self.status)
            sent, errors, kind = self.sent, self.errors, dict(self.kind)
        return {
            "sent": sent, "errors": errors, "status": status, "kind": kind,
            "req_per_sec": round(sent / elapsed, 1) if elapsed > 0 else 0.0,
            "avg_ms": round(sum(lat) / len(lat) * 1000, 1) if lat else 0.0,
            "p95_ms": percentile(lat, 95), "max_ms": round(max(lat) * 1000, 1) if lat else 0.0,
            "throttled": status.get("429", 0), "elapsed": round(elapsed, 1),
        }


# ---- the requests -----------------------------------------------------------------------------

def _fetch(method, url, data=None):
    """One request. Returns (status, seconds, error_or_None). An HTTP error status (404, 429, 413) is
    a result, not an error; only a dead socket or a timeout is an error."""
    headers = {"User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
            r.read()
            return r.status, time.perf_counter() - t, None
    except urllib.error.HTTPError as e:
        try:
            e.read()
        except Exception:   # noqa: BLE001 - draining is best-effort
            pass
        return e.code, time.perf_counter() - t, None
    except Exception as e:   # noqa: BLE001 - URLError, timeout, socket, DNS: all "the target did not answer"
        return None, time.perf_counter() - t, str(e)[:80] or "error"


def _rand():
    return uuid.uuid4().hex[:10]


def sitemap_urls(base):
    """Real public URLs to read: the target's sitemap, or just its home page if there is none."""
    status, _, err = None, None, None
    try:
        req = urllib.request.Request(base + "/sitemap.xml", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
        return urls or [base + "/"]
    except Exception:   # noqa: BLE001 - no sitemap, unreachable, malformed: fall back to home
        return [base + "/"]


def _visit(base, urls):
    return ("visitor", *_fetch("GET", random.choice(urls)))


def _attack(base, warranty_path):
    """One non-destructive probe, chosen at random."""
    pick = random.randint(0, 3)
    if pick == 0:                                          # a path that resolves to nothing
        return ("attacker", *_fetch("GET", f"{base}/{_rand()}"))
    if pick == 1:                                          # a media key that does not exist
        return ("attacker", *_fetch("GET", f"{base}/media/{_rand()}.jpg"))
    if pick == 2:                                          # warranty serial enumeration (reads only)
        sep = "&" if "?" in warranty_path else "?"
        return ("attacker", *_fetch("GET", f"{base}{warranty_path}{sep}sn={_rand().upper()}"))
    # a lead post with the honeypot filled: the endpoint accepts and drops it -- no row, no audit
    body = json.dumps({"name": "load-test", "email": f"{_rand()}@example.invalid",
                       "website": "http://filled-honeypot.invalid"}).encode()
    return ("attacker", *_fetch("POST", f"{base}/api/v1/leads", body))


def _worker(fn, args, metrics, deadline, stop_flag):
    while time.time() < deadline and not stop_flag.is_set():
        kind, status, latency, error = fn(*args)
        metrics.record(kind, status, latency, error)


def run_load(rid, target, visitors, attackers, seconds, warranty_path="/", path=STRESS_DB):
    """The controller: start the workers, flush progress while they run, finalise. Runs in its own
    background thread (see start())."""
    metrics = Metrics()
    start_t = time.time()
    deadline = start_t + seconds
    stop_flag = threading.Event()
    try:
        urls = sitemap_urls(target)
        _write(rid, "running", metrics.snapshot(0.0), path)
        threads = []
        for _ in range(visitors):
            threads.append(threading.Thread(target=_worker,
                           args=(_visit, (target, urls), metrics, deadline, stop_flag), daemon=True))
        for _ in range(attackers):
            threads.append(threading.Thread(target=_worker,
                           args=(_attack, (target, warranty_path), metrics, deadline, stop_flag), daemon=True))
        for t in threads:
            t.start()
        while any(t.is_alive() for t in threads):
            if _stopped(rid, path):
                stop_flag.set()
            _write(rid, "running", metrics.snapshot(time.time() - start_t), path)
            time.sleep(FLUSH_EVERY)
            if time.time() > deadline + REQ_TIMEOUT + 5:   # workers should have stopped; do not hang
                stop_flag.set()
                break
        for t in threads:
            t.join(timeout=1)
        _write(rid, "done", metrics.snapshot(time.time() - start_t), path)
    except Exception as e:   # noqa: BLE001 - a broken run must land as 'error', not vanish
        snap = metrics.snapshot(time.time() - start_t)
        snap["error"] = str(e)[:200]
        _write(rid, "error", snap, path)


def start(target, visitors, attackers, seconds, warranty_path="/", path=STRESS_DB):
    """Validate, clamp, register the run and kick off its controller thread. Returns the run id.
    Raises ValueError if the target is not a usable base URL."""
    target = validate_target(target)
    visitors = clamp(visitors, 0, MAX_VISITORS)
    attackers = clamp(attackers, 0, MAX_ATTACKERS)
    seconds = clamp(seconds, 1, MAX_SECONDS)
    warranty_path = "/" + (warranty_path or "/").strip().lstrip("/")
    rid = create({"target": target, "visitors": visitors, "attackers": attackers,
                  "seconds": seconds}, path)
    threading.Thread(target=run_load,
                     args=(rid, target, visitors, attackers, seconds, warranty_path, path),
                     daemon=True).start()
    return rid
