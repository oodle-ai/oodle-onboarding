FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py tracing.py tracing_otel.py tracing_langfuse.py destinations.py verify_local.py ./

EXPOSE 7860

# The runner binds the container's interface, not localhost, and serves the
# prebuilt WebRTC client on the same port.
CMD ["python", "bot.py", "--host", "0.0.0.0", "--port", "7860", "--transport", "webrtc"]
