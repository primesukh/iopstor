"""Load and abuse simulator for the owner-only /admin/stress panel.

Fires concurrent HTTP requests at a target -- this instance itself, or another one (dev -> prod) --
so the owner can watch throughput, latency and how the defences answer under pressure. Two kinds of
worker: *visitors* read real public pages, *attackers* run non-destructive probes (missing paths,
missing media, warranty-serial guesses, and lead posts with the honeypot filled so nothing is stored).

Progress lives in a sqlite file on /dev/shm, the same trick throttle.py uses: the ~30 gunicorn workers
are separate processes, so a run started in one and polled from another need shared memory, and tmpfs
gives it, wiped on redeploy -- exactly a load run's lifetime. Nothing here is application data.

One CPython process is GIL-bound, so past a few hundred threads throughput FALLS, not rises. To lift
that the load fans out across processes (`_nprocs()` of them, spawned), each running the thread model
below for its share; a coordinator merges their partial counts into the one run row the poll reads. The
generator processes are separate from the ~30 gunicorn workers that serve requests -- the Run lands on
one worker, which spawns the children; the other workers keep serving and can still answer the progress
poll because the run state is in the shared /dev/shm store.

Stdlib only (urllib, threading, multiprocessing, sqlite3): pip install is denied and no load tool is
in the image. multiprocessing uses the "spawn" context so a gunicorn worker's forked state, sockets and
locks are never copied into a child.

# ponytail: processes x threads, ceiling ~= cores. It multiplies the single-process throughput by the
# core count, not to an unconditional 10k; and the target caps it first (PostgREST pool of 10). A real
# async client would go further but is a barred dependency.
# ponytail: the controller thread and the children live in whichever worker took the Run request. If
# that worker is recycled mid-run the run freezes at its last flush (children are daemon, so they die
# with it) -- acceptable for a manual diagnostic; a broker would be the fix if runs must outlive a worker.
# ponytail: the only guard on the target URL is the scheme -- no SSRF allow-list. The panel is
# owner-only behind the office-only admin, and pointing dev at prod on the LAN is the whole point;
# add an allow-list if this ever escapes that trust boundary.
# ponytail: nothing prevents two runs at once (two Run clicks land on two workers) -- owner-only, so the
# double load is on the one person who asked for it; add a single-active-run lock if that changes.
"""
import json
import math
import multiprocessing
import os
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
REQ_TIMEOUT = 10          # a stuck target must not pin a worker thread forever, nor drag out the wind-down
LAT_SAMPLE = 2000         # reservoir size for the latency percentiles (per process)
FLUSH_EVERY = 0.5         # how often a generator writes its part out, and the coordinator merges
GRACE = 2                 # seconds after the deadline (or a Stop) before child processes are terminated
UA = "IOPSTOR-stress/1.0"
PER_PROC = 250            # threads per process; the total real concurrency ceiling is this x _nprocs()
MAX_PROCS = 16            # hard ceiling on spawned generator processes


def _plan(visitors, attackers):
    """Decide the real shape of a run: how many generator processes, and how many visitor/attacker threads
    each gets. The important part is the CAP -- real concurrency never exceeds nprocs x PER_PROC, however
    large the entered numbers are. One OS thread per worker, so an uncapped '10000 visitors' would spawn
    ten thousand threads: many seconds just to create, a thrashed box (worse on a self-test), and a run
    that then takes ages to tear those threads down -- while buying no throughput past the cap (measured).
    Over the cap, the entered numbers are scaled down proportionally. Returns (nprocs, vsplit, asplit)."""
    total = visitors + attackers
    if total == 0:
        return 1, [0], [0]
    nprocs = _nprocs(visitors, attackers)
    cap = nprocs * PER_PROC
    if total > cap:                                    # scale visitors:attackers down to fit the machine
        visitors = round(visitors * cap / total)
        attackers = round(attackers * cap / total)
    return nprocs, _split(visitors, nprocs), _split(attackers, nprocs)


