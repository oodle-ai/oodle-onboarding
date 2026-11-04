"""The demo's incident: a schema change on apac-orders that loses an index.

Nothing else changes. Without the index, the query in apac_orders.py scans
order_events once per order, takes longer than the warehouse's timeout, and
the warehouse answers without APAC.

Usage: python migrate.py drop-index | restore-index
"""

import os
import sqlite3
import sys

DB_PATH = os.environ.get("APAC_DB", "/data/apac.db")
STATEMENTS = {
    "drop-index": "DROP INDEX IF EXISTS order_events_order",
    "restore-index": "CREATE INDEX IF NOT EXISTS order_events_order ON order_events(order_id)",
}


def main(action: str) -> None:
    db = sqlite3.connect(DB_PATH)
    db.execute(STATEMENTS[action])
    db.commit()
    db.close()
    print(f"apac-orders: {action} done")


if __name__ == "__main__":
    main(sys.argv[1])
