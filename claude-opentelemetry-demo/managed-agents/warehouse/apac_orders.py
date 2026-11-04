"""APAC's order system: an acquisition the warehouse hasn't absorbed yet.

The warehouse holds every other region and fetches APAC's orders from here on
each query. Orders with a cancelled event don't count, and that check is the
query's only expensive part: it needs the index on order_events(order_id).
migrate.py removes that index to start the demo's incident.

Like the warehouse, this file has no tracing setup. It runs under
`opentelemetry-instrument`, so each request and its SELECT are spans, joined
to the agent's trace by the traceparent on the warehouse's request.
"""

import os
import sqlite3

from fastapi import FastAPI

DB_PATH = os.environ.get("APAC_DB", "/data/apac.db")

LIVE_ORDERS = """
SELECT o.order_id, o.order_date, o.region, o.channel, o.product_id, o.quantity, o.unit_price
FROM orders o
WHERE NOT EXISTS (
    SELECT 1 FROM order_events e WHERE e.order_id = o.order_id AND e.type = 'cancelled'
)
ORDER BY o.order_date
"""
# The sort also keeps the SELECT span honest. SQLite returns rows lazily, and the
# span ends when execute() returns. Sorting makes execute() finish the scan first.

app = FastAPI(title="apac-orders")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/orders")
def orders() -> list:
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        # A cursor's execute, not db.execute: the sqlite3 instrumentation traces only the cursor.
        cursor = db.cursor()
        cursor.execute(LIVE_ORDERS)
        return cursor.fetchall()
    finally:
        db.close()