def _nprocs(visitors, attackers):
    """How many generator processes to fan out to. 1 (an in-process thread, spawn-free and snappy) until
    the load is worth splitting, then one per PER_PROC up to the container's own CPU quota. Uses
    os.process_cpu_count() (Python 3.13), which honours a cgroup/affinity limit -- os.cpu_count() reports
    the host's cores, so on a CPU-capped container behind a big host it would oversubscribe wildly."""
    load = visitors + attackers
    if load <= PER_PROC:
        return 1
    cpu = os.process_cpu_count() or 2
    return max(1, min(cpu, MAX_PROCS, math.ceil(load / PER_PROC)))


def _split(n, k):
    """Distribute n as evenly as possible across k buckets; the buckets sum to n."""
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


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
    db.execute("PRAGMA journal_mode=WAL")   # many child writers + the coordinator reader, no blocking
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started REAL, state TEXT, "
               "stop INTEGER DEFAULT 0, params TEXT, progress TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS parts (rid TEXT, idx INTEGER, progress TEXT, "
               "PRIMARY KEY (rid, idx))")
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


def _write_part(rid, idx, raw, path):
    """One generator's own running counts. The coordinator reads every part and sums them."""
    with _db(path) as db:
        db.execute("INSERT OR REPLACE INTO parts (rid, idx, progress) VALUES (?,?,?)",
                   (rid, idx, json.dumps(raw)))


def _read_parts(rid, path):
    with _db(path) as db:
        rows = db.execute("SELECT progress FROM parts WHERE rid=?", (rid,)).fetchall()
    return [json.loads(r[0]) for r in rows]


# ---- metrics ----------------------------------------------------------------------------------

def percentile(sample, p):
    """Nearest-rank percentile over a latency sample, in ms. Empty -> 0."""
    if not sample:
        return 0.0
    s = sorted(sample)
    k = max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))
    return round(s[k] * 1000, 1)


def _derive(sent, errors, status, kind, lat, elapsed):
    """The progress dict the UI reads, from raw counts. Shared by a single generator's snapshot and by
    the coordinator's merge of many, so the shape is defined once."""
    return {
        "sent": sent, "errors": errors, "status": status, "kind": kind,
        "req_per_sec": round(sent / elapsed, 1) if elapsed > 0 else 0.0,
        "avg_ms": round(sum(lat) / len(lat) * 1000, 1) if lat else 0.0,
        "p95_ms": percentile(lat, 95), "max_ms": round(max(lat) * 1000, 1) if lat else 0.0,
        "throttled": status.get("429", 0), "elapsed": round(elapsed, 1),
    }


class Metrics:
    """Thread-safe counters for one generator (process). Latencies are reservoir-sampled so the memory
    is bounded however long the run goes."""
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

    def raw(self):
        """The mergeable counts, for a part row. Not derived -- the coordinator sums these first."""
        with self.lock:
            return {"sent": self.sent, "errors": self.errors, "status": dict(self.status),
                    "kind": dict(self.kind), "lat": list(self.lat)}

    def snapshot(self, elapsed):
        r = self.raw()
        return _derive(r["sent"], r["errors"], r["status"], r["kind"], r["lat"], elapsed)


def _merge_parts(rid, path, elapsed):
    """Sum every generator's raw counts into the one progress dict the poll reads."""
    sent = errors = 0
    status, kind, lat = {}, {"visitor": 0, "attacker": 0}, []
    for r in _read_parts(rid, path):
        sent += r.get("sent", 0)
        errors += r.get("errors", 0)
        for k, v in (r.get("status") or {}).items():
            status[k] = status.get(k, 0) + v
        for k, v in (r.get("kind") or {}).items():
            kind[k] = kind.get(k, 0) + v
        lat.extend(r.get("lat") or [])
    return _derive(sent, errors, status, kind, lat, elapsed)


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
        req = urllib.request.Request(base + "/sitemap", headers={"User-Agent": UA})
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


