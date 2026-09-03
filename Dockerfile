FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FLASK_APP=iopstor
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz')"
# Apply migrations/*.sql, then serve. Dokploy injects env vars (DATABASE_URL, SUPABASE_*, SECRET_KEY, SITE_URL).
CMD ["sh", "-c", "flask migrate && exec gunicorn -w 2 -b 0.0.0.0:8000 'iopstor:create_app()'"]
