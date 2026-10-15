FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY provision.py main.py ./

# `docker compose run --rm managed-agents provision.py` runs the one-time setup.
ENTRYPOINT ["python", "-u"]
CMD ["main.py"]
