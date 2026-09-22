import json
import os
import random
import time

import pika
import psycopg2
import redis

db = psycopg2.connect(os.environ["DATABASE_URL"])
db.autocommit = True
cache = redis.Redis.from_url(os.environ["REDIS_URL"])

conn = pika.BlockingConnection(pika.URLParameters(os.environ["AMQP_URL"]))
ch = conn.channel()
ch.queue_declare("orders", durable=True)
ch.basic_qos(prefetch_count=1)


def handle(ch, method, _props, body):
    order_id = json.loads(body)["id"]
    time.sleep(random.uniform(0.05, 0.3))  # pretend to do work
    with db.cursor() as cur:
        cur.execute("UPDATE orders SET status = 'processed' WHERE id = %s", (order_id,))
    cache.incr("orders:processed")
    cache.delete("products")  # nothing depends on this; just exercises another Redis command
    ch.basic_ack(method.delivery_tag)
    print(f"processed order {order_id}", flush=True)


ch.basic_consume("orders", handle)
print("worker consuming from 'orders'", flush=True)
ch.start_consuming()