def _generate(rid, idx, target, visitors, attackers, deadline, warranty_path, urls, path=STRESS_DB):
    """One generator: run this share's threads until the deadline or the stop flag, writing its own part
    row every FLUSH_EVERY. Module-level and picklable, so it is both the thread target (nprocs==1) and the
    spawned-process target (nprocs>1). It never touches the run row -- the coordinator merges the parts."""
    metrics = Metrics()
    stop_flag = threading.Event()
    threads = [threading.Thread(target=_worker, args=(_visit, (target, urls), metrics, deadline, stop_flag),
                                daemon=True) for _ in range(visitors)]
    threads += [threading.Thread(target=_worker, args=(_attack, (target, warranty_path), metrics, deadline,
                                 stop_flag), daemon=True) for _ in range(attackers)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        if _stopped(rid, path):
            stop_flag.set()
        _write_part(rid, idx, metrics.raw(), path)
        time.sleep(FLUSH_EVERY)
        if time.time() > deadline + REQ_TIMEOUT + 2:   # workers should have stopped; do not hang
            stop_flag.set()
            break
    for t in threads:
        t.join(timeout=1)
    _write_part(rid, idx, metrics.raw(), path)


def run_load(rid, target, seconds, vsplit, asplit, warranty_path="/", path=STRESS_DB):
    """The coordinator: fan the load out across generators (a thread, or spawned processes), merge their
    parts into the run row while they run, finalise. vsplit/asplit are the per-generator thread counts
    (already capped by _plan). Runs in its own background thread (see start())."""
    start_t = time.time()
    deadline = start_t + seconds
    nprocs = len(vsplit)
    try:
        urls = sitemap_urls(target)                    # fetched once, handed to every generator
        _write(rid, "running", _merge_parts(rid, path, 0.0), path)
        procs = []
        if nprocs == 1:                                # small run: an in-process thread, no spawn cost
            gen = threading.Thread(target=_generate, args=(rid, 0, target, vsplit[0], asplit[0], deadline,
                                   warranty_path, urls, path), daemon=True)
            gen.start()
            workers = [gen]
        else:
            ctx = multiprocessing.get_context("spawn")  # a fresh interpreter, not a fork of this worker
            for i in range(nprocs):
                p = ctx.Process(target=_generate, args=(rid, i, target, vsplit[i], asplit[i], deadline,
                                warranty_path, urls, path), daemon=True)
                p.start()
                procs.append(p)
            workers = procs
        mark = None                                    # when the deadline passed or Stop was pressed
        while any(w.is_alive() for w in workers):
            if mark is None and (time.time() >= deadline or _stopped(rid, path)):
                mark = time.time()
            _write(rid, "running", _merge_parts(rid, path, time.time() - start_t), path)
            # A worker blocked in a request cannot be interrupted, so waiting for a graceful drain means
            # waiting a whole REQ_TIMEOUT on a saturated target. Once time is up, kill the child processes
            # instead (SIGTERM takes their threads with them); the run ends within GRACE, not a timeout.
            if mark is not None and time.time() > mark + GRACE:
                for p in procs:
                    p.terminate()
                break
            time.sleep(FLUSH_EVERY)
        for w in workers:
            w.join(timeout=2)
        _write(rid, "done", _merge_parts(rid, path, time.time() - start_t), path)
    except Exception as e:   # noqa: BLE001 - a broken run must land as 'error', not vanish
        snap = _merge_parts(rid, path, time.time() - start_t)
        snap["error"] = str(e)[:200]
        _write(rid, "error", snap, path)


def start(target, visitors, attackers, seconds, warranty_path="/", path=STRESS_DB):
    """Validate, clamp, plan the fan-out, register the run and kick off its coordinator thread. Returns
    the run id. Raises ValueError if the target is not a usable base URL. The run records both the
    requested numbers and the *_run numbers actually driven (real concurrency is capped to what the
    machine can drive -- see _plan)."""
    target = validate_target(target)
    visitors = clamp(visitors, 0, MAX_VISITORS)
    attackers = clamp(attackers, 0, MAX_ATTACKERS)
    seconds = clamp(seconds, 1, MAX_SECONDS)
    warranty_path = "/" + (warranty_path or "/").strip().lstrip("/")
    nprocs, vsplit, asplit = _plan(visitors, attackers)
    rid = create({"target": target, "visitors": visitors, "attackers": attackers,
                  "visitors_run": sum(vsplit), "attackers_run": sum(asplit), "procs": nprocs,
                  "seconds": seconds}, path)
    threading.Thread(target=run_load,
                     args=(rid, target, seconds, vsplit, asplit, warranty_path, path),
                     daemon=True).start()
    return rid
