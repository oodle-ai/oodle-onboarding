FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# opentelemetry-bootstrap installs the instrumentation for every library it
# finds (FastAPI, httpx, sqlite3, threading ...): zero-code tracing, as the
# reference backend gets from the OpenTelemetry Java agent.
RUN pip install --no-cache-dir -r requirements.txt \
    && opentelemetry-bootstrap -a install

COPY db.py web.py app.py provision.py run.py ./
COPY bid_docs ./bid_docs

# Each compose service picks its command: the two servers run under
# opentelemetry-instrument, the one-shot scripts run plain.
CMD ["python", "-u", "run.py"]
