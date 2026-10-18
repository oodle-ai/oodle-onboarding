"""The warehouse: read-only SQL over the demo sales data.

It backs the data analyst agent's `query_warehouse` custom tool. The agent
calls the tool, the session pauses, main.py POSTs the SQL here and sends the
rows back as the tool result.

There's no tracing setup in this file. The container runs it under
`opentelemetry-instrument` (see the Dockerfile), which instruments FastAPI and
sqlite3 before the app is imported and takes its exporter settings from the
OTEL_* variables. main.py sends `traceparent` with each request, so the
request's SERVER span, and the SELECT spans under it, join the managed agent's
trace as children of the tool span.
"""

import os
import sqlite3
import time

from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel

DB_PATH = os.environ.get("WAREHOUSE_DB", "/data/warehouse.db")
MAX_ROWS = 200
QUERY_SECONDS = 5.0

# Reads only: no writes, no ATTACH, no PRAGMA.
ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

app = FastAPI(title="warehouse")


class Query(BaseModel):
    sql: str


def authorize(action: int, *_args) -> int:
    return sqlite3.SQLITE_OK if action in ALLOWED else sqlite3.SQLITE_DENY


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/query")
def query(q: Query) -> dict:
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
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
