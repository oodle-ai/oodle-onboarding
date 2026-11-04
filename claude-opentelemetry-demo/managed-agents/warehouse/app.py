"""The warehouse: read-only SQL over the demo sales data.

It backs the data analyst agent's `query_warehouse` custom tool. The agent
calls the tool, the session pauses, main.py POSTs the SQL here and sends the
rows back as the tool result.

APAC's orders aren't here: each query fetches them from the apac-orders
service first (see load_apac_orders).

There's no tracing setup in this file. The container runs it under
`opentelemetry-instrument` (see the Dockerfile), which instruments FastAPI,
httpx and sqlite3 before the app is imported and takes its exporter settings
from the OTEL_* variables. main.py sends `traceparent` with each request, so
the request's SERVER span, and the spans under it, join the managed agent's
trace as children of the tool span.
"""

import logging
import os
import sqlite3
import time

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel

DB_PATH = os.environ.get("WAREHOUSE_DB", "/data/warehouse.db")
MAX_ROWS = 200
QUERY_SECONDS = 5.0
APAC_TIMEOUT_SECONDS = 8.0

# Reads only: no writes, no ATTACH, no PRAGMA.
ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

app = FastAPI(title="warehouse")
log = logging.getLogger("warehouse")
# Auto-instrumentation puts a handler on the root logger, which turns off
# Python's default output to stderr.
log.addHandler(logging.StreamHandler())
apac_orders = httpx.Client(base_url=os.environ.get("APAC_ORDERS_URL", "http://apac-orders:8080"), timeout=APAC_TIMEOUT_SECONDS)


class Query(BaseModel):
    sql: str


def authorize(action: int, *_args) -> int:
    return sqlite3.SQLITE_OK if action in ALLOWED else sqlite3.SQLITE_DENY


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


def load_apac_orders(db: sqlite3.Connection) -> None:
    """Put APAC's orders next to the local ones, in a temp table that shadows `orders`.

    The demo's bug, on purpose: a failed fetch is only logged, so the query
    runs without APAC and still answers 200. Nothing in the response says the
    data is partial, so neither the agent nor the session's events can tell.
    """
    db.execute("CREATE TEMP TABLE orders AS SELECT * FROM main.orders")
    try:
        response = apac_orders.get("/orders")
        response.raise_for_status()
        db.executemany("INSERT INTO temp.orders VALUES (?, ?, ?, ?, ?, ?, ?)", response.json())
    except httpx.HTTPError as e:
        log.warning("apac-orders failed, answering without APAC: %r", e)
    db.commit()


@app.post("/query")
def query(q: Query) -> dict:
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        load_apac_orders(db)
        db.set_authorizer(authorize)
        deadline = time.monotonic() + QUERY_SECONDS
        db.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
        # A cursor's execute, not db.execute: the sqlite3 instrumentation traces only the cursor.
        cursor = db.cursor()
        try:
            cursor.execute(q.sql)
            rows = cursor.fetchmany(MAX_ROWS + 1)
        except sqlite3.Error as e:
            # The error goes back to the agent as the tool result, so it can fix its SQL.
            raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}") from e
        columns = [c[0] for c in cursor.description or []]
    finally:
        db.close()

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    # Auto-instrumentation made this span; the app only adds what it knows.
    span = trace.get_current_span()
    span.set_attribute("warehouse.row_count", len(rows))
    span.set_attribute("warehouse.truncated", truncated)
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}
