"""storefront is the entry service. It runs under ddtrace-run (see
Dockerfile), so Flask and requests are traced and the trace context
propagates to orders automatically."""

import logging
import os
import random

import requests
from flask import Flask, jsonify

ORDERS_URL = os.environ.get("ORDERS_URL", "http://localhost:8082")
SKUS = ["sku-100", "sku-200", "sku-300", "sku-400", "sku-999"]

app = Flask(__name__)
log = logging.getLogger("storefront")


@app.get("/health")
def health():
    return "", 200


@app.get("/catalog")
def catalog():
    return jsonify(skus=SKUS[:-1])


@app.post("/checkout")
def checkout():
    # sku-999 does not exist in inventory, so some checkouts end in a 422.
    sku = random.choice(SKUS)
    resp = requests.post(f"{ORDERS_URL}/orders", json={"sku": sku}, timeout=5)
    if resp.status_code >= 500:
        log.error("checkout failed for %s: %s", sku, resp.text)
        return jsonify(error="checkout failed"), 502
    return jsonify(resp.json()), resp.status_code
