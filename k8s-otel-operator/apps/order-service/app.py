import logging
import random
import time

from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-service")

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify(status="ok", service="order-service")


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    item = data.get("item", "unknown")
    quantity = data.get("quantity", 1)

    logger.info("Processing order", extra={"item": item, "quantity": quantity})

    time.sleep(random.uniform(0.01, 0.05))

    in_stock = random.choice([True, True, True, False])
    price = round(random.uniform(5.0, 50.0), 2)
    total = round(price * quantity, 2)

    if not in_stock:
        logger.warning("Item out of stock", extra={"item": item})
    else:
        logger.info("Order processed", extra={"item": item, "total": total})

    return jsonify(
        service="order-service",
        item=item,
        quantity=quantity,
        in_stock=in_stock,
        price=price,
        total=total,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
