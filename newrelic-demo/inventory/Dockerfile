FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && opentelemetry-bootstrap -a install
COPY app.py .
# Both agents in one process without their launchers (newrelic-admin / opentelemetry-instrument
# can't be chained: each strips itself from PYTHONPATH before exec'ing the next). New Relic's
# bootstrap sitecustomize runs first and chains to OTel's; the two NEW_RELIC_PYTHON_* vars are
# what newrelic-admin would have set.
ENV PYTHONPATH=/usr/local/lib/python3.12/site-packages/newrelic/bootstrap:/usr/local/lib/python3.12/site-packages/opentelemetry/instrumentation/auto_instrumentation \
    NEW_RELIC_PYTHON_PREFIX=/usr/local NEW_RELIC_PYTHON_VERSION=3.12
CMD ["python", "app.py"]
