FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

CMD ["opentelemetry-instrument", "gunicorn", "--bind", "0.0.0.0:8082", "--workers", "2", "app:app"]
