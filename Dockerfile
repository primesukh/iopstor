FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FLASK_APP=iopstor
# gunicorn reads this itself; Dokploy's environment overrides it (production runs -w 30). The app keeps
# nothing between requests, so the worker count is deploy config, not code -- docs/TECHNICAL.md §15.
# --access-logfile - puts one line per request on stdout, which is the only request log there is;
# the HEALTHCHECK below adds a /healthz line every 30s, and that is not traffic.
ENV GUNICORN_CMD_ARGS="-w 2 --threads 8 --preload --access-logfile -"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# bash's /dev/tcp, not python: `python -c "import urllib.request"` measured 115ms of CPU a run (a bare
# interpreter is 31ms; the import is the rest), and every 30s of that drew evenly spaced ~45% spikes on
# an otherwise idle container's monitor. This is 4.4ms and still a real GET with a real status check --
# a socket-only probe was rejected because gunicorn's listen backlog accepts TCP with every worker
# wedged. Exec form and `bash` by name: the shell form runs /bin/sh, which is dash and has no /dev/tcp.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["bash","-c","exec 3<>/dev/tcp/127.0.0.1/8000; printf 'GET /healthz HTTP/1.0\\r\\n\\r\\n' >&3; head -1 <&3 | grep -q ' 200 '"]
# Apply migrations/*.sql, then serve. Dokploy injects env vars (SUPABASE_*, SECRET_KEY, SITE_URL, GUNICORN_CMD_ARGS).
CMD ["sh", "-c", "flask migrate && exec gunicorn -b 0.0.0.0:8000 'iopstor:create_app()'"]
