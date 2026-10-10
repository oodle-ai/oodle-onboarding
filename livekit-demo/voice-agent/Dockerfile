FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py tracing.py web.py verify_local.py ./
COPY static ./static

# Fetch the plugins' model files now rather than on the first call.
RUN python agent.py download-files

# The agent worker. web.py runs from the same image, with its own command.
CMD ["python", "agent.py", "start"]
