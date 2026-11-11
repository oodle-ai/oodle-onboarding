import json
import os

import pika
import psycopg2
import redis
from flask import Flask, jsonify, request

db = psycopg2.connect(os.environ["DATABASE_URL"])
db.autocommit = True
cache = redis.Redis.from_url(os.environ["REDIS_URL"])

with db.cursor() as cur:
    cur.execute("CREATE TABLE IF NOT EXISTS inventory (product_id INT PRIMARY KEY, stock INT NOT NULL)")
    cur.execute("INSERT INTO inventory VALUES (1, 100000), (2, 100000), (3, 100000) ON CONFLICT DO NOTHING")

app = Flask(__name__)


@app.get("/stock/<int:product_id>")
def stock(product_id):
    hit = cache.get(f"stock:{product_id}")
    if hit is not None:
        return jsonify(product_id=product_id, stock=int(hit), source="cache")
    with db.cursor() as cur:
        cur.execute("SELECT stock FROM inventory WHERE product_id = %s", (product_id,))
        row = cur.fetchone()
    if not row:
        return jsonify(error="unknown product"), 404
    cache.set(f"stock:{product_id}", row[0], ex=10)
    return jsonify(product_id=product_id, stock=row[0], source="db")


@app.post("/reserve")
def reserve():
    body = request.get_json()
    with db.cursor() as cur:
        cur.execute("UPDATE inventory SET stock = stock - %s WHERE product_id = %s AND stock >= %s RETURNING stock",
                    (body["qty"], body["product_id"], body["qty"]))
        row = cur.fetchone()
    if not row:
        return jsonify(error="out of stock or unknown product"), 409
    cache.set(f"stock:{body['product_id']}", row[0], ex=10)
    # fanout exchange with no bound queue: messages are dropped, so nothing accumulates in RabbitMQ
    conn = pika.BlockingConnection(pika.URLParameters(os.environ["AMQP_URL"]))
    ch = conn.channel()
    ch.exchange_declare("stock-events", "fanout")
    ch.basic_publish("stock-events", "", json.dumps({"product_id": body["product_id"], "stock": row[0]}))
    conn.close()
    return jsonify(product_id=body["product_id"], stock=row[0])


app.run(host="0.0.0.0", port=8081)
