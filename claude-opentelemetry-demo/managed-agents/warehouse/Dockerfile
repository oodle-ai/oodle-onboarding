FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && opentelemetry-bootstrap -a install

COPY seed.py .
RUN mkdir /data && python seed.py /data/warehouse.db

COPY app.py .

EXPOSE 8080

# opentelemetry-instrument loads the instrumentations before the app starts.
# One uvicorn process, no --reload: a reloader or worker fork would start the
# app in a process the instrumentation never saw.
CMD ["opentelemetry-instrument", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
