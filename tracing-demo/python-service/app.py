import random
import time

from flask import Flask, jsonify, request
from opentelemetry import trace

app = Flask(__name__)
tracer = trace.get_tracer("inventory-service")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "python-service"})


@app.route("/check-inventory")
def check_inventory():
    item = request.args.get("item", "unknown")

    with tracer.start_as_current_span("inventory.database_lookup") as span:
        span.set_attribute("inventory.item", item)

        # Simulate database lookup with random delay (30-150ms)
        delay = random.uniform(0.03, 0.15)
        time.sleep(delay)

        in_stock = random.choice([True, False])
        quantity = random.randint(0, 100) if in_stock else 0

        span.set_attribute("inventory.in_stock", in_stock)
        span.set_attribute("inventory.quantity", quantity)

    return jsonify({"item": item, "in_stock": in_stock, "quantity": quantity})


@app.route("/get-pricing")
def get_pricing():
    item = request.args.get("item", "unknown")

    with tracer.start_as_current_span("pricing.calculate") as span:
        span.set_attribute("pricing.item", item)

        # Simulate pricing lookup with random delay (20-100ms)
        delay = random.uniform(0.02, 0.10)
        time.sleep(delay)

        price = round(random.uniform(5.0, 500.0), 2)
        currency = "USD"

        span.set_attribute("pricing.price", price)
        span.set_attribute("pricing.currency", currency)

    return jsonify({"item": item, "price": price, "currency": currency})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082)
